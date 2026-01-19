# Testing Guide

This guide covers testing best practices for the Ectocontrol Modbus integration, including unit tests, integration tests, and config flow tests.

---

## Table of Contents

- [Overview](#overview)
- [Testing Framework](#testing-framework)
- [Test Structure](#test-structure)
- [Config Flow Testing](#config-flow-testing)
- [Unit Testing](#unit-testing)
- [Integration Testing](#integration-testing)
- [Test Coverage](#test-coverage)
- [Best Practices](#best-practices)

---

## Overview

The integration uses a 3-layer architecture, and tests should cover each layer independently:

```
┌─────────────────────────────────────────────┐
│  Config Flow Tests (test_config_flow.py)    │
│  - User-initiated setup                      │
│  - Options flow (modify settings)            │
│  - Reconfigure flow (modify core data)       │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Entity Tests (test_entities*.py)           │
│  - Sensor, binary_sensor, switch, etc.       │
│  - State properties, actions                 │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Gateway Tests (test_boiler_gateway*.py)    │
│  - Register scaling, bitfield logic          │
│  - Invalid marker handling                   │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Protocol Tests (test_modbus_protocol*.py)  │
│  - Connection, read/write, timeout           │
│  - Error handling                            │
└─────────────────────────────────────────────┘
```

---

## Testing Framework

### Dependencies

```bash
# requirements.txt or requirements_test.txt
pytest>=9.0.2
pytest-asyncio>=1.3.0
pytest-homeassistant-custom-component>=0.13.0
```

### pytest.ini Configuration

```ini
[pytest]
testpaths = tests
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function
```

---

## Test Structure

### File Organization

```
tests/
├── test_config_flow.py           # Config flow, options flow, reconfigure
├── test_modbus_protocol.py       # Protocol layer (connection, read/write)
├── test_modbus_protocol_edgecases.py  # Edge cases (timeout, disconnect)
├── test_modbus_protocol_connect.py    # Connection scenarios
├── test_modbus_protocol_more.py   # Additional protocol tests
├── test_boiler_gateway.py        # Register scaling, getters
├── test_boiler_gateway_more.py   # Additional gateway tests
├── test_coordinator.py           # Polling, caching
├── test_coordinator_error.py     # Error handling
├── test_init_module.py           # Module initialization
├── test_init_more.py             # Additional init tests
├── test_init_setup_entry.py      # Entry setup
├── test_entities.py              # Sensor entities
├── test_entities_more.py         # Additional entities
├── test_entities_climate.py      # Climate entity
├── test_entities_buttons.py      # Button entities
├── test_platforms_setup.py       # Platform registration
├── test_services_cleanup.py      # Service cleanup
├── test_integration_modbus.py    # Full integration with Modbus
└── test_integration_modbus_edgecases.py  # Integration edge cases
```

---

## Config Flow Testing

Config flow testing is critical for ensuring users can successfully set up and modify the integration.

### Flow Types

| Flow Type | Purpose | Method |
|-----------|---------|--------|
| **Config Flow** | Initial setup, creates entry | `async_step_user()` |
| **Options Flow** | Modify options (polling interval, retry count) | `async_step_init()` in OptionsFlow |
| **Reconfigure Flow** | Modify core data (port, slave_id) | `async_step_reconfigure()` |

### Basic Setup

```python
import pytest
from homeassistant import config_entries, setup
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ectocontrol_modbus_controller import config_flow, const

@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Automatically enable custom integrations (required for HA >= 2021.6.0b0)."""
    yield
```

### Test 1: Successful User Flow (CREATE)

```python
@pytest.mark.asyncio
async def test_config_flow_success(hass: HomeAssistant, mock_serial_ports, monkeypatch):
    """Test successful config flow - CREATE action."""
    await setup.async_setup_component(hass, "persistent_notification", {})

    # Mock ModbusProtocol to return success
    monkeypatch.setattr(config_flow, "ModbusProtocol", FakeProtocolOK)

    # 1. Initialize flow
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN,
        context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    # 2. Submit form with valid input
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            const.CONF_PORT: "/dev/ttyUSB0",
            const.CONF_SLAVE_ID: 1,
            const.CONF_NAME: "Boiler"
        }
    )

    # 3. Verify entry creation
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Boiler"
    assert result["data"][const.CONF_PORT] == "/dev/ttyUSB0"
    assert result["data"][const.CONF_SLAVE_ID] == 1
```

### Test 2: Connection Error

```python
@pytest.mark.asyncio
async def test_config_flow_cannot_connect(hass: HomeAssistant, mock_serial_ports, monkeypatch):
    """Test connection error handling."""
    await setup.async_setup_component(hass, "persistent_notification", {})

    # Mock ModbusProtocol to fail connection
    monkeypatch.setattr(config_flow, "ModbusProtocol", FakeProtocolFailConnect)

    result = await hass.config_entries.flow.async_init(
        const.DOMAIN,
        context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            const.CONF_PORT: "/dev/ttyUSB0",
            const.CONF_SLAVE_ID: 1
        }
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"
```

### Test 3: Duplicate Detection

```python
@pytest.mark.asyncio
async def test_config_flow_duplicate_detection(hass: HomeAssistant, mock_serial_ports, monkeypatch):
    """Test duplicate entry detection."""
    await setup.async_setup_component(hass, "persistent_notification", {})

    # Add existing entry
    existing_entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={const.CONF_PORT: "/dev/ttyUSB0", const.CONF_SLAVE_ID: 2}
    )
    existing_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        const.DOMAIN,
        context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            const.CONF_PORT: "/dev/ttyUSB0",
            const.CONF_SLAVE_ID: 2
        }
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "already_configured"
```

### Test 4: Options Flow (MODIFY)

```python
@pytest.mark.asyncio
async def test_options_flow(hass: HomeAssistant):
    """Test options flow - MODIFY polling interval and retry count."""
    # Create and add mock config entry
    mock_config_entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            const.CONF_PORT: "/dev/ttyUSB0",
            const.CONF_SLAVE_ID: 1,
            const.CONF_NAME: "Boiler"
        },
        options={
            const.CONF_POLLING_INTERVAL: 15,
            const.CONF_RETRY_COUNT: 3
        }
    )
    mock_config_entry.add_to_hass(hass)

    # 1. Initialize options flow
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    # 2. Submit updated options
    user_input = {
        const.CONF_POLLING_INTERVAL: 30,
        const.CONF_RETRY_COUNT: 5
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input
    )

    # 3. Wait for completion and verify
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options[const.CONF_POLLING_INTERVAL] == 30
    assert mock_config_entry.options[const.CONF_RETRY_COUNT] == 5
```

### Test 5: Reconfigure Flow (MODIFY Core Data)

```python
@pytest.mark.asyncio
async def test_reconfigure_flow(hass: HomeAssistant, monkeypatch):
    """Test reconfigure flow - MODIFY core settings (port, slave_id)."""
    await setup.async_setup_component(hass, "persistent_notification", {})

    # Create existing entry
    mock_config_entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            const.CONF_PORT: "/dev/ttyUSB0",
            const.CONF_SLAVE_ID: 1,
            const.CONF_NAME: "Boiler"
        }
    )
    mock_config_entry.add_to_hass(hass)

    monkeypatch.setattr(config_flow, "ModbusProtocol", FakeProtocolOK)

    # 1. Initiate reconfigure
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE},
        data=mock_config_entry
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    # 2. Submit updated settings
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            const.CONF_PORT: "/dev/ttyUSB1",
            const.CONF_SLAVE_ID: 2
        }
    )

    # 3. Verify entry was updated and reloaded
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[const.CONF_PORT] == "/dev/ttyUSB1"
    assert mock_config_entry.data[const.CONF_SLAVE_ID] == 2
```

### Mock Helpers

```python
class FakeProtocolOK:
    """Mock ModbusProtocol that succeeds."""
    def __init__(self, port, debug_modbus=False):
        self.port = port
        self.debug_modbus = debug_modbus

    async def connect(self):
        return True

    async def read_registers(self, slave, addr, count, timeout=None):
        return [0]

    async def disconnect(self):
        return None


class FakeProtocolFailConnect(FakeProtocolOK):
    """Mock ModbusProtocol that fails to connect."""
    async def connect(self):
        return False


class FakeProtocolNoResponse(FakeProtocolOK):
    """Mock ModbusProtocol that gets no response."""
    async def read_registers(self, *args, **kwargs):
        return None


class FakePort:
    """Mock serial port."""
    device = "/dev/ttyUSB0"


@pytest.fixture
def mock_serial_ports(monkeypatch):
    """Mock serial port listing."""
    monkeypatch.setattr(
        "custom_components.ectocontrol_modbus_controller.config_flow.serial.tools.list_ports.comports",
        lambda: [FakePort()]
    )
```

### Why We Use Custom Fakes Instead of MockConfigEntry

This integration uses custom fake classes (`DummyEntry`, `DummyHass`, `FakeGateway`) rather than Home Assistant's `MockConfigEntry` and `hass` fixture. This is an intentional design decision:

**Benefits:**
- **Isolation from HA changes**: Custom fakes don't break when Home Assistant updates its test utilities
- **Simplicity**: Direct control over mock behavior without complex fixture setup
- **Maintainability**: Easier to understand and modify
- **Focus**: Tests focus on integration logic, not HA framework details

**Trade-offs:**
- Less "realistic" HA environment
- Must manually maintain fake class interfaces

**Verdict**: For this Modbus integration with minimal HA coupling, custom fakes provide the best test coverage with the least maintenance burden.



---

## Unit Testing

### Protocol Layer Tests

Test the Modbus RTU wrapper in isolation:

```python
import pytest
from custom_components.ectocontrol_modbus_controller.modbus_protocol import ModbusProtocol

@pytest.mark.asyncio
async def test_protocol_connect_success():
    """Test successful connection."""
    protocol = ModbusProtocol("/dev/ttyUSB0")
    result = await protocol.connect()
    assert result is True

@pytest.mark.asyncio
async def test_protocol_read_registers():
    """Test reading registers."""
    protocol = ModbusProtocol("/dev/ttyUSB0")
    await protocol.connect()
    result = await protocol.read_registers(1, 0x0010, 5)
    assert result is not None
    assert len(result) == 5

@pytest.mark.asyncio
async def test_protocol_timeout():
    """Test timeout handling."""
    protocol = ModbusProtocol("/dev/ttyUSB0", timeout=0.1)
    await protocol.connect()
    result = await protocol.read_registers(99, 0x0010, 1)  # Non-existent slave
    assert result is None
```

### Gateway Layer Tests

Test register mapping and scaling logic:

```python
import pytest
from custom_components.ectocontrol_modbus_controller.boiler_gateway import BoilerGateway
from custom_components.ectocontrol_modbus_controller.const import REGISTER_CH_TEMP

def test_gateway_ch_temperature_scaling():
    """Test CH temperature scaling (divide by 10)."""
    protocol = FakeProtocolOK("/dev/ttyUSB0")
    gateway = BoilerGateway(protocol, slave_id=1)

    # Simulate cached register value
    gateway.cache = {REGISTER_CH_TEMP: 245}  # Raw value
    result = gateway.get_ch_temperature()

    assert result == 24.5  # 245 / 10

def test_gateway_invalid_marker():
    """Test invalid marker handling (0x7FFF)."""
    protocol = FakeProtocolOK("/dev/ttyUSB0")
    gateway = BoilerGateway(protocol, slave_id=1)

    gateway.cache = {REGISTER_CH_TEMP: 0x7FFF}
    result = gateway.get_ch_temperature()

    assert result is None  # Invalid marker

def test_gateway_bitfield_extraction():
    """Test bitfield state extraction."""
    protocol = FakeProtocolOK("/dev/ttyUSB0")
    gateway = BoilerGateway(protocol, slave_id=1)

    # Burner on (bit 0), Heating enabled (bit 1)
    gateway.cache = {REGISTER_STATES: 0x0003}

    assert gateway.get_burner_on() is True
    assert gateway.get_heating_enabled() is True
```

---

## Integration Testing

### Full Integration Test

Test the complete flow with mocked Modbus hardware:

```python
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ectocontrol_modbus_controller import const

@pytest.mark.asyncio
async def test_full_integration_setup(hass: HomeAssistant, monkeypatch):
    """Test full integration setup with mocked Modbus."""
    # 1. Setup config entry
    mock_config_entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            const.CONF_PORT: "/dev/ttyUSB0",
            const.CONF_SLAVE_ID: 1,
            const.CONF_NAME: "Boiler"
        }
    )
    mock_config_entry.add_to_hass(hass)

    # 2. Mock ModbusProtocol
    monkeypatch.setattr(
        "custom_components.ectocontrol_modbus_controller.ModbusProtocol",
        FakeProtocolOK
    )

    # 3. Setup entry
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # 4. Verify entities are created
    entity_registry = er.async_get(hass)
    entities = entity_registry.entities.keys()

    assert "sensor.boiler_ch_temperature" in entities
    assert "sensor.boiler_dhw_temperature" in entities
    assert "binary_sensor.boiler_burner_on" in entities
    assert "switch.boiler_heating_enable" in entities
```

---

## Test Coverage

### Coverage Goals

| Layer | Target Coverage |
|-------|-----------------|
| Protocol (`modbus_protocol.py`) | >80% |
| Gateway (`boiler_gateway.py`) | >90% |
| Config Flow (`config_flow.py`) | >90% |
| Entities (`entities/*.py`) | >85% |
| Coordinator (`coordinator.py`) | >85% |

### Run Coverage Report

```bash
# Generate HTML coverage report
pytest --cov=custom_components/ectocontrol_modbus_controller --cov-report=html

# Open report
# Linux/macOS
open htmlcov/index.html

# Windows
start htmlcov/index.html
```

### Coverage Exclusions

```ini
# .coveragerc
[run]
omit =
    */tests/*
    */__pycache__/*
    */site-packages/*
```

---

## Best Practices

### DO's

| Practice | Description |
|----------|-------------|
| **Use `FlowResultType` enum** | Type-safe flow result checking (`FlowResultType.CREATE_ENTRY`) |
| **Use `hass` fixture** | Full Home Assistant instance for integration tests |
| **Use `MockConfigEntry`** | Standard mock for config entries |
| **Test all flow paths** | Success, errors, aborts, duplicates |
| **Mock external dependencies** | Serial ports, Modbus connections |
| **Use `asyncio` marker** | For async tests: `@pytest.mark.asyncio` |
| **Test invalid markers** | Verify `0x7FFF`, `0xFF`, `0x7F` handling |
| **Test scaling logic** | Verify register value conversions |
| **Add type hints** | On all test function signatures |

### DON'Ts

| Practice | Description |
|----------|-------------|
| **Don't use dummy fakes** | Use `MockConfigEntry` instead of `DummyEntry` |
| **Don't use string comparison** | Use `FlowResultType` enum, not `"create_entry"` |
| **Don't skip async tests** | All I/O operations must be async-tested |
| **Don't ignore errors** | Test error paths explicitly |
| **Don't hardcode values** | Use constants from `const.py` |

### Test Naming

```python
# Good: Descriptive name with test subject and expected result
async def test_config_flow_success_with_valid_input(hass: HomeAssistant):
async def test_gateway_returns_none_for_invalid_marker():
async def test_options_flow_updates_polling_interval():

# Avoid: Generic names
async def test_flow():
async def test_gateway():
async def test_it():
```

### Test Structure

```python
# Arrange, Act, Assert (AAA) pattern

async def test_config_flow_success(hass: HomeAssistant):
    # Arrange: Setup test environment
    await setup.async_setup_component(hass, "persistent_notification", {})
    monkeypatch.setattr(config_flow, "ModbusProtocol", FakeProtocolOK)

    # Act: Execute the code being tested
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN,
        context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {const.CONF_PORT: "/dev/ttyUSB0", const.CONF_SLAVE_ID: 1}
    )

    # Assert: Verify expected outcome
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][const.CONF_PORT] == "/dev/ttyUSB0"
```

---

## Test Checklist

### Config Flow Tests

- [ ] User flow with valid input (success)
- [ ] User flow with invalid input (validation errors)
- [ ] Connection error handling
- [ ] Authentication error (if applicable)
- [ ] Duplicate entry detection
- [ ] Options flow (modify settings)
- [ ] Reconfigure flow (modify core data)
- [ ] Abort conditions (already configured, incomplete discovery)

### Entity Tests

- [ ] Entity creation during setup
- [ ] `native_value` property returns correct data
- [ ] `unique_id` format is correct
- [ ] `device_info` property is present
- [ ] `_attr_has_entity_name = True`
- [ ] Entity shows unavailable when coordinator fails
- [ ] Write actions (switches, numbers, buttons)
- [ ] `async_request_refresh()` called after writes

### Gateway Tests

- [ ] Register scaling (divide by 10, MSB extraction)
- [ ] Invalid marker handling (`0x7FFF`, `0xFF`, `0x7F`)
- [ ] Bitfield extraction and manipulation
- [ ] Write helpers (setpoints, circuit enables)

### Protocol Tests

- [ ] Successful connection
- [ ] Failed connection
- [ ] Read registers success
- [ ] Read registers timeout/no response
- [ ] Write register success
- [ ] Write register failure

---

## Integration Testing with socat PTY

For testing with virtual serial ports without physical hardware, use socat PTY pairs.

### Setup socat PTY

```bash
# Create two connected pseudo-terminals
socat -d -d -ls pty,link=/tmp/ttyVIRTUAL0,raw,echo=0 pty,link=/tmp/ttyVIRTUAL1,raw,echo=0
```

Output example:
```
2026/01/19 12:45:28 socat[325] N PTY is /dev/pts/7
2026/01/19 12:45:28 socat[325] N PTY is /dev/pts/5
2026/01/19 12:45:28 socat[325] N spawning "pty" option
2026/01/19 12:45:28 socat[325] N starting data loop
```

### Run Modbus Emulator

Terminal 1:
```bash
# Run simulator on one PTY
python -m modbus_slave_simulator --port /tmp/ttyVIRTUAL1 --slave-id 1
```

### Configure Home Assistant

Terminal 2 (in HA config flow):
- **Port**: `/tmp/ttyVIRTUAL0` (the OTHER PTY)
- **Slave ID**: `1` (must match emulator)
- Enable **Debug Modbus** for detailed logging

### Diagnosing socat PTY Issues

**Enable verbose socat logging:**
```bash
socat -d -d -d -x -ls pty,link=/tmp/ttyVIRTUAL0,raw,echo=0 pty,link=/tmp/ttyVIRTUAL1,raw,echo=0
```

**Interpreting socat logs:**
```
2026/01/19 12:45:28 socat[325] I transferred 8 bytes from 7 to 5
2026/01/19 12:45:28 socat[325] I transferred 5 bytes from 5 to 7
```

- **8 bytes from 7 to 5**: HA → Emulator (request)
  - `04 03 00 10 00 01 85 9a` = slave_id=4, read_holding_registers, addr=0x0010, count=1

- **5 bytes from 5 to 7**: Emulator → HA (response)
  - Normal: `04 03 02 00 64 f1` = slave_id=4, function=0x03, byte_count=2, data=0x0064, crc
  - Error: `04 83 02 c0 f1` = slave_id=4, error_flag, exception_code=02 (illegal address), crc

### Common PTY Issues

| Issue | Symptom | Fix |
|-------|---------|-----|
| **Slave ID mismatch** | `Exception code = 2` in logs | Match HA slave_id to emulator's `--slave-id` parameter |
| **Wrong PTY path** | "No such file or directory" | Use exact path from socat output (e.g., `/tmp/ttyVIRTUAL0`) |
| **Permissions denied** | "Permission denied" | Check PTY permissions: `ls -l /tmp/ttyVIRTUAL*` |
| **Stale PTY** | Connection hangs | Restart socat: `pkill socat` and recreate PTY |
| **Emulator not running** | TX but no RX | Verify emulator process: `ps aux \| grep simulator` |

### Troubleshooting Modbus Errors with PTY

**Enable debug logging in HA:**
```yaml
# configuration.yaml
logger:
  logs:
    custom_components.ectocontrol_modbus_controller.modbus_protocol: debug
```

**Check HA logs for TX/RX:**
```
custom_components.ectocontrol_modbus_controller.modbus_protocol.MODBUS_COM3: MODBUS_COM3 TX (8 bytes): 04 03 00 10 00 01 85 9a
custom_components.ectocontrol_modbus_controller.modbus_protocol.MODBUS_COM3: MODBUS_COM3 RX (5 bytes): 04 83 02 c0 f1
```

**If RX shows "N/A":**
- Request was sent but no response received
- Check emulator is running on correct PTY
- Verify slave_id matches

**If RX shows error response (0x83 prefix):**
- Response received but contains exception code
- Check slave_id and register address match emulator configuration

For more detailed troubleshooting, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

---

## Running Tests

### Quick Test Run

```bash
# Run all tests
pytest -q

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_config_flow.py -v

# Run specific test
pytest tests/test_config_flow.py::test_config_flow_success -v
```

### Run with Coverage

```bash
# Generate coverage report
pytest --cov=custom_components --cov-report=term-missing

# Generate HTML report
pytest --cov=custom_components --cov-report=html
```

### Run Tests by Marker

```bash
# Run only async tests
pytest -m asyncio -v

# Run only integration tests
pytest -m integration -v
```

---

## Resources

### Official Documentation

- [Testing your code - Home Assistant Developer Docs](https://developers.home-assistant.io/docs/development_testing/)
- [Config flow](https://developers.home-assistant.io/docs/config_entries_config_flow_handler)
- [Options flow](https://developers.home-assistant.io/docs/config_entries_options_flow_handler)
- [Integration tests file structure](https://developers.home-assistant.io/docs/creating_integration_tests_file_structure/)
- [Full test coverage for the config flow](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/config-flow-test-coverage/)
- [Integrations should have a reconfigure flow](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/reconfiguration-flow/)

### Tools & Libraries

- [pytest-homeassistant-custom-component - GitHub](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component)
- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio Documentation](https://pytest-asyncio.readthedocs.io/)

### Project Documentation

- [BUILD.md](BUILD.md) — Development setup
- [DESIGN.md](DESIGN.md) — Architecture overview
- [USAGE.md](USAGE.md) — User guide
- [CLAUDE.md](../CLAUDE.md) — Project instructions for AI assistants
