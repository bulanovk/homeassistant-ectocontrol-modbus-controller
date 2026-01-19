# Integration Testing Plan with Virtual Serial Ports (socat PTY)

## Overview

This plan describes a comprehensive integration testing strategy using **socat PTY (pseudo-terminal)** pairs to create virtual serial ports. This enables realistic end-to-end testing of the Ectocontrol Modbus integration without requiring physical hardware.

## Why Virtual Serial Ports?

### Advantages
1. **No Physical Hardware Required** - Test on any machine without RS-485 adapters
2. **CI/CD Friendly** - Works in containerized environments, GitHub Actions, GitLab CI
3. **Deterministic Testing** - Full control over Modbus slave responses
4. **Fast Test Execution** - No physical I/O delays
5. **Parallel Testing** - Multiple virtual port pairs can run simultaneously
6. **Reproducible Bugs** - Can simulate edge cases, timeouts, malformed data

### Comparison with Existing Tests

| Test Type | Current Implementation | Limitations |
|-----------|----------------------|-------------|
| **Unit Tests** | Mock RtuMaster, fake gateways | Doesn't test real serial I/O |
| **Integration Tests** | Patched modbus_tk | Doesn't test serial port layer |
| **PTY Tests** (Proposed) | Real serial I/O via virtual PTY | Tests full stack including pyserial |

## Architecture

### Virtual Serial Port Pair

```
┌─────────────────────────────────────────────────────────┐
│  Integration (HA)                    Simulated Device   │
│  ┌──────────────────┐              ┌─────────────────┐ │
│  │ ModbusProtocol   │              │ Modbus Slave    │ │
│  │ /dev/pts/0       │              │ Simulator       │ │
│  └────────┬─────────┘              └────────┬────────┘ │
│           │                                  │          │
│  Master: /dev/pts/0               Slave: /dev/pts/1    │
│           │                                  │          │
└───────────┼──────────────────────────────────┼──────────┘
            │                                  │
        ┌───┴──────────────────────────────────┴───┐
        │         socat PTY pair                   │
        │  PTY0 (RW) ↔ PTY1 (RW)                   │
        └───────────────────────────────────────────┘
```

**How it works:**
1. **socat** creates two linked pseudo-terminals (e.g., `/dev/pts/0` and `/dev/pts/1`)
2. **Integration** (Master) writes to `/dev/pts/0`, reads from `/dev/pts/0`
3. **Simulator** (Slave) reads from `/dev/pts/1`, writes to `/dev/pts/1`
4. Data flows bidirectionally through the virtual pair

## Implementation Plan

### Phase 1: Infrastructure Setup

#### 1.1 Modbus Slave Simulator

**File**: `tests/modbus_slave_simulator.py`

Create a lightweight Modbus RTU slave simulator that:
- Listens on a serial port (PTY)
- Responds to standard Modbus function codes:
  - **0x03** (Read Holding Registers)
  - **0x06** (Write Single Register) - optional
  - **0x10** (Write Multiple Registers) - optional
- Implements Ectocontrol register map:
  - Generic device info (0x0000-0x0003)
  - Boiler status (0x0010-0x0026)
  - Command registers (0x0080-0x0081)
  - Register status monitoring (0x0040-0x006F)
- Supports configurable responses:
  - Normal operation
  - Timeout simulation
  - Invalid responses
  - Error injection

