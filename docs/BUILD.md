# Build & Development Guide

## Prerequisites

- **Python**: 3.13 or later
- **Home Assistant**: 2025.12 or later (for local testing)
- **Git**: For cloning and version control
- **Virtual Environment**: Recommended (`venv` or `conda`)

---

## Development Setup

### 1. Clone Repository

```bash
git clone https://github.com/bulanovk/ecto_modbus_devs.git
cd ecto_modbus_devs
```

### 2. Create Virtual Environment

```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate

# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Windows (cmd)
python -m venv .venv
.venv\Scripts\activate.bat
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

**requirements.txt contents**:
```
modbus-tk>=1.1.5
pyserial>=3.5
pytest>=9.0.2
pytest-asyncio>=1.3.0
```

### 4. Verify Installation

```bash
# Run tests
pytest -q

# Expected output: 52 passed
```

---

## Project Structure

```
ectocontrol-modbus-boiler/
├── .github/
│   ├── copilot-instructions.md       # Copilot guidance
│   └── PULL_REQUEST_TEMPLATE.md      # PR template
│
├── custom_components/
│   └── ectocontrol_modbus_controller/
│       ├── __init__.py               # Setup/unload, platform forwarding
│       ├── manifest.json             # Integration metadata
│       ├── const.py                  # Constants, register addresses
│       ├── config_flow.py            # User configuration UI
│       ├── modbus_protocol.py        # Modbus RTU wrapper
│       ├── boiler_gateway.py         # Register mapping, scaling
│       ├── coordinator.py            # Data polling & caching
│       ├── diagnostics.py            # HA diagnostics export
│       ├── strings.json              # Localization strings
│       ├── README.md                 # Integration README
│       └── entities/
│           ├── __init__.py
│           ├── sensor.py             # Temperature, pressure, flow sensors
│           ├── binary_sensor.py      # State flags (burner, heating, DHW)
│           ├── switch.py             # Control switches (heating, DHW)
│           ├── number.py             # Setpoints & limits (CH, DHW, modulation)
│           ├── climate.py            # Primary climate control
│           └── button.py             # Commands (reboot, reset)
│
├── tests/
│   ├── test_modbus_protocol*.py      # Protocol layer tests
│   ├── test_boiler_gateway*.py       # Gateway layer tests
│   ├── test_coordinator*.py          # Coordinator tests
│   ├── test_config_flow.py           # Config flow tests
│   ├── test_entities*.py             # Entity tests
│   ├── test_init*.py                 # Integration setup tests
│   ├── test_services_cleanup.py      # Service management tests
│   ├── test_integration*.py          # Integration tests
│   └── test_platforms_setup.py       # Platform setup tests
│
├── docs/
│   ├── DESIGN.md                     # Architecture & design
│   ├── BUILD.md                      # This file
│   ├── USAGE.md                      # User guide
│   └── TROUBLESHOOTING.md            # Troubleshooting
│
├── .gitignore
├── CHANGELOG.md
├── HARDWARE_VALIDATION.md
├── IMPLEMENTATION_PLAN.md
├── LICENSE
├── PR_CHECKLIST.md
├── README.md
├── requirements.txt
├── hacs.json
└── pytest.ini
```

---

## Building & Testing

### Run All Tests

```bash
pytest -q
```

**Output**: Shows test count and coverage summary

### Run Specific Test File

```bash
pytest tests/test_entities_climate.py -v
```

**Output**: Verbose output for single test file

### Run Tests with Coverage

```bash
pytest --cov=custom_components --cov-report=html
```

**Output**: Coverage report in `htmlcov/index.html`

### Run Tests with Specific Marker

```bash
pytest -m asyncio -v
```

**Output**: Only async tests

---

## Code Quality

### Linting (Optional, for local use)

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

### Code Style

Follow **PEP 8** conventions:
- 4-space indentation
- Max line length: 100 characters (pragmatic)
- Type hints on all function signatures
- Docstrings for public APIs

---

## Creating a New Feature

### Example: Add a New Sensor

**Step 1: Add register constant** in `const.py`

```python
REGISTER_OUTDOOR_TEMP = 0x0020
```

**Step 2: Add gateway getter** in `boiler_gateway.py`

```python
def get_outdoor_temperature(self) -> Optional[int]:
    raw = self._get_reg(REGISTER_OUTDOOR_TEMP)
    if raw is None:
        return None
    msb = (raw >> 8) & 0xFF
    if msb == 0x7F:
        return None
    # Signed i8
    if msb >= 0x80:
        msb = msb - 0x100
    return msb
```

**Step 3: Add entity** in `entities/sensor.py`

```python
class OutdoorTemperatureSensor(CoordinatorEntity, SensorEntity):
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Outdoor Temperature"
    
    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self.coordinator.gateway.slave_id}_outdoor_temp"
    
    @property
    def native_value(self):
        return self.coordinator.gateway.get_outdoor_temperature()
```

**Step 4: Register in platform setup**

```python
async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([OutdoorTemperatureSensor(coordinator)])
```

**Step 5: Add test** in `tests/test_entities.py`

```python
def test_outdoor_temp_sensor():
    gw = FakeGateway()
    gw.cache[0x0020] = 0x0C00  # 12 in MSB
    coord = DummyCoordinator(gw)
    
    sensor = OutdoorTemperatureSensor(coord)
    assert sensor.native_value == 12
```

---

## Debugging

### Enable Debug Logging

In Home Assistant `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.ectocontrol_modbus_controller: debug
    custom_components.ectocontrol_modbus_controller.modbus_protocol: debug
    custom_components.ectocontrol_modbus_controller.diagnostics: debug
    custom_components.ectocontrol_modbus_controller.button: debug
