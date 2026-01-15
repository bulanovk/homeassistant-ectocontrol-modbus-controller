# AGENT.md

This file provides guidance to AI agents working with code in this repository.

## Project Overview

This is a Home Assistant custom integration for Ectocontrol Modbus Controller, which exposes gas boiler sensors, controls, and diagnostics via RS-485 Modbus RTU protocol.

**Key Technologies:**
- Python 3.12+
- Home Assistant Core (2025.12+)
- `modbus-tk>=1.1.5` (Modbus RTU communication)
- `pyserial>=3.5` (Serial port I/O)
- `pytest>=9.0.2` + `pytest-asyncio>=1.3.0` (testing)

---

## Environment Setup

**CRITICAL: Always use the `.venv` virtual environment when working with Python in this project.**

Before running any Python commands (pytest, pylint, mypy, pip, python), ensure the virtual environment is activated:

```bash
# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate
```

Your prompt should show `(.venv)` when the environment is active.

If you see `ModuleNotFoundError` or import errors, it usually means the virtual environment is not activated or dependencies are not installed.

---

## Component Requirements Summary

### Purpose
Expose gas boiler sensors, controls, and diagnostics via RS-485 Modbus RTU protocol using the Ectocontrol Modbus Adapter v2 hardware.

### Technical Requirements
| Category | Requirement |
|----------|-------------|
| **Python** | 3.12+ |
| **Home Assistant** | 2025.12+ |
| **Protocol** | Modbus RTU (19200 baud, 8N1, half-duplex) |
| **Hardware** | Ectocontrol Modbus Adapter v2 + RS-485 serial interface |

### Required Entity Types (Per Boiler)
| Type | Required Entities |
|------|-------------------|
| **Sensors** (11+) | CH Temp, DHW Temp, Pressure, Flow, Modulation, Outdoor Temp, CH Setpoint Active, Main Error, Add Error, Manufacturer Code, Model Code |
| **Binary Sensors** | Burner On, Heating Enabled, DHW Enabled |
| **Switches** | Heating Enable, DHW Enable |
| **Numbers** | CH Setpoint, CH Min/Max Limit, DHW Min/Max Limit, DHW Setpoint, Max Modulation |
| **Climate** | Primary thermostat control (Heat/Off modes) |
| **Buttons** | Reboot Adapter, Reset Boiler Errors |

### Configuration Flow Requirements
1. **Port Selection** - List available serial ports (`/dev/ttyUSB*`, `COM*`)
2. **Slave ID Input** - Range 1-32 (validates uniqueness per port)
3. **Connection Test** - Read register 0x0010 to verify communication
4. **Friendly Name** - User-provided device name
5. **Advanced Settings (Optional)**:
   - **Polling Interval**: 5-300 seconds (default: 15)
   - **Retry Count**: 0-10 retries (default: 3)
   - **Debug Modbus**: Enable raw hex logging for troubleshooting

### Error Handling Requirements
| Layer | Behavior |
|-------|----------|
| **ModbusProtocol** | Return `None` (reads) or `False` (writes); log errors |
| **BoilerGateway** | Return `None` for invalid markers (0x7FFF, 0xFF, 0x7F) |
| **Coordinator** | Raise `UpdateFailed`; 3 consecutive failures → device unavailable |
| **Entities** | Show unavailable when `coordinator.last_update_success == False` |

### Invalid/Unsupported Value Markers
- `0x7FFF` (16-bit signed): No sensor or error
- `0xFF` (8-bit unsigned): Unsupported/unavailable
- `0x7F` (8-bit signed): Invalid

### Entity Unique ID Format
```
ectocontrol_uid_{uid_hex}_{feature}
```
Where `{uid_hex}` is the 24-bit device UID in lowercase hex format (e.g., `8abcdef`).

**Important**: All entities use UID-based unique IDs. The UID is a unique 24-bit identifier (range 0x800000-0xFFFFFF) that is hardcoded in each Ectocontrol adapter.