**Key Features:**
```python
class ModbusSlaveSimulator:
    """Simulated Ectocontrol Modbus slave device."""

    def __init__(self, port: str, slave_id: int = 1):
        self.port = port
        self.slave_id = slave_id
        self.registers = self._init_registers()
        self.running = False

    def _init_registers(self) -> dict[int, int]:
        """Initialize register map with default values."""
        return {
            # Generic device info
            0x0000: 0x0000,
            0x0001: 0x8ABC,  # UID high
            0x0002: 0xDE00,  # UID low
            0x0003: 0x1404,  # Device type 0x14, channels 4
            # Boiler status
            0x0010: 0x0009,  # Status: OpenTherm, connected
            0x0011: 0x012C,  # HW=1, SW=44
            0x0012: 0x0000,  # Uptime high
            0x0013: 0x001E,  # Uptime low (30 seconds)
            0x0018: 0x00A6,  # CH temp 16.6°C
            0x0019: 0x0158,  # DHW temp 34.8°C
            0x001A: 0x1200,  # Pressure 1.8 bar
            0x001B: 0x0E00,  # Flow 1.4 L/min
            0x001C: 0x4600,  # Modulation 70%
            0x001D: 0x0007,  # Burner on, heating on, DHW on
            0x0026: 0x0C80,  # CH setpoint active 50.0°C
            # Temperature limits
            0x0031: 0x0C80,  # CH setpoint 50.0°C
            0x0033: 0x2300,  # CH min 35°C
            0x0034: 0x5A00,  # CH max 90°C
            0x0035: 0x2800,  # DHW min 40°C
            0x0036: 0x4600,  # DHW max 70°C
            0x0037: 0x3C00,  # DHW setpoint 60°C
            0x0038: 0x6400,  # Max modulation 100%
            0x0039: 0x0003,  # Heating enabled, DHW enabled
            # Register status (all valid)
            **{addr: 0x0000 for addr in range(0x0040, 0x0070)},
        }

    async def start(self):
        """Start listening for Modbus requests."""
        self.running = True
        ser = serial.Serial(self.port, 19200, timeout=1.0)

        while self.running:
            # Read Modbus frame
            frame = self._read_frame(ser)
            if frame is None:
                continue

            # Parse and respond
            response = self._process_request(frame)
            if response:
                ser.write(response)

        ser.close()

    def _read_frame(self, ser: serial.Serial) -> bytes | None:
        """Read complete Modbus RTU frame."""
        # Read slave ID (1 byte)
        slave_id = ser.read(1)
        if not slave_id:
            return None

        # Read function code (1 byte)
        func_code = ser.read(1)
        if not func_code:
            return None

        # Read rest of frame based on function code
        # Implementation details...

    def _process_request(self, frame: bytes) -> bytes | None:
        """Process Modbus request and generate response."""
        # Parse frame
        slave_id = frame[0]
        func_code = frame[1]

        # Verify slave ID matches
        if slave_id != self.slave_id:
            return None  # Not for us

        # Route to function handler
        if func_code == 0x03:
            return self._handle_read_holding_registers(frame)
        elif func_code == 0x10:
            return self._handle_write_multiple_registers(frame)
        # ... other function codes

    def _handle_read_holding_registers(self, frame: bytes) -> bytes:
        """Handle function 0x03 (Read Holding Registers)."""
        start_addr = (frame[2] << 8) | frame[3]
        count = (frame[4] << 8) | frame[5]

        # Build response
        data = []
        for i in range(count):
            reg_addr = start_addr + i
            value = self.registers.get(reg_addr, 0x0000)
            data.append((value >> 8) & 0xFF)  # MSB
            data.append(value & 0xFF)        # LSB

        # Build response frame
        response = bytes([
            self.slave_id,      # Slave ID
            0x03,               # Function code
            len(data),          # Byte count
            *data,              # Register data
        ])

        # Calculate CRC
        crc = self._calculate_crc(response)
        return response + crc

    def set_register(self, addr: int, value: int):
        """Update register value (for test control)."""
        self.registers[addr] = value

    def inject_error(self, error_type: str):
        """Inject error condition for testing."""
        if error_type == "timeout":
            self._timeout_mode = True
        elif error_type == "invalid_crc":
            self._corrupt_crc = True
        # ... other error types
```

#### 1.2 socat PTY Manager

**File**: `tests/pty_manager.py`

