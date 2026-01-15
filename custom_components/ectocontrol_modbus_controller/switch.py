"""Switch platform for Ectocontrol Modbus Controller."""
from __future__ import annotations

import asyncio
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    # NOTE: Heating Enable (bit 0) is controlled by the Boiler Climate entity
    # NOTE: DHW Enable (bit 1) is controlled by the DHW Climate entity
    # Switches read/write from circuit enable register (0x0039)
    # Binary sensors read from states register (0x001D) for actual boiler status
    async_add_entities([])


class CircuitSwitch(CoordinatorEntity, SwitchEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, bit: int = 0, name: str | None = None,
                 state_getter: callable | None = None):
        super().__init__(coordinator)
        self._bit = bit
        self._attr_name = name or f"Circuit {bit}"
        self._state_getter = state_getter

    @property
    def unique_id(self) -> str:
        gateway = self.coordinator.gateway
        # UID MUST be available for Ectocontrol adapters
        if not gateway.device_uid:
            raise ValueError("Device UID not available")
        identifier = f"uid_{gateway.get_device_uid_hex()}"
        return f"{DOMAIN}_{identifier}_circuit_{self._bit}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for entity association."""
        return self.coordinator.gateway.get_device_info()

    @property
    def is_on(self) -> bool | None:
        if self._state_getter:
            return self._state_getter(self.coordinator.gateway)
        # fallback: read from cache directly
        states = self.coordinator.gateway.cache.get(0x001D)
        if states is None:
            return None
        lsb = states & 0xFF
        return bool(lsb & (1 << self._bit))

    async def async_turn_on(self, **kwargs) -> None:
        success = await self.coordinator.gateway.set_circuit_enable_bit(self._bit, True)
        if not success:
            _LOGGER.error("Failed to turn on circuit bit %d", self._bit)
            return
        # Small delay to allow device to process the write
        await asyncio.sleep(0.1)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        success = await self.coordinator.gateway.set_circuit_enable_bit(self._bit, False)
        if not success:
            _LOGGER.error("Failed to turn off circuit bit %d", self._bit)
            return
        # Small delay to allow device to process the write
        await asyncio.sleep(0.1)
        await self.coordinator.async_request_refresh()