### Device Registry
Each Ectocontrol adapter creates a single device in Home Assistant registry:
- **Device Identifiers**: `{DOMAIN, "uid_{uid_hex}"}` (e.g., `{"ectocontrol_modbus_controller", "uid_8abcdef"}`)
- **Device Info**: Updated after first coordinator poll with manufacturer, model, hw_version, sw_version
- **Entity Association**: All entities for an adapter belong to the same device
- **Entity Naming**: All entities use `_attr_has_entity_name = True` for automatic device-prefixed names
- **UID Requirement**: Device UID must be available during setup; integration setup fails if UID cannot be read

**Why UID-only identifiers?**
- **Port resilience**: Moving adapter to different USB port doesn't create duplicate devices
- **True uniqueness**: UID is guaranteed unique per adapter hardware
- **Simpler management**: One device per adapter, regardless of serial port configuration

### Polling Requirements
- **Default interval**: 15 seconds (configurable: 5-300 seconds via config flow)
- **Batch read**: All sensors read in single multi-register command (0x0010..0x0026 = 23 registers)
- **Timeout**: 2-3 seconds per Modbus operation
- **Retry behavior**: Configurable retry count (0-10) with exponential backoff (0.5s × attempt_number)

### Remaining Implementation Tasks (from PR_CHECKLIST.md)
- [ ] Climate entity implementation
- [ ] Button entities for reboot/reset commands
- [ ] Full switch/number entity coverage
- [ ] Adapter-type and adapter-reboot-code sensors
- [x] Centralized retry policy with exponential backoff (COMPLETED)
- [x] Slave ID range narrowed to 1-32 (COMPLETED)

### Completed Features (January 2025)
- [x] Configurable polling interval (5-300 seconds)
- [x] Configurable retry count (0-10 retries)
- [x] Debug Modbus mode with raw hex logging
- [x] Exponential backoff retry logic
- [x] DebugSerial wrapper for TX/RX byte logging
- [x] Debug logs for diagnostics calls
- [x] Debug logs for reboot/reset commands

---

## Project Structure

```
ectocontrol-modbus-boiler/
├── custom_components/
│   └── ectocontrol_modbus_controller/
│       ├── __init__.py               # Integration setup/unload
│       ├── manifest.json             # Integration metadata
│       ├── config_flow.py            # User configuration UI
│       ├── const.py                  # Constants & register addresses
│       ├── modbus_protocol.py       # Async Modbus RTU wrapper
│       ├── boiler_gateway.py        # Register mapping & scaling
│       ├── coordinator.py           # Polling & caching coordinator
│       ├── diagnostics.py           # HA diagnostics hook
│       ├── strings.json              # Localization strings
│       └── entities/
│           ├── sensor.py            # Temperature/pressure/flow sensors
│           ├── binary_sensor.py     # State flags (burner, heating, DHW)
│           ├── switch.py            # Control switches (heating, DHW enable)
│           ├── number.py            # Setpoints & limits (CH, DHW, modulation)
│           ├── climate.py           # Primary thermostat control
│           └── button.py            # Commands (reboot, reset errors)
├── tests/
│   ├── test_entities*.py            # Entity tests
│   ├── test_modbus_protocol*.py     # Protocol layer tests
│   ├── test_boiler_gateway*.py      # Gateway layer tests
│   └── ...                          # Other test files
├── docs/
│   ├── DESIGN.md                    # Architecture & design
│   ├── BUILD.md                     # Development setup & guidelines
│   └── USAGE.md                     # User guide
├── README.md                        # Main documentation
└── requirements.txt                 # Dependencies
```

## Development Commands

### Setup & Installation
```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate      # Windows

# Install dependencies
pip install -r requirements.txt
```

### Testing
```bash
# Run all tests
pytest -q

# Run tests with coverage
pytest --cov=custom_components --cov-report=html

# Run specific test file
pytest tests/test_entities_climate.py -v

# Run tests with specific marker
pytest -m asyncio -v
```