```python
import asyncio
import subprocess
from pathlib import Path

class PTYManager:
    """Manages socat PTY pairs for virtual serial port testing."""

    def __init__(self):
        self.process: subprocess.Popen | None = None
        self.master_pty: str | None = None
        self.slave_pty: str | None = None

    async def create_pair(self) -> tuple[str, str]:
        """Create a PTY pair using socat.

        Returns:
            (master_port, slave_port) - Tuple of PTY device paths
            Example: ("/dev/pts/0", "/dev/pts/1")
        """
        # Start socat with PTY pair
        # -d -d: debug output (for troubleshooting)
        # pty,raw,echo=0: PTY settings (raw mode, no echo)
        # pty,raw,echo=0: second PTY
        cmd = ["socat", "-d", "-d", "pty,raw,echo=0", "pty,raw,echo=0"]

        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Wait for socat to start and create PTYs
        await asyncio.sleep(0.5)

        # Parse stderr to get PTY names
        # Socat outputs: "2025/01/18 12:34:56 socat[12345] N PTY is /dev/pts/0"
        stderr_lines = []
        while True:
            line = await self.process.stderr.readline()
            if not line:
                break
            stderr_lines.append(line.decode())

            # Extract PTY paths from stderr
            if b"PTY is" in line:
                pty_path = line.decode().split("PTY is ")[1].strip()
                if self.master_pty is None:
                    self.master_pty = pty_path
                else:
                    self.slave_pty = pty_path
                    break  # Got both PTYs

        if not self.master_pty or not self.slave_pty:
            raise RuntimeError("Failed to create PTY pair")

        return self.master_pty, self.slave_pty

    async def close(self):
        """Close the socat process and PTY pair."""
        if self.process:
            self.process.terminate()
            await self.process.wait()
            self.process = None
            self.master_pty = None
            self.slave_pty = None

    def __del__(self):
        """Cleanup on deletion."""
        if self.process:
            self.process.terminate()
```

#### 1.3 Test Dependencies

**Update**: `requirements_test.txt`

```txt
# Existing dependencies...
-r requirements.txt

# Testing framework
pytest>=9.0.2
pytest-asyncio>=1.3.0
pytest-cov>=6.0

# NEW: Integration testing dependencies
pyserial>=3.5  # Already in requirements.txt, but ensure latest
```

**Add**: `tests/conftest.py` fixtures

```python
import pytest
import asyncio
from pathlib import Path

from .pty_manager import PTYManager
from .modbus_slave_simulator import ModbusSlaveSimulator


@pytest.fixture
async def pty_pair():
    """Create a socat PTY pair for testing.

    Yields:
        (master_port, slave_port) tuple
    """
    manager = PTYManager()
    master, slave = await manager.create_pair()

    yield master, slave

    await manager.close()


@pytest.fixture
async def modbus_slave(pty_pair):
    """Create a Modbus slave simulator on a PTY.

    Yields:
        ModbusSlaveSimulator instance
    """
    master, slave = pty_pair

    # Create slave simulator on the slave PTY
    simulator = ModbusSlaveSimulator(port=slave, slave_id=1)

    # Start simulator in background
    task = asyncio.create_task(simulator.start())

    yield simulator

    # Cleanup
    simulator.running = False
    try:
        await asyncio.wait_for(task, timeout=2.0)
    except asyncio.TimeoutError:
        task.cancel()


@pytest.fixture
def test_device_registers():
    """Provide default register values for testing."""
    return {
        # Device info
        0x0000: 0x0000,
        0x0001: 0x8ABC,
        0x0002: 0xDE00,
        0x0003: 0x1404,
        # Status
        0x0010: 0x0009,
        0x0011: 0x012C,
        # ... full register map
    }
```

### Phase 2: Integration Test Suite

#### 2.1 Basic Connection Tests

**File**: `tests/test_integration_pty_connection.py`

