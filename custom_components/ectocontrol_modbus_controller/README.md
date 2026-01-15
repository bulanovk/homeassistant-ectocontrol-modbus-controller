# Ectocontrol Modbus Controller

Home Assistant integration that acts as a Modbus controller/master on the RS-485 bus, communicating with Ectocontrol devices.

**First Implementation:** Boiler Controller V2 — polls boiler registers (0x0010..0x0026) and exposes sensors, binary sensors, numbers, switches, climate control, and buttons.

Features
- Acts as Modbus controller/master, polling Ectocontrol devices as slaves
- Uses `modbus-tk` for RTU/serial communication
- Configurable via the Integrations UI (Config Flow)
- Supports multiple devices on a single serial port (multi-slave)
- Provides integration-level services: `reboot_adapter`, `reset_boiler_errors`

Installation (HACS)
1. Add this repository to HACS (Custom Repositories) as an integration.
2. Install via HACS and restart Home Assistant.
3. Open Settings → Devices & Services → Add Integration → search for "Ectocontrol Modbus Controller".

Configuration
- The integration uses the config flow to select serial port and slave ID.
- Typical serial settings: 19200 8N1, RS-485 half-duplex.

Development / Running tests
- Create a virtualenv and install test deps from the top-level `requirements.txt` (if present) and `pytest`, `pytest-asyncio`, `pytest-cov`.

Example commands:
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-cov
python -m pytest --maxfail=1 -q --cov=custom_components --cov-report=term-missing
```

Contributing
- Please open issues at the issue tracker URL in `manifest.json`.
- Follow Home Assistant integration guidelines for code style and testing.

License & Credits
- (Add your license and codeowners in `manifest.json`.)
