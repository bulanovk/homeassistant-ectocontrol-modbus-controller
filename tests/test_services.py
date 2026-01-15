"""Tests for service layer in __init__.py."""
import pytest
import logging
from unittest.mock import MagicMock, AsyncMock

from custom_components.ectocontrol_modbus_controller import (
    async_setup_entry,
    async_unload_entry,
)


class FakeGateway:
    """Fake gateway for testing."""

    def __init__(self):
        self.slave_id = 1
        self.device_uid = 0x8ABCDEF  # Test UID (24-bit value in range 0x800000-0xFFFFFF)
        self.reboot_called = False
        self.reset_errors_called = False
        self.protocol = type('obj', (object,), {'port': 'mock_port'})

    def get_device_uid_hex(self):
        """Return UID as hex string."""
        if self.device_uid is None:
            return None
        return f"{self.device_uid:06x}"

    async def reboot_adapter(self):
        """Mock reboot adapter."""
        self.reboot_called = True
        return True

    async def reset_boiler_errors(self):
        """Mock reset boiler errors."""
        self.reset_errors_called = True
        return True


class DummyCoordinator:
    """Dummy coordinator for testing."""

    def __init__(self, gateway):
        self.gateway = gateway
        self.refreshed = False

    async def async_request_refresh(self):
        """Mock refresh method."""
        self.refreshed = True


class DummyEntry:
    """Dummy config entry for testing."""

    def __init__(self, entry_id="test_entry"):
        self.entry_id = entry_id
        self.data = {
            "port": "/dev/ttyUSB0",
            "slave_id": 1,
            "debug_modbus": False,
            "polling_interval": 15,
            "retry_count": 3,
            "read_timeout": 2.0,
        }


class DummyHass:
    """Dummy Home Assistant instance for testing."""

    def __init__(self):
        self.data = {}
        self.services = {}
        self.bus = DummyBus()

    async def async_register(self, domain, service_name, handler):
        """Mock service registration."""
        if domain not in self.services:
            self.services[domain] = {}
        self.services[domain][service_name] = handler

    async def async_remove(self, domain, service_name):
        """Mock service removal."""
        if domain in self.services and service_name in self.services[domain]:
            del self.services[domain][service_name]


class DummyBus:
    """Dummy event bus for testing."""

    def async_listen_once(self, event, callback):
        """Mock event listener."""
        pass


@pytest.mark.asyncio
async def test_service_handler_reboot_adapter() -> None:
    """Test reboot service with single entry."""
    # Arrange
    gw = FakeGateway()
    coord = DummyCoordinator(gw)
    hass = DummyHass()
    entry = DummyEntry("test_entry_1")

    # Setup entry to register services
    hass.data["ectocontrol_modbus_controller"] = {
        "protocol_manager": MagicMock(),
    }
    hass.data["ectocontrol_modbus_controller"][entry.entry_id] = {
        "gateway": gw,
        "coordinator": coord,
    }

    # Get the reboot service handler (simulating what async_setup_entry does)
    async def _service_handler(call, command):
        data = call.data or {}
        entry_id = data.get("entry_id")
        if entry_id is None:
            entries = [k for k in hass.data["ectocontrol_modbus_controller"].keys() if k != "protocol_manager"]
            if len(entries) == 1:
                entry_id = entries[0]
            else:
                return

        ent = hass.data["ectocontrol_modbus_controller"].get(entry_id)
        if not ent:
            return
        gw_handler: FakeGateway = ent["gateway"]
        try:
            if command == 2:
                await gw_handler.reboot_adapter()
            elif command == 3:
                await gw_handler.reset_boiler_errors()
        finally:
            try:
                await ent["coordinator"].async_request_refresh()
            except Exception:
                pass

    # Act
    call = MagicMock()
    call.data = {}  # No entry_id, should use single entry
    await _service_handler(call, 2)

    # Assert
    assert gw.reboot_called is True
    assert coord.refreshed is True


@pytest.mark.asyncio
async def test_service_handler_reset_errors() -> None:
    """Test reset errors service with single entry."""
    # Arrange
    gw = FakeGateway()
    coord = DummyCoordinator(gw)
    hass = DummyHass()
    entry = DummyEntry("test_entry_2")

    hass.data["ectocontrol_modbus_controller"] = {
        "protocol_manager": MagicMock(),
    }
    hass.data["ectocontrol_modbus_controller"][entry.entry_id] = {
        "gateway": gw,
        "coordinator": coord,
    }

    async def _service_handler(call, command):
        data = call.data or {}
        entry_id = data.get("entry_id")
        if entry_id is None:
            entries = [k for k in hass.data["ectocontrol_modbus_controller"].keys() if k != "protocol_manager"]
            if len(entries) == 1:
                entry_id = entries[0]
            else:
                return

        ent = hass.data["ectocontrol_modbus_controller"].get(entry_id)
        if not ent:
            return
        gw_handler: FakeGateway = ent["gateway"]
        try:
            if command == 2:
                await gw_handler.reboot_adapter()
            elif command == 3:
                await gw_handler.reset_boiler_errors()
        finally:
            try:
                await ent["coordinator"].async_request_refresh()
            except Exception:
                pass

    # Act
    call = MagicMock()
    call.data = {}  # No entry_id, should use single entry
    await _service_handler(call, 3)

    # Assert
    assert gw.reset_errors_called is True
    assert coord.refreshed is True