```

### Available Debug Logs

1. **Modbus Protocol** (`modbus_protocol.py`):
   - Raw hex dumps of TX/RX bytes (when Debug Modbus is enabled)
   - Connection status, errors, timeouts

2. **Diagnostics** (`diagnostics.py`):
   - When diagnostics are fetched via HA Developer Tools
   - Config entry ID, title, slave_id, port, baudrate
   - Cache size and complete diagnostics payload

3. **Button Commands** (`button.py`):
   - "Reboot Adapter button pressed for slave_id=X"
   - "Reset Boiler Errors button pressed for slave_id=X"

4. **Gateway Commands** (`boiler_gateway.py`):
   - Reboot/reset command execution with register address
   - Success/failure status

### Interactive Testing

```bash
# Start Python REPL
python

# Test import
from custom_components.ectocontrol_modbus_controller.boiler_gateway import BoilerGateway
from custom_components.ectocontrol_modbus_controller.modbus_protocol import ModbusProtocol

# Create instances (without real hardware)
protocol = ModbusProtocol("/dev/ttyUSB0")
gateway = BoilerGateway(protocol, slave_id=1)
print(gateway.get_ch_temperature())  # Returns None (no cache)
```

### Common Issues

**Test import errors**: Ensure `PYTHONPATH` is set:
```bash
export PYTHONPATH=/path/to/project
pytest -q
```

**Modbus connection timeout**: Check serial port and baud rate:
```bash
# List available ports
python -c "import serial.tools.list_ports; print([p.device for p in serial.tools.list_ports.comports()])"
```

**Entity not updating**: Check coordinator refresh:
- Verify polling interval in `const.py` (default 15s)
- Check for errors in `home-assistant.log`
- Restart Home Assistant integration

**Button commands not working**: Check debug logs for:
- Button press action logged
- Gateway command sent successfully
- Any errors during Modbus write operation

### Testing with Emulator

For integration testing without physical hardware, use the Modbus emulator with socat PTY:

**Setup socat PTY:**
```bash
# Create two connected pseudo-terminals
socat -d -d -ls pty,link=/tmp/ttyVIRTUAL0,raw,echo=0 pty,link=/tmp/ttyVIRTUAL1,raw,echo=0
```

**Run emulator:**
```bash
# Terminal 1: Run simulator on one PTY
python -m tests.modbus_slave_simulator --port /tmp/ttyVIRTUAL1 --slave-id 1
```

**Configure HA:**
```python
# In config flow, use the OTHER PTY
port: /tmp/ttyVIRTUAL0
slave_id: 1  # Must match emulator's --slave-id
```

**Verify communication:**
```bash
# Enable verbose socat logging to see data transfer
socat -d -d -d -x -ls pty,link=/tmp/ttyVIRTUAL0,raw,echo=0 pty,link=/tmp/ttyVIRTUAL1,raw,echo=0

# Check logs for:
# - "transferred 8 bytes from X to Y" (TX from HA)
# - "transferred 5 bytes from Y to X" (RX from emulator)
```

**Common emulator issues:**

| Issue | Symptom | Fix |
|-------|---------|-----|
| Slave ID mismatch | "Exception code = 2" in logs | Match HA slave_id to emulator's `--slave-id` |
| Emulator not running | TX but no RX in socat logs | Start emulator: `python -m tests.modbus_slave_simulator --port /tmp/ttyVIRTUAL1 --slave-id 1` |
| Wrong PTY path | "No such file or directory" | Verify PTY path matches socat output |

For detailed troubleshooting, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

---

## Committing & Creating a Pull Request

### Commit Guidelines

```bash
# Make changes, test locally
pytest -q

# Commit with clear message
git add custom_components/ectocontrol_modbus_controller/
git commit -m "feat: add outdoor temperature sensor

- Add REGISTER_OUTDOOR_TEMP constant
- Add BoilerGateway.get_outdoor_temperature() getter
- Add OutdoorTemperatureSensor entity
- Add unit tests

Closes #123"

# Push to feature branch
git push origin feature/outdoor-temp-sensor
```

### PR Checklist

Before opening a PR, verify:

- [ ] All tests pass: `pytest -q`
- [ ] New features added to `const.py` (registers), `boiler_gateway.py` (logic), and `entities/*.py` (UI)
- [ ] All entities have `unique_id` property in format `ectocontrol_{slave_id}_{feature}`
- [ ] Type hints on all function signatures
- [ ] Tests written for new code (>80% coverage)
- [ ] Docstrings added
- [ ] No hardcoded register addresses in entities
- [ ] Invalid marker checks (`0x7FFF`, `0xFF`) for new sensors
- [ ] `async_request_refresh()` called after write operations

### PR Title & Description

```
Title: feat: add outdoor temperature sensor

Description:
- Add support for reading outdoor temperature from register 0x0020
- Implements BoilerGateway getter with proper signed i8 handling
- Adds SensorEntity with automatic availability tracking
- Includes unit tests covering valid/invalid values

Related: Closes #123
```

---

## Release Process

1. **Update version** in `manifest.json`
2. **Update CHANGELOG.md** with new features/fixes
3. **Run full test suite**: `pytest --cov`
4. **Create Git tag**: `git tag v0.2.0`
5. **Create GitHub release** with CHANGELOG excerpt
6. **HACS submission** (if applicable)

---

## Resources

- [Home Assistant Developer Docs](https://developers.home-assistant.io/)
- [modbus-tk Documentation](https://github.com/ljnsn/modbus-tk)
- [IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md) — Detailed spec
- [PR_CHECKLIST.md](../PR_CHECKLIST.md) — Feature tracking
- [.github/copilot-instructions.md](../.github/copilot-instructions.md) — Copilot guidance

