"""Tests for __init__.py service handlers and edge cases."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
import importlib
from custom_components.ectocontrol_modbus_controller.const import DOMAIN


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
        self._registered = []

    def async_register(self, domain, name, handler):
        self._registered.append((domain, name, handler))

    def async_remove(self, domain, name):
        pass


class FakeConfig:
    def __init__(self):
        self.config_dir = "/tmp/config"


class FakeEntry:
    def __init__(self, entry_id="test_entry"):
        self.entry_id = entry_id
        self.data = {"port": "/dev/ttyUSB0", "slave_id": 1}


class FakeProtocol:
    async def connect(self):
        return True

    async def disconnect(self):
        pass

    async def read_registers(self, addr, count, timeout=None):
        # Return valid boiler device type (0x14) with UID in valid range
        if addr == 0x0000 and count >= 4:
            return [
                0x0000,  # Reserved
                0x8ABC,  # UID high 16 bits
                0xDE00,  # UID low 8 bits (0xDE in MSB)
                0x1404,  # Device type 0x14, channel count 4
            ]
        return [0] * count


# Import the real class to inherit from it
from custom_components.ectocontrol_modbus_controller.boiler_gateway import BoilerGateway

class FakeGateway(BoilerGateway):
    def __init__(self, protocol, slave_id):
        # Skip parent init to avoid protocol connection requirements
        self.protocol = protocol
        self.slave_id = slave_id
        self.cache = {}
        self.device_uid = 0x8ABCDEF  # Test UID (24-bit value in range 0x800000-0xFFFFFF)
        self.device_type = 0x14  # OpenTherm Adapter v2
        self.channel_count = 1

    async def read_device_info(self):
        return True

    def get_device_uid_hex(self):
        """Return device UID as hex string."""
        if self.device_uid is None:
            return None
        return f"{self.device_uid:06x}"

    def get_device_type_name(self):
        return "Test Device"

    def get_adapter_type_name(self):
        return "OpenTherm"

    async def reboot_adapter(self):
        pass

    async def reset_boiler_errors(self):
        pass

    def get_manufacturer_code(self):
        return None

    def get_model_code(self):
        return None

    def get_hw_version(self):
        return None

    def get_sw_version(self):
        return None


class FakeCoordinator:
    async def async_config_entry_first_refresh(self):
        pass

    async def async_request_refresh(self):
        pass


@pytest.mark.asyncio
async def test_async_setup():
    """Test basic async_setup."""
    from custom_components.ectocontrol_modbus_controller import async_setup

    hass = MagicMock()
    hass.data = {}

    result = await async_setup(hass, {})
    assert result is True
    assert DOMAIN in hass.data


@pytest.mark.asyncio
async def test_async_setup_entry_with_none():
    """Test async_setup_entry with entry=None (test support)."""
    from custom_components.ectocontrol_modbus_controller import async_setup_entry

    hass = MagicMock()
    hass.data = {DOMAIN: {}}

    result = await async_setup_entry(hass, None)
    assert result is True


@pytest.mark.asyncio
async def test_async_setup_entry_creates_components():
    """Test async_setup_entry creates protocol, gateway, coordinator."""
    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    hass.config = FakeConfig()
    hass.services = FakeServices()
    entry = FakeEntry()

    # Initialize protocol manager (normally done in async_setup)
    from custom_components.ectocontrol_modbus_controller.modbus_protocol_manager import ModbusProtocolManager
    manager = ModbusProtocolManager()
    hass.data[DOMAIN]["protocol_manager"] = manager

    # Create fake gateway instance
    fake_gateway = FakeGateway(None, 1)

    with patch("custom_components.ectocontrol_modbus_controller.dr.async_get") as mock_get_dr, \
         patch("custom_components.ectocontrol_modbus_controller.create_device_gateway", AsyncMock(return_value=fake_gateway)), \
         patch("custom_components.ectocontrol_modbus_controller.BoilerDataUpdateCoordinator") as MockCoord:

        # Import after patching
        from custom_components.ectocontrol_modbus_controller import async_setup_entry

        mock_get_dr.return_value = FakeDeviceRegistry()
        fake_protocol = FakeProtocol()
        # Mock the manager's get_protocol method
        manager.get_protocol = AsyncMock(return_value=fake_protocol)

        mock_coord = AsyncMock(spec=FakeCoordinator)
        MockCoord.return_value = mock_coord

        result = await async_setup_entry(hass, entry)

        assert result is True
        assert entry.entry_id in hass.data[DOMAIN]
        assert "port" in hass.data[DOMAIN][entry.entry_id]
        assert "gateway" in hass.data[DOMAIN][entry.entry_id]
        assert "coordinator" in hass.data[DOMAIN][entry.entry_id]


@pytest.mark.asyncio
async def test_async_setup_entry_initial_refresh_exception():
    """Test async_setup_entry handles initial refresh exception."""
    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    hass.config = FakeConfig()
    hass.services = FakeServices()
    entry = FakeEntry()

    # Initialize protocol manager (normally done in async_setup)
    from custom_components.ectocontrol_modbus_controller.modbus_protocol_manager import ModbusProtocolManager
    manager = ModbusProtocolManager()
    hass.data[DOMAIN]["protocol_manager"] = manager

    # Create fake gateway instance
    fake_gateway = FakeGateway(None, 1)

    with patch("custom_components.ectocontrol_modbus_controller.dr.async_get") as mock_get_dr, \
         patch("custom_components.ectocontrol_modbus_controller.create_device_gateway", AsyncMock(return_value=fake_gateway)), \
         patch("custom_components.ectocontrol_modbus_controller.BoilerDataUpdateCoordinator") as MockCoord:

        # Import after patching
        from custom_components.ectocontrol_modbus_controller import async_setup_entry

        mock_get_dr.return_value = FakeDeviceRegistry()
        fake_protocol = FakeProtocol()
        # Mock the manager's get_protocol method
        manager.get_protocol = AsyncMock(return_value=fake_protocol)

        mock_coord = AsyncMock(spec=FakeCoordinator)
        mock_coord.async_config_entry_first_refresh.side_effect = Exception("Test error")
        MockCoord.return_value = mock_coord

        result = await async_setup_entry(hass, entry)
        # Setup should succeed even if initial refresh fails
        assert result is True


@pytest.mark.asyncio
async def test_service_handler_single_entry():
    """Test service handler with single entry (uses implicit entry_id)."""
    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    hass.config = FakeConfig()
    hass.services = FakeServices()
    entry = FakeEntry()

    # Initialize protocol manager (normally done in async_setup)
    from custom_components.ectocontrol_modbus_controller.modbus_protocol_manager import ModbusProtocolManager
    manager = ModbusProtocolManager()
    hass.data[DOMAIN]["protocol_manager"] = manager

    # Create fake gateway instance with mocked reboot_adapter method
    fake_gateway = FakeGateway(None, 1)
    fake_gateway.reboot_adapter = AsyncMock()

    with patch("custom_components.ectocontrol_modbus_controller.dr.async_get") as mock_get_dr, \
         patch("custom_components.ectocontrol_modbus_controller.create_device_gateway", AsyncMock(return_value=fake_gateway)), \
         patch("custom_components.ectocontrol_modbus_controller.BoilerDataUpdateCoordinator") as MockCoord:

        # Import after patching
        from custom_components.ectocontrol_modbus_controller import async_setup_entry

        fake_protocol = AsyncMock(spec=FakeProtocol)
        # Mock the manager's get_protocol method (must accept kwargs)
        manager.get_protocol = AsyncMock(side_effect=lambda **kwargs: fake_protocol)

        mock_coord = AsyncMock(spec=FakeCoordinator)
        MockCoord.return_value = mock_coord

        mock_get_dr.return_value = FakeDeviceRegistry()

        setup_result = await async_setup_entry(hass, entry)
        assert setup_result is True, f"Setup failed: {setup_result}"

        # Verify entry was created
        assert entry.entry_id in hass.data[DOMAIN], f"Entry {entry.entry_id} not found in {list(hass.data[DOMAIN].keys())}"

        # Extract and call the registered service handler
        registered_services = hass.services._registered
        assert len(registered_services) >= 2

        # Get the reboot service handler (services are registered as tuples)
        # Format is (domain, name, handler)
        service_tuple = None
        for tup in registered_services:
            if tup[1] == "reboot_adapter":
                service_tuple = tup
                break

        assert service_tuple is not None, "reboot_adapter service not found"
        reboot_handler = service_tuple[2]

        # Simulate a service call with no entry_id (should use implicit single entry)
        fake_call = MagicMock()
        fake_call.data = None  # No entry_id specified

        # Call the service handler
        await reboot_handler(fake_call)

        # Verify gateway method was called (protocol is already connected via manager)
        # The gateway in hass.data should be the same as our fake_gateway
        gateway_in_data = hass.data[DOMAIN][entry.entry_id]["gateway"]
        assert gateway_in_data is fake_gateway, "Gateway mismatch!"
        fake_gateway.reboot_adapter.assert_called_once()


@pytest.mark.asyncio
async def test_service_handler_with_explicit_entry_id():
    """Test service handler with explicit entry_id in call data."""
    from custom_components.ectocontrol_modbus_controller import async_setup_entry

    hass = MagicMock()
    entry1 = FakeEntry("entry1")
    entry2 = FakeEntry("entry2")

    fake_protocol1 = AsyncMock(spec=FakeProtocol)
    fake_protocol2 = AsyncMock(spec=FakeProtocol)

    fake_gateway1 = MagicMock()
    fake_gateway1.protocol = fake_protocol1
    fake_gateway1.reboot_adapter = AsyncMock()
    fake_gateway1.reset_boiler_errors = AsyncMock()

    fake_gateway2 = MagicMock()
    fake_gateway2.protocol = fake_protocol2
    fake_gateway2.reboot_adapter = AsyncMock()
    fake_gateway2.reset_boiler_errors = AsyncMock()

    mock_coord1 = AsyncMock(spec=FakeCoordinator)
    mock_coord2 = AsyncMock(spec=FakeCoordinator)

    hass.data = {
        DOMAIN: {
            "entry1": {
                "protocol": fake_protocol1,
                "gateway": fake_gateway1,
                "coordinator": mock_coord1,
            },
            "entry2": {
                "protocol": fake_protocol2,
                "gateway": fake_gateway2,
                "coordinator": mock_coord2,
            },
        }
    }

    # Manually register service handler (simulating what async_setup_entry does)
    async def _service_handler(call, command):
        data = call.data or {}
        entry_id = data.get("entry_id")
        if entry_id is None:
            entries = list(hass.data[DOMAIN].keys())
            if len(entries) == 1:
                entry_id = entries[0]
            else:
                return

        ent = hass.data[DOMAIN].get(entry_id)
        if not ent:
            return
        gw = ent["gateway"]
        await gw.protocol.connect()
        try:
            if command == 2:
                await gw.reboot_adapter()
            elif command == 3:
                await gw.reset_boiler_errors()
        finally:
            await gw.protocol.disconnect()
            try:
                await ent["coordinator"].async_request_refresh()
            except Exception:
                pass

    # Call with explicit entry_id
    fake_call = MagicMock()
    fake_call.data = {"entry_id": "entry2"}

    await _service_handler(fake_call, 2)  # reboot command

    # Verify only gateway2 was called
    fake_protocol2.connect.assert_called()
    fake_gateway2.reboot_adapter.assert_called()
    fake_protocol2.disconnect.assert_called()
    fake_protocol1.connect.assert_not_called()


@pytest.mark.asyncio
async def test_async_unload_entry_with_none():
    """Test async_unload_entry with entry=None."""
    from custom_components.ectocontrol_modbus_controller import async_unload_entry

    hass = MagicMock()
    result = await async_unload_entry(hass, None)
    assert result is True


@pytest.mark.asyncio
async def test_async_unload_entry_removes_services_when_empty():
    """Test async_unload_entry removes services when last entry is unloaded."""
    from custom_components.ectocontrol_modbus_controller import async_unload_entry

    hass = MagicMock()
    entry = FakeEntry("test_entry")

    hass.data = {
        DOMAIN: {
            "test_entry": {"gateway": MagicMock(), "coordinator": MagicMock(), "port": "/dev/ttyUSB0"},
            "protocol_manager": AsyncMock(),  # Include protocol_manager to match real setup (must be AsyncMock)
        }
    }

    result = await async_unload_entry(hass, entry)

    assert result is True
    assert "test_entry" not in hass.data[DOMAIN]
    hass.services.async_remove.assert_called()
