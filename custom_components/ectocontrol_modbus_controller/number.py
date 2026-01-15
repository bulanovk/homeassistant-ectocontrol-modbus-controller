"""Number platform for Ectocontrol Modbus Controller."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    # NOTE: DHW Setpoint is controlled by the DHW Climate entity
    async_add_entities(
        [
            CHMinMaxNumber(coordinator, "CH Min Limit", "ch_min", min_value=0, max_value=100),
            CHMinMaxNumber(coordinator, "CH Max Limit", "ch_max", min_value=0, max_value=100),
            MaxModulationNumber(coordinator),
        ]
    )


class CHMinMaxNumber(CoordinatorEntity, NumberEntity):
    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, name: str, key: str, min_value: int = 0, max_value: int = 100):
        super().__init__(coordinator)
        self._attr_name = name
        self._key = key
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._attr_native_step = 1

    @property
    def unique_id(self) -> str:
        gateway = self.coordinator.gateway
        # UID MUST be available for Ectocontrol adapters
        if not gateway.device_uid:
            raise ValueError("Device UID not available")
        identifier = f"uid_{gateway.get_device_uid_hex()}"
        return f"{DOMAIN}_{identifier}_{self._key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for entity association."""
        return self.coordinator.gateway.get_device_info()

    @property
    def native_value(self):
        # Map keys to gateway getters if present
        if self._key == "ch_min":
            return self.coordinator.gateway._get_reg(0x0033)
        if self._key == "ch_max":
            return self.coordinator.gateway._get_reg(0x0034)
        return None

    async def async_set_native_value(self, value: float) -> None:
        # write single-byte u8 values into full register (assume MSB storage)
        raw = int(value) & 0xFF
        addr = 0x0033 if self._key == "ch_min" else 0x0034
        await self.coordinator.gateway.protocol.write_register(self.coordinator.gateway.slave_id, addr, raw)
        await self.coordinator.async_request_refresh()


class MaxModulationNumber(CoordinatorEntity, NumberEntity):
    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Max Modulation"
        self._attr_native_min_value = 0
        self._attr_native_max_value = 100
        self._attr_native_step = 1

    @property
    def unique_id(self) -> str:
        gateway = self.coordinator.gateway
        # UID MUST be available for Ectocontrol adapters
        if not gateway.device_uid:
            raise ValueError("Device UID not available")
        identifier = f"uid_{gateway.get_device_uid_hex()}"
        return f"{DOMAIN}_{identifier}_max_modulation"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for entity association."""
        return self.coordinator.gateway.get_device_info()

    @property
    def native_value(self):
        # value stored in MSB of 16-bit register
        raw = self.coordinator.gateway._get_reg(0x0038)
        if raw is None:
            return None
        msb = (raw >> 8) & 0xFF
        return None if msb == 0xFF else msb

    async def async_set_native_value(self, value: float) -> None:
        raw = int(value) & 0xFF
        await self.coordinator.gateway.set_max_modulation(raw)
        await self.coordinator.async_request_refresh()
