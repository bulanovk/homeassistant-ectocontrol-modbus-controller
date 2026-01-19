"""Tests for the Ectocontrol Modbus config flow."""

import pytest

import importlib

from homeassistant.data_entry_flow import FlowResultType

cf = importlib.import_module("custom_components.ectocontrol_modbus_controller.config_flow")
const = importlib.import_module("custom_components.ectocontrol_modbus_controller.const")


class DummyPort:
    """Dummy serial port for testing."""

    def __init__(self, device: str):
        self.device = device


class DummyEntry:
    """Dummy config entry for testing."""

    def __init__(self, data: dict, options: dict | None = None, entry_id: str = "test_entry_id"):
        self.data = data
        self.options = options or {}
        self.entry_id = entry_id
        self.domain = "ectocontrol_modbus_controller"


class DummyConfigEntries:
    """Dummy config entries for testing."""

    def __init__(self, entries: list[DummyEntry] | None = None):
        self._entries = entries or []
        self._entries_by_id = {e.entry_id: e for e in self._entries}

    def async_entries(self, domain: str):
        return self._entries

    def async_get_known_entry(self, entry_id: str):
        """Get entry by ID (required for reconfigure flow)."""
        return self._entries_by_id.get(entry_id)

    def async_update_entry(self, entry, data_updates: dict | None = None, **kwargs):
        """Update entry data (required for reconfigure flow)."""
        if data_updates:
            for key, value in data_updates.items():
                entry.data[key] = value
        return entry

    def async_schedule_reload(self, entry_id: str):
        """Schedule entry reload (required for reconfigure flow)."""
        return None


class DummyHass:
    """Dummy Home Assistant for testing."""

    def __init__(self, entries: list[DummyEntry] | None = None):
        self.config_entries = DummyConfigEntries(entries)


class FakeProtocolOK:
    """Fake protocol for successful connection tests."""

    def __init__(self, port: str, debug_modbus: bool = False):
        self.port = port
        self.debug_modbus = debug_modbus

    async def connect(self) -> bool:
        return True

    async def read_registers(self, slave: int, addr: int, count: int, timeout: float | None = None):
        # Return appropriate fake data based on address
        if addr == 0x0000 and count == 4:
            # Generic device info registers (0x0000-0x0003)
            # Return valid data for OpenTherm Adapter v2 with valid UID
            return [
                0x0000,  # REGISTER_RESERVED
                0x8ABC,  # UID high 16 bits
                0xDE00,  # UID low 8 bits in MSB
                0x1404,  # Device type 0x14 (OpenTherm v2), 4 channels
            ]
        return [0] * count  # Default: return count zeros

    async def disconnect(self):
        return None


class FakeProtocolFailConnect(FakeProtocolOK):
    """Fake protocol for failed connection tests."""

    async def connect(self) -> bool:
        return False


class FakeProtocolNoResponse(FakeProtocolOK):
    """Fake protocol for no response tests."""

    async def read_registers(self, *args, **kwargs):
        return None


class FakeProtocolException(FakeProtocolOK):
    """Fake protocol that raises exception during connect or read."""

    async def connect(self) -> bool:
        raise RuntimeError("Simulated connection error")


@pytest.mark.asyncio
async def test_config_flow_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test successful config flow - CREATE action."""
    monkeypatch.setattr(cf.serial.tools.list_ports, "comports", lambda: [DummyPort("/dev/ttyUSB0")])
    monkeypatch.setattr(cf, "ModbusProtocol", FakeProtocolOK)

    flow = cf.EctocontrolConfigFlow()
    flow.hass = DummyHass()

    user_input = {const.CONF_PORT: "/dev/ttyUSB0", const.CONF_SLAVE_ID: 1, const.CONF_NAME: "Boiler"}
    result = await flow.async_step_user(user_input)

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][const.CONF_PORT] == "/dev/ttyUSB0"


@pytest.mark.asyncio
async def test_config_flow_invalid_slave(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test config flow with invalid slave ID - validation error."""
    monkeypatch.setattr(cf.serial.tools.list_ports, "comports", lambda: [DummyPort("/dev/ttyUSB0")])
    flow = cf.EctocontrolConfigFlow()
    flow.hass = DummyHass()

    user_input = {const.CONF_PORT: "/dev/ttyUSB0", const.CONF_SLAVE_ID: 0, const.CONF_NAME: "Boiler"}
    result = await flow.async_step_user(user_input)

    assert result["type"] == FlowResultType.FORM
    assert "invalid_range" in result.get("errors", {}).values()


