import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from custom_components.ectocontrol_modbus_controller import async_setup_entry, async_unload_entry
from custom_components.ectocontrol_modbus_controller.const import DOMAIN, CONF_PORT, CONF_SLAVE_ID


class FakeDeviceEntry:
    def __init__(self):
        self.id = "test_device_id"


class FakeDeviceRegistry:
    def __init__(self):
        self._devices = {}

    def async_get_or_create(self, **kwargs):
        entry = FakeDeviceEntry()
        self._devices[entry.id] = entry
        return entry

    def async_get_device(self, identifiers=None, connections=None):
        return None

    def async_update_device(self, device_id, **kwargs):
        pass


class FakeServices:
    def __init__(self):
        self._registered = {}

    def async_register(self, domain, name, handler):
        self._registered[(domain, name)] = handler

    def async_remove(self, domain, name):
        self._registered.pop((domain, name), None)


class FakeConfig:
    def __init__(self):
        self.config_dir = "/tmp/config"


class FakeHass:
    def __init__(self):
        self.data = {}
        self.services = FakeServices()
        self.config = FakeConfig()


class DummyEntry:
    def __init__(self, entry_id, data):
        self.entry_id = entry_id
        self.data = data


@pytest.mark.asyncio
async def test_services_register_and_cleanup():
    import asyncio
    hass = FakeHass()
    entry = DummyEntry("e1", {CONF_PORT: "/dev/ttyUSB0", CONF_SLAVE_ID: 1})

    # Create a fake coordinator
    fake_coordinator = MagicMock()
    fake_coordinator.async_config_entry_first_refresh = AsyncMock()
    fake_coordinator.async_request_refresh = AsyncMock()

    # Initialize DOMAIN dict (normally done in async_setup)
    hass.data.setdefault(DOMAIN, {})
    
    # Initialize protocol manager (normally done in async_setup)
    from custom_components.ectocontrol_modbus_controller.modbus_protocol_manager import ModbusProtocolManager
    manager = ModbusProtocolManager()
    hass.data[DOMAIN]["protocol_manager"] = manager

    # Mock the device registry
    with patch("custom_components.ectocontrol_modbus_controller.dr.async_get") as mock_get_dr:
        mock_get_dr.return_value = FakeDeviceRegistry()

        # Mock the BoilerGateway
        with patch("custom_components.ectocontrol_modbus_controller.BoilerGateway") as mock_gateway_class, \
             patch("custom_components.ectocontrol_modbus_controller.BoilerDataUpdateCoordinator", return_value=fake_coordinator):
            mock_protocol = MagicMock()
            mock_protocol.connect = AsyncMock(return_value=True)
            mock_protocol.disconnect = AsyncMock(return_value=True)
            
            # Mock the manager's get_protocol and release_protocol methods
            manager.get_protocol = AsyncMock(return_value=mock_protocol)
            manager.release_protocol = AsyncMock(return_value=True)

            # Mock gateway with proper device_uid setup
            mock_gateway = MagicMock()
            mock_gateway.device_uid = 0x8ABCDEF  # Must have UID for setup to succeed
            mock_gateway.get_device_uid_hex = MagicMock(return_value="8abcdef")
            mock_gateway.read_device_info = AsyncMock(return_value=True)
            mock_gateway_class.return_value = mock_gateway

            ok = await async_setup_entry(hass, entry)
            assert ok is True
            # services should be registered
            assert (DOMAIN, "reboot_adapter") in hass.services._registered
            assert (DOMAIN, "reset_boiler_errors") in hass.services._registered

            # unload entry should remove services because it's the last entry
            ok2 = await async_unload_entry(hass, entry)
            assert ok2 is True
            assert (DOMAIN, "reboot_adapter") not in hass.services._registered
            assert (DOMAIN, "reset_boiler_errors") not in hass.services._registered