```python
"""Test ModbusProtocol with real serial I/O via virtual PTY."""

import pytest
import asyncio

from custom_components.ectocontrol_modbus_controller.modbus_protocol import ModbusProtocol


@pytest.mark.asyncio
async def test_connect_to_virtual_port(modbus_slave, pty_pair) -> None:
    """Test connecting to a virtual serial port."""
    master, slave = pty_pair

    protocol = ModbusProtocol(port=master, baudrate=19200, timeout=2.0)

    # Test connection
    result = await protocol.connect()
    assert result is True
    assert protocol.is_connected is True

    # Cleanup
    await protocol.disconnect()


@pytest.mark.asyncio
async def test_read_device_info(modbus_slave, pty_pair) -> None:
    """Test reading device info registers (0x0000-0x0003)."""
    master, slave = pty_pair

    protocol = ModbusProtocol(port=master, baudrate=19200, timeout=2.0)
    await protocol.connect()

    # Read generic device info
    regs = await protocol.read_registers(slave_id=1, start_addr=0x0000, count=4)

    assert regs is not None
    assert len(regs) == 4
    assert regs[0] == 0x0000  # Reserved
    assert regs[1] == 0x8ABC  # UID high
    assert regs[2] == 0xDE00  # UID low
    assert regs[3] == 0x1404  # Device type, channels

    await protocol.disconnect()


@pytest.mark.asyncio
async def test_read_boiler_status(modbus_slave, pty_pair) -> None:
    """Test reading boiler status registers."""
    master, slave = pty_pair

    protocol = ModbusProtocol(port=master, baudrate=19200, timeout=2.0)
    await protocol.connect()

    # Read status block (0x0010-0x0026)
    regs = await protocol.read_registers(slave_id=1, start_addr=0x0010, count=23)

    assert regs is not None
    assert len(regs) == 23

    # Verify specific registers
    assert regs[0] == 0x0009  # STATUS: OpenTherm, connected
    assert regs[1] == 0x012C  # VERSION: HW=1, SW=44

    await protocol.disconnect()


@pytest.mark.asyncio
async def test_write_register(modbus_slave, pty_pair) -> None:
    """Test writing to a register."""
    master, slave = pty_pair

    protocol = ModbusProtocol(port=master, baudrate=19200, timeout=2.0)
    await protocol.connect()

    # Write CH setpoint (0x0031)
    result = await protocol.write_register(slave_id=1, addr=0x0031, value=0x0C80)
    assert result is True

    # Verify the simulator received the write
    # (Simulator should update its register map)
    await asyncio.sleep(0.1)

    await protocol.disconnect()
```

#### 2.2 Full Integration Tests

**File**: `tests/test_integration_pty_full.py`

```python
"""Full integration tests with real Modbus communication."""

import pytest
from unittest.mock import patch

from custom_components.ectocontrol_modbus_controller import async_setup_entry
from custom_components.ectocontrol_modbus_controller.const import (
    DOMAIN, CONF_PORT, CONF_SLAVE_ID
)


@pytest.mark.asyncio
async def test_full_setup_with_virtual_port(modbus_slave, pty_pair) -> None:
    """Test complete integration setup with virtual serial port."""
    master, slave = pty_pair

    # Create fake HA and config entry
    class FakeHass:
        def __init__(self):
            self.data = {DOMAIN: {}}
            self.services = MagicMock()
            self.config = MagicMock()
            self.loop = asyncio.get_event_loop()

    hass = FakeHass()

    # Initialize protocol manager
    from custom_components.ectocontrol_modbus_controller.modbus_protocol_manager import ModbusProtocolManager
    hass.data[DOMAIN]["protocol_manager"] = ModbusProtocolManager()

    # Create config entry
    class FakeEntry:
        def __init__(self):
            self.entry_id = "test_entry"
            self.data = {
                CONF_PORT: master,
                CONF_SLAVE_ID: 1,
                CONF_NAME: "Test Boiler",
            }

    entry = FakeEntry()

    # Patch device registry
    with patch("custom_components.ectocontrol_modbus_controller.dr.async_get") as mock_get_dr:
        # ... setup fake device registry

        # Run setup
        result = await async_setup_entry(hass, entry)
        assert result is True

        # Verify gateway was created
        inst = hass.data[DOMAIN][entry.entry_id]
        gateway = inst["gateway"]
        coordinator = inst["coordinator"]

        # Verify device info was read
        assert gateway.device_uid is not None
        assert gateway.device_uid == 0x8ABCDE

        # Trigger coordinator update
        data = await coordinator._async_update_data()
        assert isinstance(data, dict)
        assert len(data) > 0

        # Verify entity getters return correct values
        ch_temp = gateway.get_ch_temperature()
        assert ch_temp == pytest.approx(16.6, 0.1)

        pressure = gateway.get_pressure()
        assert pressure == pytest.approx(1.8, 0.1)
```