@pytest.mark.asyncio
async def test_config_flow_duplicate_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test config flow with duplicate port/slave_id combination."""
    monkeypatch.setattr(cf.serial.tools.list_ports, "comports", lambda: [DummyPort("/dev/ttyUSB0")])
    monkeypatch.setattr(cf, "ModbusProtocol", FakeProtocolOK)

    existing = DummyEntry({const.CONF_PORT: "/dev/ttyUSB0", const.CONF_SLAVE_ID: 2, const.CONF_NAME: "Boiler1"})
    flow = cf.EctocontrolConfigFlow()
    flow.hass = DummyHass(entries=[existing])

    user_input = {const.CONF_PORT: "/dev/ttyUSB0", const.CONF_SLAVE_ID: 2, const.CONF_NAME: "Boiler2"}
    result = await flow.async_step_user(user_input)

    assert result["type"] == FlowResultType.FORM
    assert "already_configured" in result.get("errors", {}).values()


@pytest.mark.asyncio
async def test_config_flow_cannot_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test config flow when connection fails."""
    monkeypatch.setattr(cf.serial.tools.list_ports, "comports", lambda: [DummyPort("/dev/ttyUSB0")])
    monkeypatch.setattr(cf, "ModbusProtocol", FakeProtocolFailConnect)

    flow = cf.EctocontrolConfigFlow()
    flow.hass = DummyHass()

    user_input = {const.CONF_PORT: "/dev/ttyUSB0", const.CONF_SLAVE_ID: 1, const.CONF_NAME: "Boiler"}
    result = await flow.async_step_user(user_input)

    assert result["type"] == FlowResultType.FORM
    assert "cannot_connect" in result.get("errors", {}).values()


@pytest.mark.asyncio
async def test_config_flow_no_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test config flow when device does not respond."""
    monkeypatch.setattr(cf.serial.tools.list_ports, "comports", lambda: [DummyPort("/dev/ttyUSB0")])
    monkeypatch.setattr(cf, "ModbusProtocol", FakeProtocolNoResponse)

    flow = cf.EctocontrolConfigFlow()
    flow.hass = DummyHass()

    user_input = {const.CONF_PORT: "/dev/ttyUSB0", const.CONF_SLAVE_ID: 1, const.CONF_NAME: "Boiler"}
    result = await flow.async_step_user(user_input)

    assert result["type"] == FlowResultType.FORM
    assert "cannot_connect" in result.get("errors", {}).values()


@pytest.mark.asyncio
async def test_config_flow_exception_during_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test config flow when exception occurs during connection test."""
    monkeypatch.setattr(cf.serial.tools.list_ports, "comports", lambda: [DummyPort("/dev/ttyUSB0")])
    monkeypatch.setattr(cf, "ModbusProtocol", FakeProtocolException)

    flow = cf.EctocontrolConfigFlow()
    flow.hass = DummyHass()

    user_input = {const.CONF_PORT: "/dev/ttyUSB0", const.CONF_SLAVE_ID: 1, const.CONF_NAME: "Boiler"}
    result = await flow.async_step_user(user_input)

    assert result["type"] == FlowResultType.FORM
    assert "cannot_connect" in result.get("errors", {}).values()