### Linting (Optional)
```bash
# Install linter
pip install pylint

# Check code
pylint custom_components/ectocontrol_modbus_controller
```

### Type Checking (Optional)
```bash
# Install type checker
pip install mypy

# Check types
mypy custom_components/ectocontrol_modbus_controller
```

## Architecture Overview

The integration uses a 3-layer architecture with clear separation of concerns:

```
┌─────────────────────────────────────┐
│  Home Assistant Entities             │
│  (sensor, switch, number, climate)  │
└────────────────┬────────────────────┘
                 │
┌────────────────▼────────────────────┐
│  DataUpdateCoordinator               │
│  (polling, caching, availability)   │
└────────────────┬────────────────────┘
                 │
┌────────────────▼────────────────────┐
│  BoilerGateway                       │
│  (register mapping, scaling, logic) │
└────────────────┬────────────────────┘
                 │
┌────────────────▼────────────────────┐
│  ModbusProtocol                      │
│  (async RTU communication)           │
└─────────────────────────────────────┘
```

**Layers:**
1. **Hardware Communication** (`ModbusProtocol`) - Thin async wrapper around `modbus-tk` RTU client, supports debug mode with `DebugSerial` wrapper
2. **Device Abstraction** (`BoilerGateway`) - High-level boiler state adapter with register mapping and scaling
3. **Home Assistant Integration** (Coordinator & Entities) - Entities that read from cache and write via gateway helpers

Data flow: Entities → Gateway getters → Cache (populated by Coordinator) → Protocol → Serial Port

## Configuration Constants

The integration uses these configuration keys stored in each config entry:

| Constant | Type | Range | Default | Purpose |
|----------|------|-------|---------|---------|
| `CONF_PORT` | string | — | — | Serial port device path |
| `CONF_SLAVE_ID` | int | 1-32 | 1 | Modbus slave ID |
| `CONF_NAME` | string | — | "" | Friendly device name (defaults to "Ectocontrol Controller {port_name}") |
| `CONF_POLLING_INTERVAL` | int | 5-300 | 15 | Seconds between polls |
| `CONF_RETRY_COUNT` | int | 0-10 | 3 | Number of retry attempts |
| `CONF_DEBUG_MODBUS` | bool | — | False | Enable raw hex logging |

**Default values** (from `const.py`):
```python
DEFAULT_SCAN_INTERVAL = timedelta(seconds=15)
MODBUS_RETRY_COUNT = 3
MODBUS_BAUDRATE = 19200
MODBUS_TIMEOUT = 2.0
```

## Key Principles

- **No direct register access** from entities (always go through gateway)
- **Async I/O** for all Modbus operations (uses `run_in_executor()`)
- **Error handling**: Return `None`/`False` instead of raising exceptions
- **Caching**: Coordinator populates cache; gateway reads from cache
- **Availability**: Coordinator tracks update success; entities auto-mark unavailable
- Entities should **never directly access** `ModbusProtocol`. Always go through `BoilerGateway`.
- `BoilerGateway` reads from cache populated by `DataUpdateCoordinator`, never directly reads registers.
- All writes go through `BoilerGateway` async helpers (e.g., `set_ch_setpoint()`, `set_circuit_enable_bit()`).

## Modbus Register Mapping

**Key Addresses** (all 16-bit registers unless noted):

