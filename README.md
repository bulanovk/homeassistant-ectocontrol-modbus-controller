# Ectocontrol Modbus Controller — Home Assistant Integration

[![GitHub Release](https://img.shields.io/github/release/bulanovk/ecto_modbus_devs.svg)](https://github.com/bulanovk/ecto_modbus_devs/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Home Assistant](https://img.shields.io/badge/Home_Assistant-2025.12%2B-blue)](https://www.home-assistant.io/)

**Ectocontrol Modbus Controller** is a Home Assistant integration that acts as a Modbus controller/master on the RS-485 bus, communicating with Ectocontrol devices. It provides a bridge to embed Ectocontrol device control into Home Assistant.

**First Implementation:** Boiler Controller V2 — exposes gas boiler sensors, controls, and diagnostics via Modbus RTU protocol.

## Features

✅ **Real-time Monitoring**
- CH/DHW water temperatures
- System pressure, flow rate, modulation level
- Burner, heating, and DHW circuit status
- Error codes and diagnostics

✅ **Direct Control**
- Set CH/DHW target temperatures
- Enable/disable heating and hot water circuits
- Adjust min/max temperature limits and max modulation
- Reboot adapter and reset error codes

✅ **Multi-Slave Support** ✨ NEW
- Multiple boilers on single serial port (RS-485 multi-drop)
- Shared connection with automatic reference counting
- Independent polling and control for each slave
- Up to 32 slaves per port (Modbus protocol limit)

✅ **Home Assistant Integration**
- Device registry support — each boiler appears as a separate device
- Climate entity for primary thermostat control
- 11+ sensor entities for data logging and automation
- Switch entities for on/off control
- Number entities for setpoint adjustment
- Button entities for commands
- Full availability tracking and error handling
- Automatic entity naming with device prefix (e.g., "Kitchen Boiler CH Temperature")

✅ **Reliability**
- Automatic retry with exponential backoff
- Device unavailable after 3 consecutive poll failures
- Invalid marker detection (0x7FFF, 0xFF, 0x7F)
- Comprehensive error logging

---

## Quick Start

### Installation

**Via HACS (Recommended)**:
1. Open Home Assistant → Settings → Devices & Services → Custom repositories
2. Add: `https://github.com/bulanovk/ecto_modbus_devs` (Category: Integration)
3. Install the integration and restart Home Assistant

**Manual**:
1. Download latest release
2. Extract `ectocontrol_modbus_controller` to `~/.homeassistant/custom_components/`
3. Restart Home Assistant

### Configuration

1. Settings → Devices & Services → **+ Add Integration**
2. Search for **Ectocontrol Modbus Controller** and click **Create**
3. Select serial port (e.g., `/dev/ttyUSB0`, `COM3`)
4. Enter Modbus slave ID (range: 1-32, matches the device's Modbus address)
5. Provide friendly name (e.g., "Kitchen Boiler")
6. **Optional**: Configure advanced settings:
   - **Polling Interval**: How often to poll the device (5-300 seconds, default: 15)
   - **Retry Count**: Number of retries on transient failures (0-10, default: 3)
   - **Debug Modbus**: Enable raw Modbus logging for troubleshooting
7. Click **Create** — integration tests connection and starts polling

**Hardware Required:**
- Ectocontrol Boiler Controller V2 device (or compatible Ectocontrol Modbus device)
- RS-485 serial connection to Home Assistant
- USB-RS485 adapter (e.g., CH340, FTDI) or native serial port

### Adding Multiple Slaves (Multi-Boiler Setup)

To add multiple boilers on the same serial port:

1. Add first boiler:
   - Port: `COM1` (or `/dev/ttyUSB0`)
   - Slave ID: `1`
   - Name: "Boiler 1"

2. Add second boiler:
   - Port: `COM1` (same port!)
   - Slave ID: `2` (different slave)
   - Name: "Boiler 2"

3. Repeat for additional boilers (slave IDs 3-32)

**Note:** All boilers on the same port share one serial connection. Each boiler has independent entities, controls, and polling.

**Full setup guide**: See [docs/USAGE.md](docs/USAGE.md)

---

## Documentation

| Document | Purpose |
|----------|---------|
| [docs/USAGE.md](docs/USAGE.md) | 📖 User guide, installation, configuration, troubleshooting |
| [docs/DESIGN.md](docs/DESIGN.md) | 🏗️ Architecture, data flow, register mapping, error handling |
| [docs/BUILD.md](docs/BUILD.md) | 🔨 Development setup, testing, contributing, adding features |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | 📋 Detailed technical specification & design |
| [PR_CHECKLIST.md](PR_CHECKLIST.md) | ✅ Feature tracking & development tasks |

---

## Project Structure

```
custom_components/ectocontrol_modbus_controller/
├── __init__.py              # Integration setup/unload
├── manifest.json            # Integration metadata
├── config_flow.py           # User configuration UI
├── const.py                 # Constants & register addresses
├── modbus_protocol.py       # Async Modbus RTU wrapper
├── boiler_gateway.py        # Register mapping & scaling
├── coordinator.py           # Polling & caching coordinator
├── diagnostics.py           # HA diagnostics hook
└── entities/
    ├── sensor.py            # 11+ temperature/pressure/flow sensors
    ├── binary_sensor.py     # State flags (burner, heating, DHW)
    ├── switch.py            # Control switches (heating, DHW enable)
    ├── number.py            # Setpoints & limits (CH, DHW, modulation)
    ├── climate.py           # Primary thermostat control
    └── button.py            # Commands (reboot, reset errors)
```

---

## Development

### Prerequisites

- Python 3.13+
- Home Assistant 2025.12+ (for local testing)
- `modbus-tk>=1.1.5`, `pyserial>=3.5`

### Setup

```bash
git clone https://github.com/bulanovk/ecto_modbus_devs.git
cd ecto_modbus_devs

python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### Testing

```bash
# Run all tests
pytest -q

# Run with coverage
pytest --cov=custom_components --cov-report=html

# Run specific test file
pytest tests/test_entities_climate.py -v
```

**Current status**: 52 tests passing ✅

### Adding a Feature

1. Add register constant in `const.py`
2. Add getter/setter in `boiler_gateway.py`
3. Add entity class in appropriate `entities/*.py` file with:
   - `_attr_has_entity_name = True` class attribute
   - `device_info` property with correct identifiers
   - `unique_id` property following naming convention
4. Register entity in `async_setup_entry()`
5. Add tests
6. Run full test suite: `pytest -q`

See [docs/BUILD.md](docs/BUILD.md) for detailed examples.

---

## Architecture

The integration uses a **3-layer architecture**:

```
┌──────────────────────┐
│  Home Assistant      │
│  Entities (Sensor,   │
│  Climate, Switch)    │
└──────────┬───────────┘
           │ (via gateway getters)
┌──────────▼───────────┐
│  DataUpdate          │
│  Coordinator         │
│  (polls every 15s)   │
└──────────┬───────────┘
           │ (updates cache)
┌──────────▼───────────┐
│  BoilerGateway       │
│  (register mapping,  │
│   scaling)           │
└──────────┬───────────┘
           │ (reads/writes)
┌──────────▼───────────┐
│  ModbusProtocol      │
│  (RTU I/O,           │
│   error handling)    │
└──────────┬───────────┘
           │
     ┌─────▼────────┐
     │ Serial Port  │
     │ ↔ Boiler    │
     │ (19200 RTU)  │
     └──────────────┘
```

**Key principles**:
- **No direct register access** from entities (always go through gateway)
- **Async I/O** for all Modbus operations (uses `run_in_executor()`)
- **Error handling**: Return `None`/`False` instead of raising exceptions
- **Caching**: Coordinator populates cache; gateway reads from cache
- **Availability**: Coordinator tracks update success; entities auto-mark unavailable

See [docs/DESIGN.md](docs/DESIGN.md) for full architecture details.

---

## Hardware Requirements

- **Ectocontrol device** (currently supported: Boiler Controller V2)
- **RS-485 serial interface** (USB converter or native UART)
- **Home Assistant** running on Linux, Raspberry Pi, or equivalent

**Supported Devices:**
- Ectocontrol Boiler Controller V2 (first implementation)
- Future: Additional Ectocontrol Modbus devices (e.g., eBus Adapter, Navien Adapter, etc.)

The integration acts as a **Modbus controller/master** on the RS-485 bus, polling Ectocontrol devices as slaves.

---

## Troubleshooting

### Connection Failed
- Verify serial port: `ls /dev/ttyUSB*` (Linux) or Device Manager (Windows)
- Check slave ID (usually `1`) against adapter/boiler manual
- Test with adapter software first to isolate HA vs. hardware issues
- **Enable Debug Modbus**: Reconfigure integration and check "Debug Modbus" to see raw Modbus traffic in logs

### Entities Show "Unavailable"
- Check integration reload: Settings → Devices & Services → Ectocontrol → Reload
- Increase polling interval if boiler is slow (reconfigure integration)
- Increase retry count for unreliable connections (reconfigure integration)
- Enable debug logging:
  ```yaml
  logger:
    logs:
      custom_components.ectocontrol_modbus_controller: debug
  ```

### Debug Mode
When **Debug Modbus** is enabled, raw Modbus frames appear in logs:
```
MODBUS_COM3 TX (8 bytes): 02 03 10 00 00 11 84 4a
MODBUS_COM3 RX (5 bytes): 02 03 02 00 64 f1
```

This helps diagnose:
- **TX bytes but no RX**: Wiring/baud rate issue
- **No TX bytes**: Port issue
- **RX garbage**: Baud rate mismatch

### More Help
See [docs/USAGE.md#troubleshooting](docs/USAGE.md#troubleshooting) or open an [issue](https://github.com/bulanovk/ecto_modbus_devs/issues).

---

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make changes and add tests
4. Ensure all tests pass: `pytest -q`
5. Open a Pull Request referencing [PR_CHECKLIST.md](PR_CHECKLIST.md)

See [docs/BUILD.md](docs/BUILD.md) for detailed development guidelines.

---

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

---

## Acknowledgments

- Home Assistant community and developers
- `modbus-tk` library maintainers
- Ectocontrol boiler adapter team

---

## Roadmap

- [ ] Auto-discovery of boilers on RS-485 network
- [ ] Multi-register write optimization
- [ ] Thermostat mode expansion (HEAT_ONLY, DHW_ONLY, HEAT+DHW)
- [ ] Historical error logging
- [ ] MQTT bridge
- [ ] Advanced scheduling (time-based setpoint profiles)

See [PR_CHECKLIST.md](PR_CHECKLIST.md) for detailed feature tracking.
