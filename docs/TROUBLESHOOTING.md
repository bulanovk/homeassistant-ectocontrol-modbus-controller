# Troubleshooting Guide

This guide helps diagnose and fix common issues with the Ectocontrol Modbus Controller integration.

---

## Table of Contents

- [Overview](#overview)
- [Quick Diagnosis Flowchart](#quick-diagnosis-flowchart)
- [Modbus Communication Issues](#modbus-communication-issues)
- [Testing with Emulators](#testing-with-emulators)
- [Entity Availability Issues](#entity-availability-issues)
- [Performance Issues](#performance-issues)
- [Debugging Tools](#debugging-tools)

---

## Overview

Common symptoms and their likely causes:

| Symptom | Likely Cause | Section |
|---------|--------------|---------|
| "Cannot connect" error | Wrong port, slave ID mismatch, emulator not running | [Modbus Communication](#modbus-communication-issues) |
| Entities show "unavailable" | Coordinator update failures, invalid markers | [Entity Availability](#entity-availability-issues) |
| Stale sensor values | Polling interval too long, coordinator not refreshing | [Performance](#performance-issues) |
| Config flow crashes | Missing dependencies, incorrect Python version | [Prerequisites](#prerequisites) |

---

## Quick Diagnosis Flowchart

```
┌─────────────────────────────────────────┐
│ Entities showing unavailable?           │
└──────────────┬──────────────────────────┘
               │ Yes
               ▼
    ┌──────────────────────┐
    │ Check HA logs for   │
    │ Modbus errors       │
    └──────────┬───────────┘
               │
    ┌──────────▼───────────┐
    │ "Modbus Error:       │
    │  Exception code = X" │
    └──────────┬───────────┘
               │
       ┌───────┴────────┐
       │                │
       ▼                ▼
┌──────────┐      ┌──────────┐
│ Code 02: │      │ Code 03: │
│ Illegal  │      │ Illegal  │
│ Data     │      │ Quantity │
│ Address  │      │          │
└────┬─────┘      └────┬─────┘
     │                 │
     ▼                 ▼
┌──────────┐      ┌──────────┐
│ Wrong    │      │ Wrong    │
│ slave_id │      │ register │
│ or       │      │ address  │
│ register │      │ or count │
└──────────┘      └──────────┘
```

---

## Modbus Communication Issues

### Symptom: "Cannot connect" during config flow

**Error in logs:**
```
Modbus error reading from port /dev/ttyUSB3 - Request: slave_id=4, start_addr=0x0010, count=1
Error: Modbus Error: Exception code = 2
```

**Diagnosis:** Modbus Exception Code 2 = "Illegal data address"

**Possible Causes:**

1. **Slave ID mismatch** (most common with emulators)
   - Your emulator is configured for `slave_id=1`, but you entered `slave_id=4` in the config flow
   - The emulator receives the request but rejects it because the slave ID doesn't match

2. **Wrong register address**
   - The emulator doesn't implement register 0x0010
   - Check your emulator's register map

3. **Emulator not running**
   - Verify the emulator process is active
   - Check socat PTY connections

**Solutions:**

**Option 1: Match the slave_id**
```bash
# If your emulator uses slave_id=1, configure HA with slave_id=1
# In the config flow, enter:
# - Slave ID: 1 (not 4)
```

**Option 2: Change emulator slave_id**
```python
# If using modbus_slave_simulator.py
python -m modbus_slave_simulator --slave-id 4 --port /dev/pts/1
```

**Option 3: Verify emulator register map**
```python
# Check if register 0x0010 is implemented
# In modbus_slave_simulator.py, verify _init_registers() includes:
self.registers[0x0010] = 0x0009  # Status register
```

---

### Symptom: "No response from device"

**Error in logs:**
```
Unexpected error reading registers - Error: Modbus Error: Exception code = 4 | TX: 04 03 00 10 00 01 85 9a | RX: N/A
```

**Diagnosis:** Modbus Exception Code 4 = "Slave device failure" or no response

**Possible Causes:**

1. **Emulator not running**
2. **Wrong serial port** (typo in port name)
3. **Baud rate mismatch** (emulator uses different baud rate)
4. **Serial port permissions** (Linux: not in `dialout` group)

**Solutions:**

**Verify emulator is running:**
```bash
# Check process
ps aux | grep socat
ps aux | grep python | grep simulator

# Check PTY connections
ls -l /dev/pts/*
```

**Verify serial port exists:**
```bash
# Linux
ls -l /dev/ttyUSB* /dev/ttyACM* /dev/pts/*

# Windows
mode COM*
```

**Fix permissions (Linux):**
```bash
# Add user to dialout group
sudo usermod -a -G dialout $USER

# Log out and back in for changes to take effect
```

**Check baud rate:**
```python
# Ensure emulator uses 19200 baud (default)
# In modbus_slave_simulator.py:
ser = serial.Serial(port, baudrate=19200, ...)
```

---

## Testing with Emulators

### Using socat PTY for Testing

**Setup:**
```bash
# Create two PTYs connected back-to-back
socat -d -d -ls pty,link=/tmp/ttyVIRTUAL0,raw,echo=0 pty,link=/tmp/ttyVIRTUAL1,raw,echo=0
```

**Run emulator:**
```bash
# Terminal 1: Run emulator on one PTY
python -m modbus_slave_simulator --port /tmp/ttyVIRTUAL1 --slave-id 1
```

**Configure HA:**
```yaml
# In config flow, use the OTHER PTY
port: /tmp/ttyVIRTUAL0
slave_id: 1
```

### Diagnosing socat PTY Issues

**Enable socat debug logging:**
```bash
socat -d -d -d -x -ls pty,link=/tmp/ttyVIRTUAL0,raw,echo=0 pty,link=/tmp/ttyVIRTUAL1,raw,echo=0
```

**Interpreting socat logs:**
```
2026/01/19 12:45:28 socat[325] I transferred 8 bytes from 7 to 5
2026/01/19 12:45:28 socat[325] I transferred 5 bytes from 5 to 7
```

- **8 bytes from 7 to 5**: Request sent from HA to emulator
  - `04 03 00 10 00 01 85 9a` = slave_id=4, read_holding_registers, addr=0x0010, count=1

- **5 bytes from 5 to 7**: Response received from emulator
  - If response is `04 83 02 c0 f1`: Exception response (code 02 = illegal address)

**Common PTY issues:**

| Issue | Symptom | Fix |
|-------|---------|-----|
| Wrong PTY path | "No such file or directory" | Use exact path from socat output |
| Permissions denied | "Permission denied" | Check PTY permissions (should be crw-rw----) |
| Stale PTY | Connection hangs | Restart socat after PTY restart |

---

## Entity Availability Issues

### Symptom: All entities show "unavailable"

**Diagnosis:** Coordinator update is failing

**Check in HA logs:**
```
Error fetching data: Update failed
```

**Solutions:**

1. **Verify physical connection**
   - Check USB/RS485 adapter is plugged in
   - Check LED indicators on adapter

2. **Check for Modbus errors**
   - Enable debug logging (see [Debugging Tools](#debugging-tools))
   - Look for exception codes in logs

3. **Verify device UID is available**
   - The integration requires UID during setup
   - Check logs for "Failed to read device UID"

4. **Increase timeout**
   - In config flow, increase "Read Timeout" from 3.0 to 5.0 seconds

### Symptom: Some entities unavailable, others working

**Diagnosis:** Specific registers returning invalid markers

**Check in HA DevTools → States:**
```
sensor.boiler_ch_temperature: 21.5
sensor.boiler_dhw_temperature: unavailable
```

**Solutions:**

1. **Verify sensor exists on boiler**
   - Some boilers don't have all sensors
   - Check boiler documentation

2. **Check for invalid markers in logs**
   ```
   Register 0x0019 returned 0x7FFF (invalid marker)
   ```

3. **Verify register address in const.py**
   ```python
   REGISTER_DHW_TEMP = 0x0019  # Verify address
   ```

---

## Performance Issues

### Symptom: Sensor values update too slowly

**Diagnosis:** Polling interval too long

**Solution:** Decrease polling interval

**In config flow:**
- Set "Polling Interval" to 5 seconds (minimum)

**Or via options flow:**
1. Settings → Devices & Services
2. Select Ectocontrol integration
3. Click "3-dot menu" → "Configure"
4. Change "Polling Interval"

### Symptom: HA becomes slow/unresponsive

**Diagnosis:** Polling interval too short or too many entities

**Solutions:**

1. **Increase polling interval** to 30-60 seconds
2. **Reduce retry count** to 1-2 retries
3. **Check for serial port conflicts** (multiple integrations using same port)

---

## Debugging Tools

### Enable Debug Logging

Add to `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.ectocontrol_modbus_controller: debug
    custom_components.ectocontrol_modbus_controller.modbus_protocol: debug
    custom_components.ectocontrol_modbus_controller.diagnostics: debug
    custom_components.ectocontrol_modbus_controller.button: debug
```

### Enable Modbus Debug Mode

**In config flow:**
1. Check "Debug Modbus" option
2. This enables raw hex logging of all TX/RX bytes

**Example debug output:**
```
custom_components.ectocontrol_modbus_controller.modbus_protocol.MODBUS_COM3: MODBUS_COM3 TX (8 bytes): 04 03 00 10 00 01 85 9a
custom_components.ectocontrol_modbus_controller.modbus_protocol.MODBUS_COM3: MODBUS_COM3 RX (5 bytes): 04 83 02 c0 f1
```

**Interpreting the logs:**

| Field | Meaning |
|-------|---------|
| `04` | Slave ID (4) |
| `03` | Function code (read holding registers) |
| `00 10` | Starting address (0x0010) |
| `00 01` | Register count (1) |
| `85 9a` | CRC checksum |

**Error response:**
| Field | Meaning |
|-------|---------|
| `04` | Slave ID |
| `83` | Function code + 0x80 (error flag) |
| `02` | Exception code 2 (illegal address) |
| `c0 f1` | CRC checksum |

### Use HA Diagnostics

**Developer Tools → Diagnostics:**

1. Select your Ectocontrol device
2. Click "Download Diagnostics"
3. Review the JSON file for:
   - Config entry settings
   - Register cache contents
   - Coordinator last update status
   - Device information (UID, model, version)

### Check Register Values Directly

**Using Python REPL:**
```python
# In HA container or venv
from custom_components.ectocontrol_modbus_controller import const
import serial
import modbus_tk.modbus_rtu as modbus_rtu

# Connect
ser = serial.Serial("/dev/ttyUSB0", baudrate=19200, timeout=2.0)
master = modbus_rtu.RtuMaster(ser)
master.open()

# Read register
result = master.execute(1, 3, 0x0010, 1)  # slave_id=1, read_holding, addr=0x0010, count=1
print(f"Register 0x0010 = {result[0]}")  # Should print hex value
```

---

## Common Error Messages

### "Modbus Error: Exception code = 02"

**Meaning:** Illegal data address

**Fix:**
- Check slave_id matches emulator/device
- Verify register address exists in device
- Check device documentation

### "Modbus Error: Exception code = 03"

**Meaning:** Illegal data value (invalid count or value in write request)

**Fix:**
- Check register count (typically 1-23 registers)
- Verify write values are within valid range

### "Modbus Error: Exception code = 04"

**Meaning:** Slave device failure

**Fix:**
- Check device is powered on
- Verify serial connections
- Check for device errors (LED indicators)

### "Failed to read device UID during setup"

**Meaning:** Cannot read unique device identifier

**Fix:**
- Verify device is an Ectocontrol adapter
- Check register 0x0001-0x0002 are accessible
- Ensure device supports UID protocol

### "Coordinator update failed after 3 attempts"

**Meaning:** Repeated Modbus communication failures

**Fix:**
- Check physical connection
- Increase timeout setting
- Reduce polling interval
- Check for electromagnetic interference

---

## Getting Help

### Before asking for help:

1. **Collect diagnostic information:**
   - HA log entries (search for "ectocontrol_modbus_controller")
   - Diagnostics file (Developer Tools → Diagnostics)
   - Config entry settings (port, slave_id, polling interval)

2. **Verify basics:**
   - Python version >= 3.12
   - Home Assistant version >= 2025.12
   - Dependencies installed (`pip install -r requirements.txt`)

3. **Test with emulator:**
   - Try with `modbus_slave_simulator.py` first
   - This isolates hardware from software issues

### Useful resources:

- **Project README**: [README.md](../README.md)
- **Modbus Protocol**: [docs/MODBUS_PROTOCOL.md](MODBUS_PROTOCOL.md)
- **Testing Guide**: [docs/TESTING.md](TESTING.md)
- **Build Guide**: [docs/BUILD.md](BUILD.md)

### Report issues:

Include in your bug report:
1. Home Assistant version
2. Integration version (from manifest.json)
3. Full error logs with debug logging enabled
4. Diagnostics file
5. Steps to reproduce
6. Hardware setup (adapter model, connection type)
