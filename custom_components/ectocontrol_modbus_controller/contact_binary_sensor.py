"""Binary sensor platform for Ectocontrol Contact Sensor Splitter.

This module provides binary sensor entities for each channel of the Contact
Sensor Splitter, representing the open/closed state of dry contact inputs.
"""
from __future__ import annotations

import logging
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback
):
    """Set up Contact Sensor Splitter binary sensor entities.

    Creates binary sensor entities dynamically based on the actual number of
    channels supported by the device (read from device info).

    Args:
        hass: Home Assistant instance
        entry: Config entry
        async_add_entities: Callback to add entities
    """
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    gateway = data["gateway"]

    # Verify this is a Contact Sensor Splitter
    from .contact_gateway import ContactSensorGateway
    if not isinstance(gateway, ContactSensorGateway):
        _LOGGER.warning("Not a Contact Sensor Splitter, skipping binary sensor setup")
        return

    # Create entities dynamically based on actual channel count
    entities = []
    channel_count = gateway.get_channel_count()

    _LOGGER.info(
        "Creating %d binary sensor entities for slave_id=%s (UID=%s)",
        channel_count,
        gateway.slave_id,
        gateway.get_device_uid_hex()
    )

    for channel in range(1, channel_count + 1):
        entity = ContactChannelBinarySensor(coordinator, channel)
        entities.append(entity)

    async_add_entities(entities)


class ContactChannelBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor entity for a single contact channel.

    Represents the open/closed state of a dry contact input on the Contact
    Sensor Splitter.

    Attributes:
        _attr_has_entity_name: True (uses device name prefix)
        _attr_device_class: BinarySensorDeviceClass.OPENING (for doors/windows)
    """

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
