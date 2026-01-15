import pytest

from custom_components.ectocontrol_modbus_controller.diagnostics import async_get_config_entry_diagnostics
from custom_components.ectocontrol_modbus_controller.const import DOMAIN, CONF_PORT, CONF_SLAVE_ID


class FakeGateway:
    def __init__(self, slave_id, cache):
        self.slave_id = slave_id
        self.cache = cache


class FakeProtocol:
    def __init__(self, port, baudrate):
        self.port = port
        self.baudrate = baudrate


class FakeCoordinator:
    def __init__(self, name):
        self.name = name


class FakeEntry:
    def __init__(self, entry_id, title="Test Entry"):
        self.entry_id = entry_id
        self.title = title


class FakeHass:
    def __init__(self, data=None):
        self.data = data or {}


@pytest.mark.asyncio
async def test_diagnostics_entry_found():
    """Test diagnostics when entry and data are present."""
    gw = FakeGateway(slave_id=5, cache={0x0010: 100, 0x0020: 50})
    proto = FakeProtocol(port="/dev/ttyUSB0", baudrate=19200)
    coord = FakeCoordinator(name="test_coord")

    hass = FakeHass(
        {
            DOMAIN: {
                "entry1": {"gateway": gw, "protocol": proto, "coordinator": coord}
            }
        }
    )
    entry = FakeEntry("entry1")

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["slave_id"] == 5
    assert result["cache"] == {0x0010: 100, 0x0020: 50}
    assert result["protocol"]["port"] == "/dev/ttyUSB0"
    assert result["protocol"]["baudrate"] == 19200
    assert result["coordinator_name"] == "test_coord"


@pytest.mark.asyncio
async def test_diagnostics_entry_not_found():
    """Test diagnostics when entry is not found."""
    hass = FakeHass({})
    entry = FakeEntry("nonexistent")

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result == {"error": "entry_not_setup"}
