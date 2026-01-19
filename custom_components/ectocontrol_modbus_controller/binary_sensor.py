"""Binary sensor platform for Ectocontrol Modbus Controller."""
from __future__ import annotations

import logging
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


# Binary sensors for BoilerGateway (OpenTherm/eBus/Navien adapters)
BOILER_BINARY_SENSORS = [
    ("Burner On", "get_burner_on"),
    ("Heating Enabled", "get_heating_enabled"),
    ("DHW Enabled", "get_dhw_enabled"),
    ("Boiler Connection", "get_is_boiler_connected"),
]


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback):
    from .boiler_gateway import BoilerGateway
    from .contact_gateway import ContactSensorGateway

    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    gateway = coordinator.gateway

    entities = []

    # BoilerGateway: create boiler state binary sensors
    if isinstance(gateway, BoilerGateway):
        for name, getter in BOILER_BINARY_SENSORS:
            entities.append(BoilerBinarySensor(coordinator, getter, name))

    # ContactSensorGateway: create contact channel binary sensors
    elif isinstance(gateway, ContactSensorGateway):
        channel_count = gateway.get_channel_count()

        _LOGGER.info(
            "Creating %d contact channel binary sensors for slave_id=%s (UID=%s)",
            channel_count,
            gateway.slave_id,
            gateway.get_device_uid_hex()
        )

        for channel in range(1, channel_count + 1):
            entities.append(ContactChannelBinarySensor(coordinator, channel))

    async_add_entities(entities)


class BoilerBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for boiler-specific states (Burner On, Heating Enabled, etc.)."""

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


class ContactChannelBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor entity for a single contact channel on Contact Sensor Splitter."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.OPENING

    def __init__(self, coordinator, channel: int):
        """Initialize the binary sensor entity.

        Args:
            coordinator: ContactSensorDataUpdateCoordinator instance
            channel: Channel number (1-indexed, 1-10)
        """
        super().__init__(coordinator)
        self._channel = channel
        self._attr_name = f"Channel {channel}"

    @property
    def unique_id(self) -> str:
        """Return unique ID for this entity.

        Format: {DOMAIN}_uid_{uid_hex}_channel_{channel}

        Example: ectocontrol_modbus_controller_uid_8abcdef_channel_1
        """
        gateway = self.coordinator.gateway

        # UID MUST be available for Ectocontrol adapters
        if not gateway.device_uid:
            raise ValueError("Device UID not available")

        uid_hex = gateway.get_device_uid_hex()
        return f"{DOMAIN}_uid_{uid_hex}_channel_{self._channel}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for entity association.

        All channel entities belong to the same device (the Contact Splitter).
        """
        return self.coordinator.gateway.get_device_info()

    @property
    def is_on(self) -> bool | None:
        """Return the current state of the contact.

        Returns:
            True if contact is CLOSED (circuit complete)
            False if contact is OPEN (circuit broken)
            None if state is not available
        """
        return self.coordinator.gateway.get_channel_state(self._channel)