```
0x0010  Status & Adapter Type (REGISTER_STATUS)
0x0011  HW/SW Version
0x0012-0x0013  Uptime (high/low words)
0x0018  CH Temperature (i16, ÷10 °C)
0x0019  DHW Temperature (u16, ÷10 °C)
0x001A  Pressure (u8 MSB, ÷10 bar)
0x001B  Flow Rate (u8 MSB, ÷10 L/min)
0x001C  Modulation Level (u8 MSB, %)
0x001D  States: burner/heating/DHW (bitfield)
0x001E  Main Error Code (u16)
0x001F  Additional Error Code (u16)
0x0020  Outdoor Temperature (i8 MSB, °C)
0x0026  CH Setpoint Active (i16, 1/256 °C)
0x0031  CH Setpoint (i16, ÷10 °C)
0x0032  Emergency CH Setpoint
0x0033  CH Min Limit (u8)
0x0034  CH Max Limit (u8)
0x0035  DHW Min Limit (u8)
0x0036  DHW Max Limit (u8)
0x0037  DHW Setpoint (u8, °C)
0x0038  Max Modulation (u8, %)
0x0039  Circuit Enable Flags (bitfield: bit0=heating, bit1=dhw)
0x0080  Command Register (2=reboot, 3=reset errors)
0x0081  Command Result Register
```

**Climate Entity Temperature Limits:**
The climate entity uses dynamic min/max temperature limits read from the boiler:
- `get_ch_min_limit()` - Returns CH minimum temperature from register 0x0033 (u8, °C)
- `get_ch_max_limit()` - Returns CH maximum temperature from register 0x0034 (u8, °C)
- `get_dhw_min_limit()` - Returns DHW minimum temperature from register 0x0035 (u8, °C)
- `get_dhw_max_limit()` - Returns DHW maximum temperature from register 0x0036 (u8, °C)

These methods extract the MSB from the 16-bit register value and return `None` if the value is `0xFF` (invalid marker). The climate entity falls back to safe defaults (5.0°C min, 85.0°C max) when limits are unavailable.

**Invalid/Unsupported Markers:**
- `0x7FFF` (16-bit signed): No sensor or error
- `0xFF` (8-bit unsigned): Unsupported/unavailable
- `0x7F` (8-bit signed): Invalid

When reading a register with an invalid marker, **return `None`** so Home Assistant shows the entity as unavailable.

## Scaling & Unit Conversion

Apply scaling in `BoilerGateway` getters, not in entity code:

```python
# Temperature: divide by 10
raw = 291  # from register
celsius = raw / 10.0  # 29.1°C

# Modulation: direct percentage
percent = msb  # 75 = 75%

# Pressure: MSB only, divide by 10
msb = (raw >> 8) & 0xFF  # extract MSB
bar = msb / 10.0  # 12 (0x0C) = 1.2 bar

# Bitfield: extract bits
lsb = raw & 0xFF
burner_on = bool(lsb & 0x01)  # bit 0
heating_enabled = bool((lsb >> 1) & 0x01)  # bit 1
```

## Async Patterns

**All blocking operations (serial I/O, Modbus reads/writes) must use `asyncio`:**

```python
# ✅ CORRECT: Use run_in_executor for sync modbus-tk calls
loop = asyncio.get_event_loop()
result = await loop.run_in_executor(None, self.client.read_holding_registers, slave, addr, count)

# ❌ WRONG: Never block the event loop directly
result = self.client.read_holding_registers(slave, addr, count)  # blocks!
```

**Lock pattern for concurrent access:**

```python
async with self._lock:
    # Serialize modbus operations to avoid conflicts on half-duplex RS-485
    result = await loop.run_in_executor(None, ...)
```

## Error Handling Strategy

**Protocol/Modbus errors return `None` or `False`:**

```python
async def read_registers(self, slave_id, start_addr, count, timeout=None):
    # On timeout, ModbusError, or any exception → return None
    try:
        ...
    except modbus.ModbusError:
        _LOGGER.error("...")
        return None  # Entity will show unavailable
```

**Coordinator marks device unavailable after 3 consecutive failures:**

```python
class BoilerDataUpdateCoordinator(DataUpdateCoordinator):
    async def _async_update_data(self):
        regs = await self.gateway.protocol.read_registers(...)
        if regs is None:
            raise UpdateFailed("No response")
        # Coordinator automatically tracks this; device → unavailable if threshold hit
```

## Coding Standards

### File Organization

