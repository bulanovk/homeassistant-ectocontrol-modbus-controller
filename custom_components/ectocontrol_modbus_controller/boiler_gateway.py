"""BoilerGateway: maps Modbus registers to semantic boiler values."""
from __future__ import annotations

from typing import Dict, Optional
import asyncio
import logging

from .const import (
    REGISTER_CH_TEMP,
    REGISTER_DHW_TEMP,
    REGISTER_PRESSURE,
    REGISTER_FLOW,
    REGISTER_MODULATION,
    REGISTER_STATES,
    REGISTER_MAIN_ERROR,
    REGISTER_ADD_ERROR,
    REGISTER_OUTDOOR_TEMP,
    REGISTER_MFG_CODE,
    REGISTER_MODEL_CODE,
    REGISTER_OT_ERROR,
    REGISTER_CH_SETPOINT,
    REGISTER_CH_SETPOINT_ACTIVE,
    REGISTER_CH_MIN,
    REGISTER_CH_MAX,
    REGISTER_DHW_SETPOINT,
    REGISTER_DHW_MIN,
    REGISTER_DHW_MAX,
    REGISTER_MAX_MODULATION,
    REGISTER_COMMAND,
    REGISTER_COMMAND_RESULT,
    REGISTER_CIRCUIT_ENABLE,
    REGISTER_STATUS,
    REGISTER_STATUS_BASE,
    REGISTER_VERSION,
    REGISTER_UPTIME,
    DEVICE_TYPE_NAMES,
    REG_STATUS_VALID,
    REG_STATUS_NOT_INITIALIZED,
    REG_STATUS_NOT_SUPPORTED,
    REG_STATUS_READ_WRITE_ERROR,
    CMD_RESULT_SUCCESS,
    CMD_RESULT_NO_COMMAND,
    CMD_RESULT_PROCESSING,
    CMD_RESULT_TIMEOUT,
    CMD_RESULT_NOT_SUPPORTED_ADAPTER,
    CMD_RESULT_NOT_SUPPORTED_BOILER,
    CMD_RESULT_EXECUTION_ERROR,
)

_LOGGER = logging.getLogger(__name__)


