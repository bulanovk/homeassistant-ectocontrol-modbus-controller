"""Contact Sensor Gateway for Ectocontrol Contact Sensor Splitter.

This module provides a gateway for the Ectocontrol 10-channel Contact Sensor Splitter
(device type 0x59), which monitors up to 10 dry contact inputs via Modbus RTU.

The gateway reads contact states from bitfield registers 0x0010-0x0011 and provides
methods to extract individual channel states.
"""
from __future__ import annotations

from typing import Dict, Optional, Union
import logging

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, DEVICE_TYPE_NAMES

_LOGGER = logging.getLogger(__name__)


class ContactSensorGateway:
    """Gateway for Ectocontrol Contact Sensor Splitter (device type 0x59).

    The Contact Sensor Splitter monitors up to 10 dry contact inputs and exposes
    their states via Modbus bitfield registers:
    - Register 0x0010: Channels 1-8 (bits 0-7)
    - Register 0x0011: Channels 9-10 (bits 0-2)

    Channel count is dynamically read from the device (1-10 channels supported).
    """

    def __init__(self, protocol, slave_id: int):
        """Initialize the Contact Sensor Gateway.

        Args:
            protocol: ModbusProtocol instance for communication
            slave_id: Modbus slave ID (1-32)
        """
        self.protocol = protocol
        self.slave_id = slave_id
        self.cache: Dict[int, int] = {}

        # Generic device info (populated by read_device_info)
        self.device_uid: Optional[int] = None      # 24-bit UID (0x800000-0xFFFFFF)
        self.device_type: Optional[int] = None     # Device type code (should be 0x59)
        self.channel_count: Optional[int] = None   # Number of channels (1-10)

    # ---------- GENERIC DEVICE INFO (read once at setup) ----------

    async def read_device_info(self) -> bool:
        """Read generic device information from registers 0x0000-0x0003.

        Populates:
            device_uid: 24-bit unique identifier (0x800000-0xFFFFFF)
            device_type: Device type code (should be 0x59 for Contact Splitter)
            channel_count: Number of channels (1-10, from LSB of 0x0003)

        Returns:
            True if device info was successfully read, False otherwise.
        """
        regs = await self.protocol.read_registers(self.slave_id, 0x0000, 4)
        if regs is None or len(regs) < 4:
            _LOGGER.warning(
                "Failed to read device info registers for slave_id=%s", self.slave_id
            )
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

        # Validate UID range
        if self.device_uid < 0x800000 or self.device_uid > 0xFFFFFF:
            _LOGGER.error(
                "Invalid UID 0x%06X for slave_id=%s (must be 0x800000-0xFFFFFF)",
                self.device_uid,
                self.slave_id
            )
            return False

        # Extract device type (MSB of reg[3]) and channel count (LSB of reg[3])
        self.device_type = (regs[3] >> 8) & 0xFF
        self.channel_count = regs[3] & 0xFF

        # Validate device type
        if self.device_type != 0x59:
            _LOGGER.warning(
                "Unexpected device type 0x%02X for slave_id=%s (expected 0x59 for Contact Splitter)",
                self.device_type,
                self.slave_id
            )

        # Validate channel count
        if self.channel_count < 1 or self.channel_count > 10:
            _LOGGER.error(
                "Invalid channel count %d for slave_id=%s (must be 1-10)",
                self.channel_count,
                self.slave_id
            )
            return False

        _LOGGER.info(
            "Contact Splitter device info for slave_id=%s: UID=0x%06X, channels=%d",
            self.slave_id,
            self.device_uid,
            self.channel_count
        )

        return True

    # ---------- HELPER METHODS ----------

    def get_channel_count(self) -> int:
        """Return the number of channels this device has.

        Dynamically read from device info, not hardcoded.

        Returns:
            Number of channels (1-10) if available, otherwise 0.
        """
        return self.channel_count if self.channel_count is not None else 0

    def get_device_uid_hex(self) -> Optional[str]:
        """Return device UID as hex string (e.g., '8abcdef').

        Returns:
            UID in lowercase hex format, or None if not available.
        """
        if self.device_uid is None:
            return None
        return f"{self.device_uid:06x}"

    def get_device_type_name(self) -> Optional[str]:
        """Return human-readable device type name.

        Returns:
            Device type name, or None if device_type not available.
        """
        if self.device_type is None:
            return None
        return DEVICE_TYPE_NAMES.get(
            self.device_type,
            f"Unknown (0x{self.device_type:02X})"
        )

    def get_manufacturer_code(self) -> Optional[int]:
        """Return manufacturer code (not applicable for contact sensors).

        Contact sensor devices don't have a manufacturer code like boiler adapters.
        This method returns None for consistency with the boiler gateway interface.
        """
        return None

    def get_model_code(self) -> Optional[int]:
        """Return model code (not applicable for contact sensors).

        Contact sensor devices don't have a model code like boiler adapters.
        This method returns None for consistency with the boiler gateway interface.
        """
        return None

    # ---------- BITFIELD ACCESS ----------

    def get_channel_bitfields(self) -> tuple[Optional[int], Optional[int]]:
        """Get the raw bitfield values from registers 0x0010 and 0x0011.

        The contact states are stored in bitfield registers:
        - Register 0x0010: Channels 1-8 (bits 0-7)
        - Register 0x0011: Channels 9-10 (bits 0-2)

        Returns:
            Tuple of (register_0x0010_value, register_0x0011_value)
            None for any register not available or read failed
        """
        reg_0x0010 = self.cache.get(0x0010)
        reg_0x0011 = self.cache.get(0x0011)
        return reg_0x0010, reg_0x0011

    def get_channel_state(self, channel: int) -> Optional[bool]:
        """Get contact state for a specific channel using bitfield extraction.

        Args:
            channel: Channel number (1-indexed, must be 1-10 and <= channel_count)

        Returns:
            True if contact is CLOSED (bit = 1)
            False if contact is OPEN (bit = 0)
            None if channel invalid, bitfield not available, or read failed

        Raises:
            ValueError: If channel number is out of range (must be 1-10)

        Bit Extraction Logic:
            Channels 1-8: Extract from register 0x0010
                Channel n = bit (n-1) of register 0x0010

            Channels 9-10: Extract from register 0x0011
                Channel 9 = bit 0 of register 0x0011
                Channel 10 = bit 1 of register 0x0011
        """
        # Validate channel number (must be 1-10)
        if channel < 1 or channel > 10:
            raise ValueError(
                f"Channel must be 1-10, got {channel}"
            )

        # Check against device's actual channel count
        if self.channel_count is not None and channel > self.channel_count:
            _LOGGER.debug(
                "Channel %d not available (device has %d channels)",
                channel,
                self.channel_count
            )
            return None

        # Get bitfields from cache
        reg_0x0010, reg_0x0011 = self.get_channel_bitfields()

        if channel <= 8:
            # Channels 1-8 are in register 0x0010
            if reg_0x0010 is None:
                _LOGGER.debug("Register 0x0010 not in cache")
                return None

            # Extract bit for this channel
            bit_position = channel - 1  # Channel 1 = bit 0, Channel 8 = bit 7
            is_closed = bool((reg_0x0010 >> bit_position) & 0x01)
            return is_closed
        else:
            # Channels 9-10 are in register 0x0011
            if reg_0x0011 is None:
                _LOGGER.debug("Register 0x0011 not in cache")
                return None

            # Extract bit for this channel
            bit_position = channel - 9  # Channel 9 = bit 0, Channel 10 = bit 1
            is_closed = bool((reg_0x0011 >> bit_position) & 0x01)
            return is_closed

    # ---------- DEVICE INFO ----------

    def get_device_info(self) -> DeviceInfo:
        """Return Home Assistant DeviceInfo structure for this gateway.

        Returns:
            DeviceInfo object with UID-based identifier.
        """
        # UID MUST be available (Ectocontrol adapters always have a UID)
        if not self.device_uid:
            _LOGGER.error("Device UID not available, cannot create DeviceInfo")
            # Fallback for error reporting only
            return DeviceInfo(
                identifiers={(DOMAIN, f"uid_unknown_{self.slave_id}")}
            )

        return DeviceInfo(
            identifiers={(DOMAIN, f"uid_{self.get_device_uid_hex()}")},
            name=f"Ectocontrol Contact Splitter {self.get_channel_count()}ch",
            manufacturer="Ectocontrol",
            model=self.get_device_type_name(),
            serial_number=self.get_device_uid_hex(),
        )