1. **`const.py`** — All register addresses, domain, config keys, polling intervals
2. **`modbus_protocol.py`** — Async wrapper around modbus-tk, connection lifecycle
3. **`boiler_gateway.py`** — Register mapping, getters (read-only, cached), write helpers
4. **`coordinator.py`** — `DataUpdateCoordinator` subclass, polling logic
5. **`config_flow.py`** — Port selection, slave ID validation, connection test
6. **`__init__.py`** — Entry setup/unload, platform forwarding, services
7. **`diagnostics.py`** — Diagnostics export hook
8. **`entities/*.py`** — Sensor, switch, number, binary_sensor, climate, button entities

### Python Style

- Use **type hints** on all function signatures
- **Async functions** for I/O, state updates, or coordinator calls
- **Private methods** prefixed with `_` (e.g., `_read_register_cached`)
- **Logging**: Use module-level `_LOGGER = logging.getLogger(__name__)`
- **Docstrings**: One-liner for simple methods; full docstring for complex logic

### Imports

```python
from __future__ import annotations

from typing import Optional, List, Dict
import asyncio
import logging

from homeassistant.core import HomeAssistant
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, REGISTER_CH_TEMP
```

### Entity Unique IDs

All entities **must** have a unique ID in format: `{DOMAIN}_{slave_id}_{feature}`

```python
@property
def unique_id(self) -> str:
    return f"ectocontrol_{self.coordinator.gateway.slave_id}_ch_temperature"
```

This ensures entities persist across restarts and renames.

## Testing Conventions

### Test File Structure

- **`test_modbus_protocol.py`** — Connection, read/write, timeout, error handling
- **`test_boiler_gateway.py`** — Register scaling, getters, bitfield logic
- **`test_coordinator*.py`** — Polling, caching, refresh behavior
- **`test_config_flow.py`** — Port validation, slave ID uniqueness, connection test
- **`test_entities*.py`** — Entity state, properties, write actions
- **`test_init*.py`** — Setup/unload, service registration
- **`test_integration*.py`** — Full flow with mocked Modbus slave

### Mock/Fake Objects

Use simple `Fake*` classes for testing (no MagicMock for critical objects):

```python
class FakeGateway:
    def __init__(self):
        self.slave_id = 1
        self.cache = {}

    def get_ch_temperature(self):
        return 21.5  # Fixed return for consistent testing

    async def set_ch_setpoint(self, raw):
        self.last_set_raw = raw
        return True

class DummyCoordinator:
    def __init__(self, gateway):
        self.gateway = gateway

    async def async_request_refresh(self):
        self.refreshed = True
```

### Async Test Marker

```python
@pytest.mark.asyncio
async def test_my_async_function():
    result = await my_function()
    assert result == expected
```

## Adding New Features

### Adding a New Sensor

1. **Add register constant** in `const.py`:
   ```python
   REGISTER_NEW_SENSOR = 0x00XX
   ```

2. **Add gateway getter** in `boiler_gateway.py`:
   ```python
   def get_new_sensor(self) -> Optional[float]:
       raw = self._get_reg(REGISTER_NEW_SENSOR)
       if raw is None or raw == 0x7FFF:
           return None
       return raw / 10.0  # Apply scaling
   ```

3. **Add entity** in `entities/sensor.py`:
   ```python
   from homeassistant.helpers.device_registry import DeviceInfo

   class NewSensor(CoordinatorEntity, SensorEntity):
       _attr_has_entity_name = True

       @property
       def unique_id(self) -> str:
           return f"{DOMAIN}_{self.coordinator.gateway.slave_id}_new_sensor"

       @property
       def device_info(self) -> DeviceInfo:
           """Return device info for entity association."""
           return DeviceInfo(
               identifiers={(DOMAIN, f"{self.coordinator.gateway.protocol.port}:{self.coordinator.gateway.slave_id}")}
           )

       @property
       def native_value(self):
           return self.coordinator.gateway.get_new_sensor()
   ```

