"""Button platform for adapter commands (reboot, reset errors)."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    entities = [RebootAdapterButton(coordinator), ResetErrorsButton(coordinator)]
    async_add_entities(entities)


class RebootAdapterButton(CoordinatorEntity, ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Reboot Adapter"

    @property
    def unique_id(self) -> str:
        gateway = self.coordinator.gateway
        # UID MUST be available for Ectocontrol adapters
        if not gateway.device_uid:
            raise ValueError("Device UID not available")
        identifier = f"uid_{gateway.get_device_uid_hex()}"
        return f"{DOMAIN}_{identifier}_reboot"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for entity association."""
        return self.coordinator.gateway.get_device_info()

    async def async_press(self) -> None:
        _LOGGER.debug("Reboot Adapter button pressed for slave_id=%s",
                      self.coordinator.gateway.slave_id)
        await self.coordinator.gateway.reboot_adapter()
        await self.coordinator.async_request_refresh()


class ResetErrorsButton(CoordinatorEntity, ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Reset Boiler Errors"

    @property
    def unique_id(self) -> str:
        gateway = self.coordinator.gateway
        # UID MUST be available for Ectocontrol adapters
        if not gateway.device_uid:
            raise ValueError("Device UID not available")
        identifier = f"uid_{gateway.get_device_uid_hex()}"
        return f"{DOMAIN}_{identifier}_reset_errors"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for entity association."""
        return self.coordinator.gateway.get_device_info()

    async def async_press(self) -> None:
        _LOGGER.debug("Reset Boiler Errors button pressed for slave_id=%s",
                      self.coordinator.gateway.slave_id)
        await self.coordinator.gateway.reset_boiler_errors()
        await self.coordinator.async_request_refresh()
