"""Tests for entity platform async_setup_entry functions."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from custom_components.ectocontrol_modbus_controller.const import DOMAIN


class FakeEntry:
    def __init__(self, entry_id="test_entry"):
        self.entry_id = entry_id


class FakeCoordinator:
    def __init__(self):
        self.gateway = MagicMock()
        self.name = "test_coordinator"


@pytest.mark.asyncio
async def test_sensor_async_setup_entry():
    """Test sensor platform async_setup_entry."""
    from custom_components.ectocontrol_modbus_controller.sensor import async_setup_entry as sensor_setup

    hass = MagicMock(spec=HomeAssistant)
    entry = FakeEntry()
    coordinator = FakeCoordinator()

    hass.data = {
        DOMAIN: {
            entry.entry_id: {
                "coordinator": coordinator,
            }
        }
    }

    entities_added = []

    def add_entities(entities):
        entities_added.extend(entities)

    await sensor_setup(hass, entry, add_entities)

    assert len(entities_added) == 11  # 11 sensors (including Adapter Uptime, OT Error, Main Error, Additional Error)
    assert all(hasattr(ent, "_attr_name") for ent in entities_added)


@pytest.mark.asyncio
async def test_binary_sensor_async_setup_entry():
    """Test binary_sensor platform async_setup_entry."""
    from custom_components.ectocontrol_modbus_controller.binary_sensor import async_setup_entry as binary_setup

    hass = MagicMock(spec=HomeAssistant)
    entry = FakeEntry()
    coordinator = FakeCoordinator()

    hass.data = {
        DOMAIN: {
            entry.entry_id: {
                "coordinator": coordinator,
            }
        }
    }

    entities_added = []

    def add_entities(entities):
        entities_added.extend(entities)

    await binary_setup(hass, entry, add_entities)

    assert len(entities_added) == 4  # 4 binary sensors (including Boiler Connection)
    assert all(hasattr(ent, "_attr_name") for ent in entities_added)


@pytest.mark.asyncio
async def test_number_async_setup_entry():
    """Test number platform async_setup_entry."""
    from custom_components.ectocontrol_modbus_controller.number import async_setup_entry as number_setup

    hass = MagicMock(spec=HomeAssistant)
    entry = FakeEntry()
    coordinator = FakeCoordinator()

    hass.data = {
        DOMAIN: {
            entry.entry_id: {
                "coordinator": coordinator,
            }
        }
    }

    entities_added = []

    def add_entities(entities):
        entities_added.extend(entities)

    await number_setup(hass, entry, add_entities)

    assert len(entities_added) == 3  # CH Min, CH Max, Max Modulation (DHW Setpoint removed - handled by DHW Climate entity)
    assert hasattr(entities_added[0], "async_set_native_value")


@pytest.mark.asyncio
async def test_switch_async_setup_entry():
    """Test switch platform async_setup_entry."""
    from custom_components.ectocontrol_modbus_controller.switch import async_setup_entry as switch_setup

    hass = MagicMock(spec=HomeAssistant)
    entry = FakeEntry()
    coordinator = FakeCoordinator()

    hass.data = {
        DOMAIN: {
            entry.entry_id: {
                "coordinator": coordinator,
            }
        }
    }

    entities_added = []

    def add_entities(entities):
        entities_added.extend(entities)

    await switch_setup(hass, entry, add_entities)

    assert len(entities_added) == 0  # All switches removed - Heating Enable handled by Boiler Climate, DHW Enable handled by DHW Climate