4. **Register in platform setup**:
   ```python
   async def async_setup_entry(hass, entry, async_add_entities):
       ...
       async_add_entities([NewSensor(coordinator)])
   ```

5. **Add tests** in `tests/test_entities.py` or new file:
   ```python
   def test_new_sensor_value():
       gw = FakeGateway()
       gw.cache[REGISTER_NEW_SENSOR] = 245
       coord = DummyCoordinator(gw)
       entity = NewSensor(coord)
       assert entity.native_value == 24.5
   ```

### Adding a New Control Switch

1. **Add write helper** in `boiler_gateway.py`:
   ```python
   async def set_new_control(self, enabled: bool) -> bool:
       return await self.set_circuit_enable_bit(2, enabled)  # bit 2
   ```

2. **Add entity** in `entities/switch.py`:
   ```python
   from homeassistant.helpers.device_registry import DeviceInfo

   class NewControlSwitch(CoordinatorEntity, SwitchEntity):
       _attr_has_entity_name = True

       def __init__(self, coordinator):
           super().__init__(coordinator)
           self._attr_name = "New Control"

       @property
       def unique_id(self) -> str:
           return f"{DOMAIN}_{self.coordinator.gateway.slave_id}_new_control"

       @property
       def device_info(self) -> DeviceInfo:
           return DeviceInfo(
               identifiers={(DOMAIN, f"{self.coordinator.gateway.protocol.port}:{self.coordinator.gateway.slave_id}")}
           )

       async def async_turn_on(self, **kwargs) -> None:
           await self.coordinator.gateway.set_new_control(True)
           await self.coordinator.async_request_refresh()
   ```

3. **Test** the action and coordinator refresh.

### Adding a New Number Entity

1. **Add register constant** and/or use existing setter in `boiler_gateway.py`
2. **Create NumberEntity subclass**:
   ```python
   from homeassistant.helpers.device_registry import DeviceInfo

   class NewSetpointNumber(CoordinatorEntity, NumberEntity):
       _attr_has_entity_name = True

       def __init__(self, coordinator):
           super().__init__(coordinator)
           self._attr_name = "New Setpoint"
           self._attr_native_min_value = 0
           self._attr_native_max_value = 100
           self._attr_native_step = 1

       @property
       def unique_id(self) -> str:
           return f"{DOMAIN}_{self.coordinator.gateway.slave_id}_new_setpoint"

       @property
       def device_info(self) -> DeviceInfo:
           return DeviceInfo(
               identifiers={(DOMAIN, f"{self.coordinator.gateway.protocol.port}:{self.coordinator.gateway.slave_id}")}
           )

       @property
       def native_value(self):
           return self.coordinator.gateway.get_new_setpoint()

       async def async_set_native_value(self, value: float) -> None:
           raw = int(round(value * SCALE_FACTOR))
           await self.coordinator.gateway.set_new_setpoint(raw)
           await self.coordinator.async_request_refresh()
   ```

## Common Patterns & Pitfalls

### ✅ DO

- Always add a `unique_id` property to entities using UID format: `ectocontrol_uid_{uid_hex}_{feature}`
- Always add a `device_info` property to entities for device association
- Always set `_attr_has_entity_name = True` on entity classes for automatic naming
- Call `async_request_refresh()` after write operations
- Check for invalid markers (`0x7FFF`, `0xFF`) and return `None`
- Use `_LOGGER.error()` for errors, `_LOGGER.debug()` for verbose logs
- Test with `FakeGateway` and `DummyCoordinator` to isolate entity logic
- Ensure test FakeGateway classes have `device_uid` set (e.g., `0x8ABCDEF`)
- Wrap modbus-tk calls in `run_in_executor()` to avoid blocking
- Use consistent UID-based device identifiers: `{DOMAIN, "uid_{uid_hex}"}`

### ❌ DON'T