@pytest.mark.asyncio
async def test_config_flow_invalid_slave_not_a_number(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test config flow with invalid slave ID (not a number)."""
    monkeypatch.setattr(cf.serial.tools.list_ports, "comports", lambda: [DummyPort("/dev/ttyUSB0")])
    flow = cf.EctocontrolConfigFlow()
    flow.hass = DummyHass()

    user_input = {const.CONF_PORT: "/dev/ttyUSB0", const.CONF_SLAVE_ID: "abc", const.CONF_NAME: "Boiler"}
    result = await flow.async_step_user(user_input)

    assert result["type"] == FlowResultType.FORM
    assert "invalid_number" in result.get("errors", {}).values()


@pytest.mark.asyncio
async def test_config_flow_invalid_retry_count_not_a_number(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test config flow with invalid retry count (not a number)."""
    monkeypatch.setattr(cf.serial.tools.list_ports, "comports", lambda: [DummyPort("/dev/ttyUSB0")])
    monkeypatch.setattr(cf, "ModbusProtocol", FakeProtocolOK)

    flow = cf.EctocontrolConfigFlow()
    flow.hass = DummyHass()

    user_input = {
        const.CONF_PORT: "/dev/ttyUSB0",
        const.CONF_SLAVE_ID: 1,
        const.CONF_NAME: "Boiler",
        const.CONF_RETRY_COUNT: "invalid"
    }
    result = await flow.async_step_user(user_input)

    assert result["type"] == FlowResultType.FORM
    assert "invalid_number" in result.get("errors", {}).values()


@pytest.mark.asyncio
async def test_config_flow_invalid_read_timeout_not_a_number(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test config flow with invalid read timeout (not a number)."""
    monkeypatch.setattr(cf.serial.tools.list_ports, "comports", lambda: [DummyPort("/dev/ttyUSB0")])
    monkeypatch.setattr(cf, "ModbusProtocol", FakeProtocolOK)

    flow = cf.EctocontrolConfigFlow()
    flow.hass = DummyHass()

    user_input = {
        const.CONF_PORT: "/dev/ttyUSB0",
        const.CONF_SLAVE_ID: 1,
        const.CONF_NAME: "Boiler",
        const.CONF_READ_TIMEOUT: "invalid"
    }
    result = await flow.async_step_user(user_input)

    assert result["type"] == FlowResultType.FORM
    assert "invalid_number" in result.get("errors", {}).values()


@pytest.mark.asyncio
async def test_config_flow_invalid_retry_count_out_of_range(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test config flow with invalid retry count (out of range)."""
    monkeypatch.setattr(cf.serial.tools.list_ports, "comports", lambda: [DummyPort("/dev/ttyUSB0")])
    monkeypatch.setattr(cf, "ModbusProtocol", FakeProtocolOK)

    flow = cf.EctocontrolConfigFlow()
    flow.hass = DummyHass()

    user_input = {
        const.CONF_PORT: "/dev/ttyUSB0",
        const.CONF_SLAVE_ID: 1,
        const.CONF_NAME: "Boiler",
        const.CONF_RETRY_COUNT: 15
    }
    result = await flow.async_step_user(user_input)

    assert result["type"] == FlowResultType.FORM
    assert "invalid_range" in result.get("errors", {}).values()


@pytest.mark.asyncio
async def test_config_flow_invalid_read_timeout_out_of_range(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test config flow with invalid read timeout (out of range)."""
    monkeypatch.setattr(cf.serial.tools.list_ports, "comports", lambda: [DummyPort("/dev/ttyUSB0")])
    monkeypatch.setattr(cf, "ModbusProtocol", FakeProtocolOK)

    flow = cf.EctocontrolConfigFlow()
    flow.hass = DummyHass()

    user_input = {
        const.CONF_PORT: "/dev/ttyUSB0",
        const.CONF_SLAVE_ID: 1,
        const.CONF_NAME: "Boiler",
        const.CONF_READ_TIMEOUT: 100.0
    }
    result = await flow.async_step_user(user_input)

    assert result["type"] == FlowResultType.FORM
    assert "invalid_range" in result.get("errors", {}).values()


@pytest.mark.asyncio
async def test_config_flow_empty_ports_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test config flow when no serial ports are available."""
    monkeypatch.setattr(cf.serial.tools.list_ports, "comports", lambda: [])

    flow = cf.EctocontrolConfigFlow()
    flow.hass = DummyHass()

    # Initial form should be shown with empty ports
    result = await flow.async_step_user(None)

    assert result["type"] == FlowResultType.FORM
    # When no ports, the schema should allow any string input


@pytest.mark.asyncio
async def test_config_flow_serial_port_listing_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test config flow when serial port listing raises exception."""
    def failing_comports():
        raise OSError("Failed to list ports")

    monkeypatch.setattr(cf.serial.tools.list_ports, "comports", failing_comports)

    flow = cf.EctocontrolConfigFlow()
    flow.hass = DummyHass()

    # Initial form should still be shown even when port listing fails
    result = await flow.async_step_user(None)

    assert result["type"] == FlowResultType.FORM


@pytest.mark.asyncio
async def test_options_flow_init(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test options flow initial step shows form."""
    entry = DummyEntry(
        {const.CONF_PORT: "/dev/ttyUSB0", const.CONF_SLAVE_ID: 1, const.CONF_NAME: "Boiler"},
        options={const.CONF_POLLING_INTERVAL: 30, const.CONF_RETRY_COUNT: 5}
    )

    options_flow = cf.EctocontrolOptionsFlow(entry)
    result = await options_flow.async_step_init(None)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"


@pytest.mark.asyncio
async def test_options_flow_submit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test options flow submission creates entry."""
    entry = DummyEntry(
        {const.CONF_PORT: "/dev/ttyUSB0", const.CONF_SLAVE_ID: 1, const.CONF_NAME: "Boiler"},
        options={const.CONF_POLLING_INTERVAL: 15, const.CONF_RETRY_COUNT: 3}
    )

    options_flow = cf.EctocontrolOptionsFlow(entry)
    user_input = {
        const.CONF_POLLING_INTERVAL: 60,
        const.CONF_RETRY_COUNT: 7,
        const.CONF_DEBUG_MODBUS: True
    }
    result = await options_flow.async_step_init(user_input)

    assert result["type"] == FlowResultType.CREATE_ENTRY


@pytest.mark.asyncio
async def test_async_get_options_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test EctocontrolConfigFlow.async_get_options_flow returns options flow."""
    entry = DummyEntry(
        {const.CONF_PORT: "/dev/ttyUSB0", const.CONF_SLAVE_ID: 1, const.CONF_NAME: "Boiler"},
        options={}
    )

    options_flow = cf.EctocontrolConfigFlow.async_get_options_flow(entry)

    assert isinstance(options_flow, cf.EctocontrolOptionsFlow)
    assert options_flow._config_entry == entry


@pytest.mark.asyncio
async def test_reconfigure_flow_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test successful reconfigure flow - MODIFY port and slave_id."""
    from homeassistant import config_entries

    monkeypatch.setattr(cf.serial.tools.list_ports, "comports", lambda: [DummyPort("/dev/ttyUSB0"), DummyPort("/dev/ttyUSB1")])
    monkeypatch.setattr(cf, "ModbusProtocol", FakeProtocolOK)

    existing = DummyEntry(
        {const.CONF_PORT: "/dev/ttyUSB0", const.CONF_SLAVE_ID: 1, const.CONF_NAME: "Boiler"}
    )
    flow = cf.EctocontrolConfigFlow()
    flow.context = {"entry_id": existing.entry_id, "source": config_entries.SOURCE_RECONFIGURE}
    flow.hass = DummyHass(entries=[existing])

    # Submit new settings
    user_input = {const.CONF_PORT: "/dev/ttyUSB1", const.CONF_SLAVE_ID: 2, const.CONF_NAME: "Updated Boiler"}
    result = await flow.async_step_reconfigure(user_input)

    # Verify the flow aborts with success reason
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"


@pytest.mark.asyncio
async def test_reconfigure_flow_invalid_slave_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test reconfigure flow with invalid slave ID."""
    from homeassistant import config_entries

    monkeypatch.setattr(cf.serial.tools.list_ports, "comports", lambda: [DummyPort("/dev/ttyUSB0")])

    existing = DummyEntry({const.CONF_PORT: "/dev/ttyUSB0", const.CONF_SLAVE_ID: 1, const.CONF_NAME: "Boiler"})
    flow = cf.EctocontrolConfigFlow()
    flow.context = {"entry_id": existing.entry_id, "source": config_entries.SOURCE_RECONFIGURE}
    flow.hass = DummyHass(entries=[existing])

    user_input = {const.CONF_SLAVE_ID: 0, const.CONF_NAME: "Boiler"}
    result = await flow.async_step_reconfigure(user_input)

    assert result["type"] == FlowResultType.FORM
    assert "invalid_range" in result.get("errors", {}).values()


@pytest.mark.asyncio
async def test_reconfigure_flow_duplicate_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test reconfigure flow detects duplicate with another entry."""
    from homeassistant import config_entries

    monkeypatch.setattr(cf.serial.tools.list_ports, "comports", lambda: [DummyPort("/dev/ttyUSB0")])
    monkeypatch.setattr(cf, "ModbusProtocol", FakeProtocolOK)

    other_entry = DummyEntry({const.CONF_PORT: "/dev/ttyUSB0", const.CONF_SLAVE_ID: 2, const.CONF_NAME: "Other"}, entry_id="other_entry_id")
    existing = DummyEntry({const.CONF_PORT: "/dev/ttyUSB0", const.CONF_SLAVE_ID: 1, const.CONF_NAME: "Boiler"}, entry_id="existing_entry_id")

    flow = cf.EctocontrolConfigFlow()
    flow.context = {"entry_id": existing.entry_id, "source": config_entries.SOURCE_RECONFIGURE}
    flow.hass = DummyHass(entries=[other_entry, existing])

    user_input = {const.CONF_PORT: "/dev/ttyUSB0", const.CONF_SLAVE_ID: 2, const.CONF_NAME: "Boiler"}
    result = await flow.async_step_reconfigure(user_input)

    # Verify the form is shown with duplicate error
    assert result["type"] == FlowResultType.FORM
    assert "already_configured" in result.get("errors", {}).values()


@pytest.mark.asyncio
async def test_reconfigure_flow_cannot_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test reconfigure flow when connection fails."""
    from homeassistant import config_entries

    monkeypatch.setattr(cf.serial.tools.list_ports, "comports", lambda: [DummyPort("/dev/ttyUSB0")])
    monkeypatch.setattr(cf, "ModbusProtocol", FakeProtocolFailConnect)

    existing = DummyEntry({const.CONF_PORT: "/dev/ttyUSB0", const.CONF_SLAVE_ID: 1, const.CONF_NAME: "Boiler"})
    flow = cf.EctocontrolConfigFlow()
    flow.context = {"entry_id": existing.entry_id, "source": config_entries.SOURCE_RECONFIGURE}
    flow.hass = DummyHass(entries=[existing])

    user_input = {const.CONF_PORT: "/dev/ttyUSB0", const.CONF_SLAVE_ID: 1, const.CONF_NAME: "Boiler"}
    result = await flow.async_step_reconfigure(user_input)

    assert result["type"] == FlowResultType.FORM
    assert "cannot_connect" in result.get("errors", {}).values()
