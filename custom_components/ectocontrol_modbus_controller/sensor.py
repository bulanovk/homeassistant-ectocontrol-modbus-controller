"""Sensor platform for Ectocontrol Modbus Controller."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


SENSORS = [
    ("Adapter Uptime", "get_adapter_uptime_formatted", "text"),
    ("CH Temperature", "get_ch_temperature", "°C"),
    ("DHW Temperature", "get_dhw_temperature", "°C"),
    ("Pressure", "get_pressure", "bar"),
    ("Flow Rate", "get_flow_rate", "L/min"),
    ("Modulation", "get_modulation_level", "%"),
    ("Outdoor Temperature", "get_outdoor_temperature", "°C"),
    ("CH Setpoint Active", "get_ch_setpoint_active", "°C"),
    ("OT Error", "get_ot_error", ""),
    ("Main Error", "get_main_error", ""),
    ("Additional Error", "get_additional_error", ""),
]


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]

    entities = []
    for name, getter, unit in SENSORS:
        if unit == "text":
            # Text-based sensor (non-numeric value)
            entities.append(BoilerTextSensor(coordinator, getter, name))
        else:
            # Numeric sensor
            entities.append(BoilerSensor(coordinator, getter, name, unit))

    async_add_entities(entities)


class BoilerSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, getter_name: str, name: str, unit: str):
        super().__init__(coordinator)
        self._getter = getter_name
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit

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
    def native_value(self):
        value = getattr(self.coordinator.gateway, self._getter)()
        return value


class BoilerTextSensor(CoordinatorEntity, SensorEntity):
    """Sensor for text-based values (non-numeric)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, getter_name: str, name: str):
        super().__init__(coordinator)
        self._getter = getter_name
        self._attr_name = name
        # Don't set unit of measurement for text sensors
        self._attr_native_unit_of_measurement = None

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
    def native_value(self):
        value = getattr(self.coordinator.gateway, self._getter)()
        return value