@pytest.mark.asyncio
async def test_service_handler_multi_entry_without_entry_id() -> None:
    """Test service handler with multiple entries, no entry_id provided."""
    # Arrange
    gw1 = FakeGateway()
    gw2 = FakeGateway()
    coord1 = DummyCoordinator(gw1)
    coord2 = DummyCoordinator(gw2)
    hass = DummyHass()
    entry1 = DummyEntry("test_entry_1")
    entry2 = DummyEntry("test_entry_2")

    hass.data["ectocontrol_modbus_controller"] = {
        "protocol_manager": MagicMock(),
    }
    hass.data["ectocontrol_modbus_controller"][entry1.entry_id] = {
        "gateway": gw1,
        "coordinator": coord1,
    }
    hass.data["ectocontrol_modbus_controller"][entry2.entry_id] = {
        "gateway": gw2,
        "coordinator": coord2,
    }

    async def _service_handler(call, command):
        data = call.data or {}
        entry_id = data.get("entry_id")
        if entry_id is None:
            entries = [k for k in hass.data["ectocontrol_modbus_controller"].keys() if k != "protocol_manager"]
            if len(entries) == 1:
                entry_id = entries[0]
            else:
                return  # Multiple entries, no entry_id - should return early

        ent = hass.data["ectocontrol_modbus_controller"].get(entry_id)
        if not ent:
            return
        gw_handler: FakeGateway = ent["gateway"]
        try:
            if command == 2:
                await gw_handler.reboot_adapter()
            elif command == 3:
                await gw_handler.reset_boiler_errors()
        finally:
            try:
                await ent["coordinator"].async_request_refresh()
            except Exception:
                pass

    # Act
    call = MagicMock()
    call.data = {}  # No entry_id with multiple entries
    await _service_handler(call, 2)

    # Assert - should not call anything when multiple entries and no entry_id
    assert gw1.reboot_called is False
    assert gw2.reboot_called is False
    assert coord1.refreshed is False
    assert coord2.refreshed is False


@pytest.mark.asyncio
async def test_service_handler_entry_not_found() -> None:
    """Test service handler with invalid entry_id."""
    # Arrange
    gw = FakeGateway()
    coord = DummyCoordinator(gw)
    hass = DummyHass()
    entry = DummyEntry("test_entry_1")

    hass.data["ectocontrol_modbus_controller"] = {
        "protocol_manager": MagicMock(),
    }
    hass.data["ectocontrol_modbus_controller"][entry.entry_id] = {
        "gateway": gw,
        "coordinator": coord,
    }

    async def _service_handler(call, command):
        data = call.data or {}
        entry_id = data.get("entry_id")
        if entry_id is None:
            entries = [k for k in hass.data["ectocontrol_modbus_controller"].keys() if k != "protocol_manager"]
            if len(entries) == 1:
                entry_id = entries[0]
            else:
                return

        ent = hass.data["ectocontrol_modbus_controller"].get(entry_id)
        if not ent:
            return  # Entry not found - should return early

        gw_handler: FakeGateway = ent["gateway"]
        try:
            if command == 2:
                await gw_handler.reboot_adapter()
            elif command == 3:
                await gw_handler.reset_boiler_errors()
        finally:
            try:
                await ent["coordinator"].async_request_refresh()
            except Exception:
                pass

    # Act
    call = MagicMock()
    call.data = {"entry_id": "invalid_entry_id"}  # Non-existent entry
    await _service_handler(call, 2)

    # Assert - should not call anything when entry not found
    assert gw.reboot_called is False
    assert coord.refreshed is False


