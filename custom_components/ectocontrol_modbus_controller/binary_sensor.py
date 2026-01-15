"""Binary sensor platform for Ectocontrol Modbus Controller."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


BINARY_SENSORS = [
    ("Burner On", "get_burner_on"),
    ("Heating Enabled", "get_heating_enabled"),
    ("DHW Enabled", "get_dhw_enabled"),
    ("Boiler Connection", "get_is_boiler_connected"),
]


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]

    entities = []
    for name, getter in BINARY_SENSORS:
        entities.append(BoilerBinarySensor(coordinator, getter, name))

    async_add_entities(entities)


class BoilerBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, getter_name: str, name: str):
        super().__init__(coordinator)
        self._getter = getter_name
        self._attr_name = name
        if getter_name == "get_is_boiler_connected":
            self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    @property
    def unique_id(self) -> str:
        gateway = self.coordinator.gateway
        # UID MUST be available for Ectocontrol adapters
        if not gateway.device_uid:
            raise ValueError("Device UID not available")
        identifier = f"uid_{gateway.get_device_uid_hex()}"
        return f"{DOMAIN}_{identifier}_{self._getter}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for entity association."""
        return self.coordinator.gateway.get_device_info()

    @property
    def is_on(self) -> bool | None:
        return getattr(self.coordinator.gateway, self._getter)()