- Directly read from `self.coordinator.data` in entity; use `BoilerGateway` getters
- Raise exceptions in `ModbusProtocol` or `BoilerGateway`; return `None`/`False`
- Mix sync and async code without proper `run_in_executor()`
- Hardcode register addresses in entity files; use constants
- Skip tests for new functionality
- Modify registers without going through `BoilerGateway` write helpers
- Forget to add `device_info` property to new entity classes
- Use `port:slave_id` format for device identifiers; only UID-based identifiers are supported
- Create entities without checking if `gateway.device_uid` is available

### Register Bitfield Manipulation

```python
# Read, modify, write pattern for 0x0039 (Circuit Enable flags)
current = await self.protocol.read_registers(slave_id, 0x0039, 1)
if current:
    current = current[0]
else:
    current = 0

# Set bit 1 (DHW enable)
newval = current | (1 << 1)  # Set bit
# newval = current & ~(1 << 1)  # Clear bit
# newval = current ^ (1 << 1)  # Toggle bit

await self.protocol.write_register(slave_id, 0x0039, newval)
```

## Debugging

### Debug Modbus Mode

When **Debug Modbus** is enabled (via config flow), the `DebugSerial` wrapper logs all raw bytes sent/received:

```
custom_components.ectocontrol_modbus_controller.modbus_protocol.MODBUS_COM3: MODBUS_COM3 TX (8 bytes): 02 03 10 00 00 11 84 4a
custom_components.ectocontrol_modbus_controller.modbus_protocol.MODBUS_COM3: MODBUS_COM3 RX (5 bytes): 02 03 02 00 64 f1
```

**Diagnosis guide**:
| Log Pattern | Diagnosis |
|-------------|-----------|
| TX but no RX | Wiring issue, wrong slave ID, adapter not powered |
| No TX bytes | Serial port issue or incorrect port |
| RX garbage data | Baud rate mismatch |
| CRC errors | Electrical noise or cable interference |

### Enable Debug Logging

Enable debug logging in Home Assistant configuration.yaml:
```yaml
logger:
  logs:
    custom_components.ectocontrol_modbus_controller: debug
    custom_components.ectocontrol_modbus_controller.modbus_protocol: debug
    custom_components.ectocontrol_modbus_controller.diagnostics: debug
    custom_components.ectocontrol_modbus_controller.button: debug
```

**Available debug logs**:

1. **Diagnostics calls** (`diagnostics.py`):
   - When diagnostics are fetched via HA Developer Tools
   - Shows config entry ID, title, slave_id, port, baudrate, cache size
   - Logs the complete diagnostics data payload

2. **Button commands** (`button.py`):
   - When "Reboot Adapter" button is pressed
   - When "Reset Boiler Errors" button is pressed

3. **Gateway commands** (`boiler_gateway.py`):
   - Reboot command (2) sent to register 0x0080
   - Reset errors command (3) sent to register 0x0080
   - Success/failure status for each command

**Check Modbus traffic** by adding log statements in `ModbusProtocol`:
```python
_LOGGER.debug(f"Read {count} regs from addr 0x{start_addr:04X}, slave {slave_id}")
_LOGGER.debug(f"Result: {result}")
```

**Verify register values** in HA diagnostics or via DevTools → States

**Run tests with verbose output**:
```bash
pytest tests/test_modbus_protocol.py -vv
```

## Integration Checklist for New Features

- [ ] Register address added to `const.py`
- [ ] `BoilerGateway` getter or write helper implemented
- [ ] Entity class created in appropriate `entities/*.py` file
- [ ] Entity registered in `async_setup_entry()`
- [ ] Unique ID format: `ectocontrol_{slave_id}_{feature}`
- [ ] Device info property added with correct identifiers
- [ ] `_attr_has_entity_name = True` set on entity class
- [ ] Unit/scaling applied correctly
- [ ] Invalid markers (`0x7FFF`, `0xFF`) handled → return `None`
- [ ] Tests written (fake gateway, coordinator, entity state/action)
- [ ] Tests pass locally (`pytest -q`)
- [ ] Docstrings and type hints added