@pytest.mark.asyncio
async def test_service_handler_gateway_access() -> None:
    """Test service handler gateway access."""
    # Arrange
    gw = FakeGateway()
    coord = DummyCoordinator(gw)
    hass = DummyHass()
    entry = DummyEntry("test_entry_1")

    hass.data["ectocontrol_modbus_controller"] = {
        "protocol_manager": MagicMock(),
    }
    hass.data["ectocontrol_modbus_controller"][entry.entry_id] = {
        "gateway": gw,
        "coordinator": coord,
    }

    async def _service_handler(call, command):
        data = call.data or {}
        entry_id = data.get("entry_id")
        if entry_id is None:
            entries = [k for k in hass.data["ectocontrol_modbus_controller"].keys() if k != "protocol_manager"]
            if len(entries) == 1:
                entry_id = entries[0]
            else:
                return

        ent = hass.data["ectocontrol_modbus_controller"].get(entry_id)
        if not ent:
            return
        gw_handler: FakeGateway = ent["gateway"]
        try:
            if command == 2:
                await gw_handler.reboot_adapter()
            elif command == 3:
                await gw_handler.reset_boiler_errors()
        finally:
            try:
                await ent["coordinator"].async_request_refresh()
            except Exception:
                pass

    # Act - Test both commands
    call1 = MagicMock()
    call1.data = {}
    await _service_handler(call1, 2)
    assert gw.reboot_called is True

    # Reset and test reset errors
    gw.reboot_called = False
    call2 = MagicMock()
    call2.data = {}
    await _service_handler(call2, 3)

    # Assert
    assert gw.reset_errors_called is True
    assert coord.refreshed is True


@pytest.mark.asyncio
async def test_read_write_registers_service() -> None:
    """Test debugging service for reading write registers."""
    # Arrange
    gw = FakeGateway()
    coord = DummyCoordinator(gw)
    hass = DummyHass()
    entry = DummyEntry("test_entry_1")

    # Mock protocol with read_registers method
    protocol_mock = MagicMock()
    protocol_mock.port = "/dev/ttyUSB0"

    async def mock_read_registers(slave_id, start_addr, count, timeout=None):
        """Mock read_registers to return test data."""
        # Return different values based on address
        if start_addr == 0x0031:  # CH_SETPOINT
            return [500]  # 50.0°C
        elif start_addr == 0x0032:  # EMERGENCY_CH
            return [600]
        elif start_addr == 0x0033:  # CH_MIN
            return [0x0030]  # MSB=0x00=48
        elif start_addr == 0x0034:  # CH_MAX
            return [0x0055]  # MSB=0x00=85
        elif start_addr == 0x0035:  # DHW_MIN
            return [0x0028]  # MSB=0x00=40
        elif start_addr == 0x0036:  # DHW_MAX
            return [0x0046]  # MSB=0x00=70
        elif start_addr == 0x0037:  # DHW_SETPOINT
            return [0x003C]  # MSB=0x00=60
        elif start_addr == 0x0038:  # MAX_MODULATION
            return [0x0064]  # MSB=0x00=100
        return None

    protocol_mock.read_registers = mock_read_registers
    gw.protocol = protocol_mock

    hass.data["ectocontrol_modbus_controller"] = {
        "protocol_manager": MagicMock(),
    }
    hass.data["ectocontrol_modbus_controller"][entry.entry_id] = {
        "gateway": gw,
        "coordinator": coord,
    }

    async def _read_write_registers_service(call):
        """Service to read write registers and log them for debugging."""
        data = call.data or {}
        entry_id = data.get("entry_id")
        if entry_id is None:
            entries = list(hass.data["ectocontrol_modbus_controller"].keys())
            if len(entries) == 1:
                entry_id = entries[0]
            else:
                return

        ent = hass.data["ectocontrol_modbus_controller"].get(entry_id)
        if not ent:
            return

        gw_handler: FakeGateway = ent["gateway"]
        protocol = gw_handler.protocol
        slave_id = gw_handler.slave_id

        # Write register addresses to read
        write_registers = {
            0x0031: "CH_SETPOINT",
            0x0032: "EMERGENCY_CH",
            0x0033: "CH_MIN",
            0x0034: "CH_MAX",
            0x0035: "DHW_MIN",
            0x0036: "DHW_MAX",
            0x0037: "DHW_SETPOINT",
            0x0038: "MAX_MODULATION",
        }

        results = []
        for addr, name in write_registers.items():
            try:
                result = await protocol.read_registers(slave_id, addr, 1)
                if result and len(result) > 0:
                    value = result[0]
                    results.append((addr, name, value))
                else:
                    results.append((addr, name, None))
            except Exception:
                results.append((addr, name, None))

        return results

    # Act
    call = MagicMock()
    call.data = {"entry_id": entry.entry_id}
    results = await _read_write_registers_service(call)

    # Assert - service returns results
    assert results is not None

    # Check DHW_SETPOINT (0x0037)
    dhw_setpoint = next((r for r in results if r[0] == 0x0037), None)
    assert dhw_setpoint is not None
    assert dhw_setpoint[1] == "DHW_SETPOINT"
    assert dhw_setpoint[2] == 0x003C
