"""Data update coordinator for Ectocontrol Contact Sensor Splitter.

This module provides a coordinator that polls the contact states from the Contact
Sensor Splitter and caches them for entity access.
"""
from __future__ import annotations

from typing import Dict
import asyncio
import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, MODBUS_RETRY_COUNT, MODBUS_READ_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class ContactSensorDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator for polling Contact Sensor Splitter states.

    The coordinator polls the bitfield registers (0x0010-0x0011) that contain
    the contact states for all channels. It dynamically adjusts the number
    of registers to read based on the device's channel count.

    Polling Strategy:
        - Devices with 1-8 channels: Read only register 0x0010 (1 register)
        - Devices with 9-10 channels: Read registers 0x0010-0x0011 (2 registers)
    """

    def __init__(
        self,
        hass: HomeAssistant,
        gateway,
        name: str,
        update_interval: timedelta = DEFAULT_SCAN_INTERVAL,
        retry_count: int = MODBUS_RETRY_COUNT,
        read_timeout: float = MODBUS_READ_TIMEOUT,
        config_entry = None,
    ):
        """Initialize the coordinator.

        Args:
            hass: Home Assistant instance
            gateway: ContactSensorGateway instance
            name: Coordinator name
            update_interval: Polling interval (default 15 seconds)
            retry_count: Number of retry attempts (default 3)
            read_timeout: Modbus read timeout in seconds (default 3.0)
            config_entry: Config entry (optional)
        """
        self.gateway = gateway
        self.retry_count = retry_count
        self.read_timeout = read_timeout
        self.config_entry = config_entry

        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=update_interval,
        )

        _LOGGER.info(
            "Contact Sensor coordinator initialized for slave_id=%s, interval=%s",
            gateway.slave_id,
            update_interval
        )

    async def _async_update_data(self) -> Dict[int, int]:
        """Poll contact states from the device.

        Reads the bitfield registers containing contact states:
        - Register 0x0010: Channels 1-8 (always read)
        - Register 0x0011: Channels 9-10 (read only if channel_count > 8)

        Returns:
            Dictionary mapping register addresses to values:
            - For ≤8 channels: {0x0010: value}
            - For >8 channels: {0x0010: value, 0x0011: value}

        Raises:
            UpdateFailed: If communication fails or data is invalid
        """
        channel_count = self.gateway.channel_count or 10

        if channel_count <= 8:
            # Only need register 0x0010 (channels 1-8)
            # NOTE: Contact sensor data is in INPUT registers, not holding registers
            _LOGGER.debug(
                "Reading contact states for slave_id=%s: 1 INPUT register (0x0010, %d channels)",
                self.gateway.slave_id,
                channel_count
            )

            regs = await self.gateway.protocol.read_input_registers(
                self.gateway.slave_id,
                0x0010,
                1
            )

            if regs is None or len(regs) == 0:
                _LOGGER.error("Failed to read INPUT register 0x0010")
                raise UpdateFailed("Failed to read contact states")

            # Update gateway cache
            cache_data = {0x0010: regs[0]}
            _LOGGER.debug(
                "Contact states for slave_id=%s: 0x0010=0x%04X",
                self.gateway.slave_id,
                regs[0]
            )
            return cache_data
        else:
            # Need both registers (channels 9-10 present)
            # NOTE: Contact sensor data is in INPUT registers, not holding registers
            _LOGGER.debug(
                "Reading contact states for slave_id=%s: 2 INPUT registers (0x0010-0x0011, %d channels)",
                self.gateway.slave_id,
                channel_count
            )

            regs = await self.gateway.protocol.read_input_registers(
                self.gateway.slave_id,
                0x0010,
                2
            )

            if regs is None or len(regs) < 2:
                _LOGGER.error("Failed to read INPUT registers 0x0010-0x0011")
                raise UpdateFailed("Failed to read contact states")

            # Update gateway cache
            cache_data = {0x0010: regs[0], 0x0011: regs[1]}
            _LOGGER.debug(
                "Contact states for slave_id=%s: 0x0010=0x%04X, 0x0011=0x%04X",
                self.gateway.slave_id,
                regs[0],
                regs[1]
            )
            return cache_data

    def is_channel_available(self, channel: int) -> bool:
        """Check if a channel has valid data available.

        Args:
            channel: Channel number (1-indexed)

        Returns:
            True if the channel's bitfield register is in cache and valid,
            False otherwise.
        """
        if self.gateway.channel_count is None:
            return False

        if channel < 1 or channel > self.gateway.channel_count:
            return False

        # Check if appropriate register is in cache
        if channel <= 8:
            return 0x0010 in self.gateway.cache
        else:
            return 0x0011 in self.gateway.cache