#### 2.3 Error Scenario Tests

**File**: `tests/test_integration_pty_errors.py`

```python
"""Test error handling with virtual serial port."""

import pytest


@pytest.mark.asyncio
async def test_timeout_on_read(modbus_slave, pty_pair) -> None:
    """Test timeout handling when simulator doesn't respond."""
    master, slave = pty_pair

    # Configure simulator to timeout
    modbus_slave.inject_error("timeout")

    protocol = ModbusProtocol(port=master, baudrate=19200, timeout=1.0)
    await protocol.connect()

    # Attempt read should return None after timeout
    regs = await protocol.read_registers(slave_id=1, start_addr=0x0010, count=1)
    assert regs is None

    await protocol.disconnect()


@pytest.mark.asyncio
async def test_invalid_slave_id(modbus_slave, pty_pair) -> None:
    """Test reading from wrong slave ID."""
    master, slave = pty_pair

    protocol = ModbusProtocol(port=master, baudrate=19200, timeout=2.0)
    await protocol.connect()

    # Read with wrong slave ID (simulator is slave 1)
    regs = await protocol.read_registers(slave_id=2, start_addr=0x0010, count=1)
    # Should return None (no response from slave 2)
    assert regs is None

    await protocol.disconnect()


@pytest.mark.asyncio
async def test_malformed_response(modbus_slave, pty_pair) -> None:
    """Test handling of malformed Modbus response."""
    master, slave = pty_pair

    # Configure simulator to send malformed response
    modbus_slave.inject_error("malformed")

    protocol = ModbusProtocol(port=master, baudrate=19200, timeout=2.0)
    await protocol.connect()

    # Read should handle malformed response gracefully
    regs = await protocol.read_registers(slave_id=1, start_addr=0x0010, count=1)
    assert regs is None  # Error should be caught

    await protocol.disconnect()
```

### Phase 3: Test Execution & CI/CD

#### 3.1 Run Commands

**Local Testing:**
```bash
# Check if socat is installed
socat -V

# Run all PTY integration tests
pytest tests/test_integration_pty*.py -v

# Run specific test
pytest tests/test_integration_pty_connection.py::test_connect_to_virtual_port -v

# Run with verbose output
pytest tests/test_integration_pty*.py -vv -s

# Run with coverage
pytest --cov=custom_components tests/test_integration_pty*.py
```

#### 3.2 CI/CD Integration

**GitHub Actions**: `.github/workflows/integration-tests.yml`

```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  integration-tests:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.13'

      - name: Install dependencies
        run: |
          python -m venv .venv
          source .venv/bin/activate
          pip install -r requirements.txt
          pip install -r requirements_test.txt

      - name: Install socat
        run: sudo apt-get install -y socat

      - name: Verify socat installation
        run: socat -V

      - name: Run integration tests
        run: |
          source .venv/bin/activate
          pytest tests/test_integration_pty*.py -v --cov=custom_components

      - name: Upload coverage
        uses: codecov/codecov-action@v4
```

## Test Scenarios

### Scenario 1: Normal Operation
**Purpose**: Verify correct data flow in ideal conditions

1. Create PTY pair
2. Start Modbus simulator with default registers
3. Connect with ModbusProtocol
4. Read device info registers
5. Read boiler status registers
6. Verify data scaling and conversion
7. Write to command register
8. Verify write response
9. Disconnect

**Expected Result**: All reads/writes succeed, data matches expected values

### Scenario 2: Connection Failure
**Purpose**: Test handling of unavailable serial port