class BoilerGateway:
    """High-level adapter for a single boiler slave.

    The gateway holds a `cache` dict populated by the coordinator. Values
    are raw 16-bit register integers as returned by `modbus-tk`.
    """

    def __init__(self, protocol, slave_id: int):
        self.protocol = protocol
        self.slave_id = slave_id
        self.cache: Dict[int, int] = {}

        # Generic device info (populated by read_device_info())
        self.device_uid: Optional[int] = None      # 24-bit UID (0x800000-0xFFFFFF)
        self.device_type: Optional[int] = None     # Device type code
        self.channel_count: Optional[int] = None   # Number of channels (1-10)

        # Shared cache for CH setpoint to keep climate and number entities in sync
        self._ch_setpoint_cache: Optional[float] = None

    # ---------- GENERIC DEVICE INFO (read once at setup) ----------

    async def read_device_info(self) -> bool:
        """Read generic device information from registers 0x0000-0x0003.

        Should be called once during setup. Populates device_uid, device_type,
        and channel_count attributes.

        Returns True if successful, False otherwise.
        """
        regs = await self.protocol.read_registers(self.slave_id, 0x0000, 4)
        if regs is None or len(regs) < 4:
            _LOGGER.warning("Failed to read device info registers for slave_id=%s", self.slave_id)
            return False

        # Extract UID: 24-bit value from registers 0x0000-0x0001
        # Per Russian documentation MODBUS_PROTOCOL_RU.md:
        #   UID is 3 bytes in big-endian order across bytes 1-3 of the stream
        #   Register 0x0000: RSVD (MSB), UID MSB (LSB)
        #   Register 0x0001: UID middle (MSB), UID LSB (LSB)
        # Example: bytes 80 00 01 (big-endian) = UID 0x800001
        uid_byte_msb = regs[0] & 0xFF  # Register 0x0000 LSB = UID MSB
        uid_byte_mid = (regs[1] >> 8) & 0xFF  # Register 0x0001 MSB = UID middle
        uid_byte_lsb = regs[1] & 0xFF  # Register 0x0001 LSB = UID LSB
        
        # Combine as big-endian: MSB << 16 | middle << 8 | LSB
        self.device_uid = (uid_byte_msb << 16) | (uid_byte_mid << 8) | uid_byte_lsb

        # Extract device type (MSB of reg[3])
        self.device_type = (regs[3] >> 8) & 0xFF

        # Extract channel count (LSB of reg[3])
        self.channel_count = regs[3] & 0xFF

        _LOGGER.debug(
            "Device info for slave_id=%s: UID=0x%06X, type=0x%02X (%s), channels=%d",
            self.slave_id, self.device_uid, self.device_type,
            self.get_device_type_name() or "Unknown", self.channel_count
        )
        return True

    def get_device_uid_hex(self) -> Optional[str]:
        """Return device UID as hex string (e.g., '8a3f21')."""
        if self.device_uid is None:
            return None
        return f"{self.device_uid:06x}"

    def get_device_type_name(self) -> Optional[str]:
        """Return human-readable device type name."""
        if self.device_type is None:
            return None
        return DEVICE_TYPE_NAMES.get(self.device_type, f"Unknown (0x{self.device_type:02X})")

    # ---------- READ ACCESSORS (from cache) ----------

    def _get_reg(self, addr: int) -> Optional[int]:
        return self.cache.get(addr)

    def _get_register_status_description(self, status_code: int) -> str:
        """Return human-readable description of register status code."""
        descriptions = {
            REG_STATUS_VALID: "Data valid",
            REG_STATUS_NOT_INITIALIZED: "Not initialized",
            REG_STATUS_NOT_SUPPORTED: "Not supported by boiler",
            REG_STATUS_READ_WRITE_ERROR: "Read/write error",
        }
        return descriptions.get(status_code, f"Unknown status: {status_code}")

    def get_register_status(self, register_addr: int) -> Optional[int]:
        """Get status of a register from the status register range (0x0040-0x006F).

        Per Russian documentation, the status of register R is available at R + 0x30.
        For example, status of register 0x0018 is at 0x0048.

        Args:
            register_addr: The register address to check status for (0x0010-0x003F)

        Returns:
            Status code: 0=valid, 1=not initialized, -1=not supported, -2=error
            None if status register not available or outside valid range
        """
        # Status registers only available for 0x0010-0x003F
        if register_addr < 0x0010 or register_addr > 0x003F:
            _LOGGER.debug("Register 0x%04X outside status monitoring range (0x0010-0x003F)", register_addr)
            return None

        # Calculate status register address: R + 0x30
        status_addr = register_addr + 0x30

        # Read status register from cache
        status_raw = self._get_reg(status_addr)
        if status_raw is None:
            return None

        # Convert to signed i16
        if status_raw >= 0x8000:
            status_raw = status_raw - 0x10000

        return status_raw

    def is_register_valid(self, register_addr: int) -> bool:
        """Check if a register has valid data (status = 0).

        Returns True if status is REG_STATUS_VALID (0), False otherwise.
        Returns True if status register not available (fallback to assume valid).
        """
        status = self.get_register_status(register_addr)
        if status is None:
            # Status register not available, assume data is valid
            return True
        return status == REG_STATUS_VALID

    def get_adapter_uptime(self) -> Optional[int]:
        """Get adapter uptime in seconds from registers 0x0012 (high) and 0x0013 (low)."""
        high = self._get_reg(REGISTER_UPTIME)
        if high is None:
            return None
        low = self._get_reg(0x0013)
        if low is None:
            return None
        # Combine 32-bit value: high word at 0x0012, low word at 0x0013
        uptime_seconds = (high << 16) | low
        # Check for invalid marker (0xFFFFFFFF)
        if uptime_seconds == 0xFFFFFFFF:
            _LOGGER.debug("Uptime registers contain invalid marker 0xFFFFFFFF")
            return None

        # Log the raw uptime value for debugging
        if uptime_seconds == 0:
            _LOGGER.debug("Adapter uptime is 0 seconds (device just started)")
        elif uptime_seconds < 60:
            _LOGGER.debug("Adapter uptime: %d seconds", uptime_seconds)

        return uptime_seconds

    def get_adapter_uptime_formatted(self) -> str:
        """Get adapter uptime as human-readable string (e.g., '2d 5h 30m').

        Returns:
            Formatted uptime string, or '0m' if unavailable.
        """
        seconds = self.get_adapter_uptime()
        if seconds is None:
            return "0m"

        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0 or (days == 0 and hours == 0):
            parts.append(f"{minutes}m")

        return " ".join(parts)

    def get_ch_temperature(self) -> Optional[float]:
        # Check register status if available
        status = self.get_register_status(REGISTER_CH_TEMP)
        if status is not None:
            if status == REG_STATUS_NOT_SUPPORTED:
                _LOGGER.warning("CH temperature (0x0018) not supported by boiler")
                return None
            elif status == REG_STATUS_READ_WRITE_ERROR:
                _LOGGER.error("Read error for CH temperature (0x0018)")
                return None
            elif status == REG_STATUS_NOT_INITIALIZED:
                _LOGGER.debug("CH temperature (0x0018) not yet initialized")
                return None

        raw = self._get_reg(REGISTER_CH_TEMP)
        if raw is None or raw == 0x7FFF:
            return None
        # i16 scaled by 10
        # modbus-tk returns unsigned 16-bit; interpret signed
        if raw >= 0x8000:
            raw = raw - 0x10000
        return raw / 10.0

    def get_dhw_temperature(self) -> Optional[float]:
        # Check register status if available
        status = self.get_register_status(REGISTER_DHW_TEMP)
        if status is not None:
            if status == REG_STATUS_NOT_SUPPORTED:
                _LOGGER.warning("DHW temperature (0x0019) not supported by boiler")
                return None
            elif status == REG_STATUS_READ_WRITE_ERROR:
                _LOGGER.error("Read error for DHW temperature (0x0019)")
                return None
            elif status == REG_STATUS_NOT_INITIALIZED:
                _LOGGER.debug("DHW temperature (0x0019) not yet initialized")
                return None

        raw = self._get_reg(REGISTER_DHW_TEMP)
        if raw is None or raw == 0x7FFF:
            return None
        return raw / 10.0

    def get_pressure(self) -> Optional[float]:
        # Check register status if available
        status = self.get_register_status(REGISTER_PRESSURE)
        if status is not None:
            if status == REG_STATUS_NOT_SUPPORTED:
                _LOGGER.warning("Pressure (0x001A) not supported by boiler")
                return None
            elif status == REG_STATUS_READ_WRITE_ERROR:
                _LOGGER.error("Read error for pressure (0x001A)")
                return None
            elif status == REG_STATUS_NOT_INITIALIZED:
                _LOGGER.debug("Pressure (0x001A) not yet initialized")
                return None

        raw = self._get_reg(REGISTER_PRESSURE)
        if raw is None:
            return None
        lsb = raw & 0xFF
        if lsb == 0xFF:
            return None
        return lsb / 10.0

    def get_flow_rate(self) -> Optional[float]:
        # Check register status if available
        status = self.get_register_status(REGISTER_FLOW)
        if status is not None:
            if status == REG_STATUS_NOT_SUPPORTED:
                _LOGGER.warning("Flow rate (0x001B) not supported by boiler")
                return None
            elif status == REG_STATUS_READ_WRITE_ERROR:
                _LOGGER.error("Read error for flow rate (0x001B)")
                return None
            elif status == REG_STATUS_NOT_INITIALIZED:
                _LOGGER.debug("Flow rate (0x001B) not yet initialized")
                return None

        raw = self._get_reg(REGISTER_FLOW)
        if raw is None:
            return None
        lsb = raw & 0xFF
        if lsb == 0xFF:
            return None
        return lsb / 10.0

    def get_modulation_level(self) -> Optional[int]:
        # Check register status if available
        status = self.get_register_status(REGISTER_MODULATION)
        if status is not None:
            if status == REG_STATUS_NOT_SUPPORTED:
                _LOGGER.warning("Modulation level (0x001C) not supported by boiler")
                return None
            elif status == REG_STATUS_READ_WRITE_ERROR:
                _LOGGER.error("Read error for modulation level (0x001C)")
                return None
            elif status == REG_STATUS_NOT_INITIALIZED:
                _LOGGER.debug("Modulation level (0x001C) not yet initialized")
                return None

        raw = self._get_reg(REGISTER_MODULATION)
        if raw is None:
            return None
        lsb = raw & 0xFF
        return None if lsb == 0xFF else lsb

    def get_burner_on(self) -> Optional[bool]:
        raw = self._get_reg(REGISTER_STATES)
        if raw is None:
            return None
        lsb = raw & 0xFF
        return bool(lsb & 0x01)

    def get_heating_enabled(self) -> Optional[bool]:
        raw = self._get_reg(REGISTER_STATES)
        if raw is None:
            return None
        lsb = raw & 0xFF
        return bool((lsb >> 1) & 0x01)

    def get_dhw_enabled(self) -> Optional[bool]:
        raw = self._get_reg(REGISTER_STATES)
        if raw is None:
            return None
        lsb = raw & 0xFF
        return bool((lsb >> 2) & 0x01)

    def get_main_error(self) -> Optional[int]:
        raw = self._get_reg(REGISTER_MAIN_ERROR)
        if raw is None or raw == 0xFFFF:
            return None
        return raw

    def get_additional_error(self) -> Optional[int]:
        raw = self._get_reg(REGISTER_ADD_ERROR)
        if raw is None or raw == 0xFFFF:
            return None
        return raw

    def get_outdoor_temperature(self) -> Optional[int]:
        # Check register status if available
        status = self.get_register_status(REGISTER_OUTDOOR_TEMP)
        if status is not None:
            if status == REG_STATUS_NOT_SUPPORTED:
                _LOGGER.warning("Outdoor temperature (0x0020) not supported by boiler")
                return None
            elif status == REG_STATUS_READ_WRITE_ERROR:
                _LOGGER.error("Read error for outdoor temperature (0x0020)")
                return None
            elif status == REG_STATUS_NOT_INITIALIZED:
                _LOGGER.debug("Outdoor temperature (0x0020) not yet initialized")
                return None

        raw = self._get_reg(REGISTER_OUTDOOR_TEMP)
        if raw is None:
            return None
        msb = (raw >> 8) & 0xFF
        if msb == 0x7F:
            return None
        # signed i8
        if msb >= 0x80:
            msb = msb - 0x100
        return msb

    def get_manufacturer_code(self) -> Optional[int]:
        raw = self._get_reg(REGISTER_MFG_CODE)
        if raw is None or raw == 0xFFFF:
            return None
        return raw

    def get_model_code(self) -> Optional[int]:
        raw = self._get_reg(REGISTER_MODEL_CODE)
        if raw is None or raw == 0xFFFF:
            return None
        return raw

    def get_ot_error(self) -> Optional[int]:
        """Get OpenTherm error flags from register 0x0023 (s8).

        Only relevant for OpenTherm adapter types. For other adapter types
        (eBus, Navien), this register is not used and returns None.

        Returns:
            OpenTherm error flags as signed i8, or None if:
            - Register not available
            - Invalid marker (0x7F)
            - Adapter type is not OpenTherm
        """
        # Only applicable to OpenTherm adapters
        adapter_type = self.get_adapter_type()
        if adapter_type is None or adapter_type != 0x00:
            # Not an OpenTherm adapter
            return None

        raw = self._get_reg(REGISTER_OT_ERROR)
        if raw is None:
            return None

        # Extract signed i8 from MSB
        msb = (raw >> 8) & 0xFF
        if msb == 0x7F:
            # Invalid marker
            return None

        # Convert to signed i8
        if msb >= 0x80:
            msb = msb - 0x100
        return msb

    def get_hw_version(self) -> Optional[int]:
        """Extract hardware version from REGISTER_VERSION (0x0011 MSB)."""
        raw = self._get_reg(REGISTER_VERSION)
        if raw is None:
            return None
        msb = (raw >> 8) & 0xFF
        return None if msb == 0xFF else msb

    def get_sw_version(self) -> Optional[int]:
        """Extract software version from REGISTER_VERSION (0x0011 LSB)."""
        raw = self._get_reg(REGISTER_VERSION)
        if raw is None:
            return None
        lsb = raw & 0xFF
        return None if lsb == 0xFF else lsb

    def get_adapter_type(self) -> Optional[int]:
        """Extract adapter type from REGISTER_STATUS (0x0010 bits 0-2).

        Returns:
            0x00 = OpenTherm
            0x01 = eBus
            0x02 = Navien
            0x03-0x07 = Reserved
        """
        raw = self._get_reg(REGISTER_STATUS)
        if raw is None:
            return None
        adapter_type = (raw >> 0) & 0x07  # bits 0-2

        # Log for debugging
        _LOGGER.debug(
            "REGISTER_STATUS (0x0010) raw=0x%04X, adapter_type=0x%02X (%s)",
            raw, adapter_type, self._get_adapter_type_name_from_code(adapter_type)
        )

        return adapter_type

    def _get_adapter_type_name_from_code(self, code: int) -> str:
        """Helper to get adapter type name from code without import."""
        from .const import ADAPTER_TYPE_NAMES
        return ADAPTER_TYPE_NAMES.get(code, f"Unknown (0x{code:02X})")

    def get_adapter_type_name(self) -> Optional[str]:
        """Return human-readable adapter type name (e.g. 'OpenTherm', 'eBus', 'Navien')."""
        val = self.get_adapter_type()
        if val is None:
            return None
        return self._get_adapter_type_name_from_code(val)

    def get_is_boiler_connected(self) -> Optional[bool]:
        """Check bit 3 of REGISTER_STATUS (0x0010).

        Per Russian documentation (verified correct):
        - Bit 3 = 0: No response from boiler (disconnected/error)
        - Bit 3 = 1: Response received from boiler (connected/OK)

        Note: English documentation has this inverted, but Russian docs are correct.

        Returns:
            True if boiler is connected (bit 3 = 1)
            False if boiler not responding (bit 3 = 0)
            None if register not available
        """
        raw = self._get_reg(REGISTER_STATUS)
        if raw is None:
            return None

        # Extract bit 3
        comm_bit = (raw >> 3) & 0x01

        # Log connection status
        _LOGGER.debug(
            "REGISTER_STATUS (0x0010) raw=0x%04X, comm_bit=0x%X (%s)",
            raw,
            comm_bit,
            "Connected" if comm_bit == 1 else "Not responding"
        )

        # Russian docs (verified correct): bit 3 = 1 means response received (connected)
        return bool(comm_bit)

    def get_device_info(self) -> "DeviceInfo":
        """Return Home Assistant DeviceInfo structure for this gateway."""
        from homeassistant.helpers.device_registry import DeviceInfo
        from .const import DOMAIN

        # UID MUST be available (Ectocontrol adapters always have a UID)
        if not self.device_uid:
            _LOGGER.error("Device UID not available, cannot create DeviceInfo")
            # Fallback to port:slave_id for error reporting only
            identifier = f"{self.protocol.port}:{self.slave_id}"
        else:
            identifier = f"uid_{self.get_device_uid_hex()}"

        # Model name from device type (e.g., "OpenTherm Adapter v2", "eBus Adapter")
        # The device type already indicates the boiler protocol, no need to add adapter_type
        model = self.get_device_type_name() or "Ectocontrol Adapter"

        # Versions
        sw_ver = self.get_sw_version()
        hw_ver = self.get_hw_version()
        sw_v_str = str(sw_ver) if sw_ver is not None else None
        hw_v_str = str(hw_ver) if hw_ver is not None else None

        return DeviceInfo(
            identifiers={(DOMAIN, identifier)},
            name=f"Ectocontrol {model}",
            manufacturer="Ectostroy",
            model=model,
            sw_version=sw_v_str,
            hw_version=hw_v_str,
        )

    def get_ch_setpoint_active(self) -> Optional[float]:
        # Check register status if available
        status = self.get_register_status(REGISTER_CH_SETPOINT_ACTIVE)
        if status is not None:
            if status == REG_STATUS_NOT_SUPPORTED:
                _LOGGER.warning("CH setpoint active (0x0026) not supported by boiler")
                return None
            elif status == REG_STATUS_READ_WRITE_ERROR:
                _LOGGER.error("Read error for CH setpoint active (0x0026)")
                return None
            elif status == REG_STATUS_NOT_INITIALIZED:
                _LOGGER.debug("CH setpoint active (0x0026) not yet initialized")
                return None

        raw = self._get_reg(REGISTER_CH_SETPOINT_ACTIVE)
        if raw is None or raw == 0x7FFF:
            return None
        # step = 1/256 degC
        # treat as signed i16
        if raw >= 0x8000:
            raw = raw - 0x10000
        return raw / 256.0

    def get_ch_setpoint(self) -> Optional[float]:
        """Get CH setpoint from register 0x0031 (scaled by 10).

        Returns cached value if register is unavailable, to keep climate
        and number entities in sync.
        """
        # Check register status if available
        status = self.get_register_status(REGISTER_CH_SETPOINT)
        if status is not None:
            if status == REG_STATUS_NOT_SUPPORTED:
                _LOGGER.warning("CH setpoint (0x0031) not supported by boiler")
                return self._ch_setpoint_cache
            elif status == REG_STATUS_READ_WRITE_ERROR:
                _LOGGER.error("Read error for CH setpoint (0x0031)")
                return self._ch_setpoint_cache
            elif status == REG_STATUS_NOT_INITIALIZED:
                _LOGGER.debug("CH setpoint (0x0031) not yet initialized")
                return self._ch_setpoint_cache

        raw = self._get_reg(REGISTER_CH_SETPOINT)
        if raw is None or raw == 0x7FFF:
            # Return cached value if register unavailable
            return self._ch_setpoint_cache

        # i16 scaled by 10
        if raw >= 0x8000:
            raw = raw - 0x10000
        value = raw / 10.0

        # Update cache when we have a valid value from the register
        self._ch_setpoint_cache = value
        return value

    # ---------- WRITE HELPERS ----------

    def get_ch_min_limit(self) -> Optional[float]:
        """Get CH minimum temperature limit from register 0x0033 (u8, °C)."""
        raw = self._get_reg(REGISTER_CH_MIN)
        if raw is None:
            return None
        msb = (raw >> 8) & 0xFF
        return None if msb == 0xFF else float(msb)

    def get_ch_max_limit(self) -> Optional[float]:
        """Get CH maximum temperature limit from register 0x0034 (u8, °C)."""
        raw = self._get_reg(REGISTER_CH_MAX)
        if raw is None:
            return None
        msb = (raw >> 8) & 0xFF
        return None if msb == 0xFF else float(msb)

    def get_dhw_min_limit(self) -> Optional[float]:
        """Get DHW minimum temperature limit from register 0x0035 (u8, °C)."""
        raw = self._get_reg(REGISTER_DHW_MIN)
        if raw is None:
            return None
        msb = (raw >> 8) & 0xFF
        return None if msb == 0xFF else float(msb)

    def get_dhw_max_limit(self) -> Optional[float]:
        """Get DHW maximum temperature limit from register 0x0036 (u8, °C)."""
        raw = self._get_reg(REGISTER_DHW_MAX)
        if raw is None:
            return None
        msb = (raw >> 8) & 0xFF
        return None if msb == 0xFF else float(msb)

    def get_dhw_setpoint(self) -> Optional[float]:
        """Get DHW setpoint from register 0x0037 (u8, °C)."""
        raw = self._get_reg(REGISTER_DHW_SETPOINT)
        if raw is None:
            return None
        msb = (raw >> 8) & 0xFF
        return None if msb == 0xFF else float(msb)

    async def set_ch_setpoint(self, value_raw: int) -> bool:
        """Set CH setpoint.

        Updates the shared cache to keep climate and number entities in sync.
        """
        # Convert raw to temperature for caching
        temp_value = value_raw / 10.0
        self._ch_setpoint_cache = temp_value

        return await self.protocol.write_register(
            self.slave_id, REGISTER_CH_SETPOINT, value_raw
        )

    async def set_dhw_setpoint(self, value: int) -> bool:
        """Set DHW setpoint."""
        return await self.protocol.write_register(
            self.slave_id, REGISTER_DHW_SETPOINT, value
        )

    async def set_max_modulation(self, value: int) -> bool:
        """Set max modulation level (0-100%)."""
        return await self.protocol.write_register(self.slave_id, REGISTER_MAX_MODULATION, value)

    async def set_circuit_enable_bit(self, bit: int, enabled: bool) -> bool:
        """Set a specific bit in the circuit enable register (0x0039).

        Uses the cached value (updated by coordinator) and updates only the
        specified bit to avoid disturbing other bits in the register.
        """
        # Use cached value from coordinator's last poll
        current = self.cache.get(REGISTER_CIRCUIT_ENABLE, 0)

        if enabled:
            newv = current | (1 << bit)
        else:
            newv = current & ~(1 << bit)

        _LOGGER.debug("Circuit enable write: bit=%d enabled=%s current=0x%04X new=0x%04X",
                     bit, enabled, current, newv)

        result = await self.protocol.write_register(
            self.slave_id,
            REGISTER_CIRCUIT_ENABLE,
            newv
        )
        if not result:
            _LOGGER.error("Failed to write circuit enable register 0x0039, value: 0x%04X", newv)
        else:
            # Update cache immediately to provide optimistic update
            self.cache[REGISTER_CIRCUIT_ENABLE] = newv
        return result

    def get_heating_enable_switch(self) -> Optional[bool]:
        """Read heating enable switch state from circuit enable register (0x0039 bit 0)."""
        raw = self._get_reg(REGISTER_CIRCUIT_ENABLE)
        if raw is None:
            return None
        return bool(raw & 0x01)

    def get_dhw_enable_switch(self) -> Optional[bool]:
        """Read DHW enable switch state from circuit enable register (0x0039 bit 1)."""
        raw = self._get_reg(REGISTER_CIRCUIT_ENABLE)
        if raw is None:
            return None
        return bool((raw >> 1) & 0x01)

    def _get_command_result_description(self, result_code: int) -> str:
        """Return human-readable description of command result code."""
        descriptions = {
            CMD_RESULT_SUCCESS: "Command executed successfully",
            CMD_RESULT_NO_COMMAND: "No command (default)",
            CMD_RESULT_PROCESSING: "Command processing in progress",
            CMD_RESULT_TIMEOUT: "No response received (timeout)",
            CMD_RESULT_NOT_SUPPORTED_ADAPTER: "Command not supported by adapter",
            CMD_RESULT_NOT_SUPPORTED_BOILER: "Device ID not supported by boiler",
            CMD_RESULT_EXECUTION_ERROR: "Command execution error",
        }
        return descriptions.get(result_code, f"Unknown result code: {result_code}")

    async def _read_command_result(self) -> Optional[int]:
        """Read command result register (0x0081).

        Returns the raw i16 value or None if read fails.
        """
        result = await self.protocol.read_registers(
            self.slave_id,
            REGISTER_COMMAND_RESULT,
            1
        )
        if result is None or len(result) == 0:
            return None

        raw = result[0]
        # Convert to signed i16
        if raw >= 0x8000:
            raw = raw - 0x10000
        return raw

    async def reboot_adapter(self) -> bool:
        """Send reboot command (2) to command register 0x0080.

        After sending command, reads result register to verify success.
        Returns True if command was sent successfully (not necessarily executed).
        """
        _LOGGER.debug("Sending reboot command (2) to slave_id=%s register=0x%04X",
                      self.slave_id, REGISTER_COMMAND)
        result = await self.protocol.write_register(
            self.slave_id,
            REGISTER_COMMAND,
            2,
        )
        if not result:
            _LOGGER.error("Failed to send reboot command to slave_id=%s", self.slave_id)
            return False

        _LOGGER.debug("Reboot command sent successfully to slave_id=%s", self.slave_id)

        # Wait briefly for command to process
        await asyncio.sleep(0.5)

        # Read command result
        result_code = await self._read_command_result()
        if result_code is not None:
            _LOGGER.info(
                "Reboot command result for slave_id=%s: %d (%s)",
                self.slave_id,
                result_code,
                self._get_command_result_description(result_code)
            )
        else:
            _LOGGER.warning("Could not read reboot command result for slave_id=%s", self.slave_id)

        return True

    async def reset_boiler_errors(self) -> bool:
        """Send reset errors command (3) to command register 0x0080.

        After sending command, reads result register to verify success.
        Returns True if command was sent successfully (not necessarily executed).
        """
        _LOGGER.debug("Sending reset errors command (3) to slave_id=%s register=0x%04X",
                      self.slave_id, REGISTER_COMMAND)
        result = await self.protocol.write_register(
            self.slave_id,
            REGISTER_COMMAND,
            3,
        )
        if not result:
            _LOGGER.error("Failed to send reset errors command to slave_id=%s", self.slave_id)
            return False

        _LOGGER.debug("Reset errors command sent successfully to slave_id=%s", self.slave_id)

        # Wait briefly for command to process
        await asyncio.sleep(0.5)

        # Read command result
        result_code = await self._read_command_result()
        if result_code is not None:
            _LOGGER.info(
                "Reset errors command result for slave_id=%s: %d (%s)",
                self.slave_id,
                result_code,
                self._get_command_result_description(result_code)
            )
        else:
            _LOGGER.warning("Could not read reset errors command result for slave_id=%s", self.slave_id)

        return True
