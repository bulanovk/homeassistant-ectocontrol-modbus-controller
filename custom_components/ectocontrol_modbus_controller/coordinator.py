"""DataUpdateCoordinator for polling the boiler registers."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict, Optional

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, MODBUS_READ_TIMEOUT

_LOGGER = logging.getLogger(__name__)

# Register name mapping for debug output
_REGISTER_NAMES = {
    0x0010: "STATUS",
    0x0011: "VERSION",
    0x0012: "UPTIME_HIGH",
    0x0013: "UPTIME_LOW",
    0x0014: "RESERVED_14",
    0x0015: "RESERVED_15",
    0x0016: "RESERVED_16",
    0x0017: "RESERVED_17",
    0x0018: "CH_TEMP",
    0x0019: "DHW_TEMP",
    0x001A: "PRESSURE",
    0x001B: "FLOW",
    0x001C: "MODULATION",
    0x001D: "STATES",
    0x001E: "MAIN_ERROR",
    0x001F: "ADD_ERROR",
    0x0020: "OUTDOOR_TEMP",
    0x0021: "MFG_CODE",
    0x0022: "MODEL_CODE",
    0x0023: "OT_ERROR",
    0x0024: "RESERVED_24",
    0x0025: "RESERVED_25",
    0x0026: "CH_SETPOINT_ACTIVE",
}


class BoilerDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator that polls Modbus registers and updates the `BoilerGateway` cache."""

    def __init__(
        self,
        hass,
        gateway,
        name: str,
        update_interval: timedelta = DEFAULT_SCAN_INTERVAL,
        retry_count: int = 3,
        read_timeout: float = MODBUS_READ_TIMEOUT,
        config_entry: Optional[Any] = None,
        debug_modbus: bool = False,
    ):
        self.gateway = gateway
        self.name = name
        self.retry_count = retry_count
        self.read_timeout = read_timeout
        self.debug_modbus = debug_modbus
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=update_interval,
            config_entry=config_entry,
        )

    async def _async_update_data(self) -> Dict[int, int]:
        """Fetch data from Modbus and update gateway cache.

        Reads registers 0x0010..0x0026 in a single batch and also reads
        0x0039 (circuit enable) for switch state tracking.

        Implements configurable retry logic for transient failures.
        """
        last_error = None
        for attempt in range(self.retry_count + 1):
            try:
                # Start address 0x0010, count 23 (0x0010..0x0026)
                regs = await self.gateway.protocol.read_registers(
                    self.gateway.slave_id, 0x0010, 23, timeout=self.read_timeout
                )
                if regs is None:
                    raise UpdateFailed("No response from device")

                data = {}
                base = 0x0010
                for i, v in enumerate(regs):
                    data[base + i] = v

                # Also read circuit enable register (0x0039) for switch states
                circuit_enable = await self.gateway.protocol.read_registers(
                    self.gateway.slave_id, 0x0039, 1, timeout=self.read_timeout
                )
                if circuit_enable:
                    data[0x0039] = circuit_enable[0]

                # Update gateway cache
                self.gateway.cache = data

                # Debug log with register names (only if debug_modbus is enabled)
                if self.debug_modbus:
                    _LOGGER.debug(
                        "Received data: %s",
                        ", ".join(
                            f"{_REGISTER_NAMES.get(addr, f'0x{addr:04X}')}=0x{val:04X}({val})"
                            for addr, val in data.items()
                        )
                    )

                # Log retry recovery
                if attempt > 0:
                    _LOGGER.info("Recovered after %d retry attempts", attempt)

                return data

            except asyncio.TimeoutError as err:
                last_error = err
                if attempt < self.retry_count:
                    _LOGGER.warning(
                        "Timeout polling device (attempt %d/%d), retrying...",
                        attempt + 1,
                        self.retry_count + 1,
                    )
                    await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
                    continue
            except UpdateFailed:
                # Re-raise UpdateFailed immediately (already handled)
                raise
            except Exception as err:
                last_error = err
                if attempt < self.retry_count:
                    _LOGGER.warning(
                        "Error polling boiler (attempt %d/%d): %s, retrying...",
                        attempt + 1,
                        self.retry_count + 1,
                        err,
                    )
                    await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
                    continue

        # All retries exhausted
        _LOGGER.error("Unexpected error polling boiler after %d attempts: %s", self.retry_count + 1, last_error)
        raise UpdateFailed(f"Unexpected error: {last_error}")