1. Try to connect to non-existent PTY
2. Verify connect() returns False
3. Verify error logging
4. Verify no exception raised

**Expected Result**: Graceful failure, logged error

### Scenario 3: Timeout Handling
**Purpose**: Test read timeout behavior

1. Connect to simulator
2. Configure simulator to not respond
3. Issue read request with short timeout
4. Verify read returns None after timeout
5. Verify error log with timeout message
6. Verify protocol still connected

**Expected Result**: Timeout handled gracefully, connection remains

### Scenario 4: Multiple Slaves
**Purpose**: Test multi-slave architecture

1. Create multiple PTY pairs
2. Start simulators on each with different slave IDs
3. Create protocol for each port
4. Verify protocols can operate concurrently
5. Verify reference counting

**Expected Result**: All slaves communicate independently

### Scenario 5: Register Status Monitoring
**Purpose**: Test register health checking

1. Configure simulator with register status
2. Set some registers to "not supported" status
3. Read registers via gateway
4. Verify gateway returns None for unsupported registers
5. Verify status is logged

**Expected Result**: Unsupported registers handled correctly

### Scenario 6: Command Execution
**Purpose**: Test reboot/reset commands

1. Connect to simulator
2. Send reboot command to 0x0080
3. Read command result from 0x0081
4. Verify result = CMD_RESULT_SUCCESS
5. Verify simulator state changed

**Expected Result**: Commands execute successfully

## Known Limitations

### 1. Timing Differences
Virtual PTY has different timing characteristics than real serial:
- No physical signal delays
- No baud rate limitations
- Instant data transfer

**Mitigation**: Add artificial delays in simulator for realistic testing

### 2. Platform Support
socat PTY works on Linux/macOS, not Windows:
- Windows requires named pipes (socat can create PIPE:)
- Alternative: Use `com0com` null-modem emulator

**Mitigation**: Skip PTY tests on Windows, use mocks

### 3. Resource Cleanup
PTY pairs must be cleaned up properly:
- Orphaned socat processes
- Stale PTY devices

**Mitigation**: Robust cleanup in fixtures, process monitoring

## Success Metrics

- [ ] All existing unit tests continue to pass
- [ ] 20+ new integration test cases added
- [ ] Tests cover: connection, reads, writes, errors, multi-slave
- [ ] CI/CD pipeline runs PTY tests successfully
- [ ] Test execution time < 60 seconds
- [ ] Code coverage maintained or improved
- [ ] Documentation updated with testing instructions

## Deliverables

1. **Modbus Slave Simulator** (`tests/modbus_slave_simulator.py`)
2. **PTY Manager** (`tests/pty_manager.py`)
3. **pytest fixtures** (`tests/conftest.py`)
4. **Integration test suite**:
   - `tests/test_integration_pty_connection.py`
   - `tests/test_integration_pty_full.py`
   - `tests/test_integration_pty_errors.py`
   - `tests/test_integration_pty_multislave.py`
5. **CI/CD workflow** (`.github/workflows/integration-tests.yml`)
6. **Documentation updates**:
   - `docs/BUILD.md` - Add integration testing section
   - `README.md` - Add testing quick start

## Timeline Estimate

- **Phase 1** (Infrastructure): 8-12 hours
  - Modbus simulator: 4-6 hours
  - PTY manager: 2-3 hours
  - Fixtures: 2-3 hours

- **Phase 2** (Test Suite): 12-16 hours
  - Connection tests: 3-4 hours
  - Full integration tests: 5-6 hours
  - Error scenario tests: 4-6 hours

- **Phase 3** (CI/CD): 4-6 hours
  - GitHub Actions setup: 2-3 hours
  - Testing and refinement: 2-3 hours

**Total**: 24-34 hours

## Next Steps

1. **Review and approval** of this plan
2. **Implement Phase 1** (Infrastructure)
3. **Implement Phase 2** (Test Suite)
4. **Implement Phase 3** (CI/CD)
5. **Documentation updates**
6. **Final testing and validation**

---

**Status**: Draft - Ready for review and implementation
