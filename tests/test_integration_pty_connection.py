"""Integration tests for ModbusProtocol with virtual serial ports (socat PTY).

These tests use socat to create virtual serial port pairs, allowing
realistic testing of serial I/O without requiring physical hardware.
"""
from __future__ import annotations

import pytest
import logging

from custom_components.ectocontrol_modbus_controller.modbus_protocol import ModbusProtocol

_LOGGER = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.pty
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
    assert protocol.is_connected is False


@pytest.mark.asyncio
@pytest.mark.pty
async def test_connect_with_debug_mode(modbus_slave, pty_pair) -> None:
    """Test connecting with debug mode enabled."""
    master, slave = pty_pair

    protocol = ModbusProtocol(
        port=master,
        baudrate=19200,
        timeout=2.0,
        debug_modbus=True
    )

    result = await protocol.connect()
    assert result is True
    assert protocol.debug_modbus is True
    assert protocol._debug_serial is not None

    await protocol.disconnect()


@pytest.mark.asyncio
@pytest.mark.pty
async def test_read_device_info_registers(modbus_slave, pty_pair) -> None:
    """Test reading generic device info registers (0x0000-0x0003)."""
    master, slave = pty_pair

    protocol = ModbusProtocol(port=master, baudrate=19200, timeout=2.0)
    await protocol.connect()

    # Read generic device info
    regs = await protocol.read_registers(slave_id=1, start_addr=0x0000, count=4)

    assert regs is not None
    assert len(regs) == 4

    # Verify values match simulator defaults
    assert regs[0] == 0x0000  # Reserved
    assert regs[1] == 0x8ABC  # UID high
    assert regs[2] == 0xDE00  # UID low
    assert regs[3] == 0x1404  # Device type 0x14, channels 4

    await protocol.disconnect()


@pytest.mark.asyncio
@pytest.mark.pty
async def test_read_status_registers(modbus_slave, pty_pair) -> None:
    """Test reading status and diagnostics registers."""
    master, slave = pty_pair

    protocol = ModbusProtocol(port=master, baudrate=19200, timeout=2.0)
    await protocol.connect()

    # Read status block (0x0010-0x0013)
    regs = await protocol.read_registers(slave_id=1, start_addr=0x0010, count=4)

    assert regs is not None
    assert len(regs) == 4

    # Verify specific registers
    assert regs[0] == 0x0009  # STATUS: OpenTherm (0), boiler connected (bit 3)
    assert regs[1] == 0x012C  # VERSION: HW=1, SW=44

    await protocol.disconnect()


@pytest.mark.asyncio
@pytest.mark.pty
async def test_read_boiler_sensor_registers(modbus_slave, pty_pair) -> None:
    """Test reading boiler sensor registers."""
    master, slave = pty_pair

    protocol = ModbusProtocol(port=master, baudrate=19200, timeout=2.0)
    await protocol.connect()

    # Read boiler sensor block (0x0018-0x0020)
    regs = await protocol.read_registers(slave_id=1, start_addr=0x0018, count=9)

    assert regs is not None
    assert len(regs) == 9

    # Verify specific sensor values
    assert regs[0] == 0x00A6  # CH temp: 16.6°C
    assert regs[1] == 0x0158  # DHW temp: 34.8°C
    assert regs[2] == 0x0012  # Pressure: 1.8 bar (18 in LSB)
    assert regs[3] == 0x000E  # Flow: 1.4 L/min (14 in LSB)
    assert regs[4] == 0x0046  # Modulation: 70% (70 in LSB)

    await protocol.disconnect()


@pytest.mark.asyncio
@pytest.mark.pty
async def test_read_temperature_limits(modbus_slave, pty_pair) -> None:
    """Test reading temperature limit registers."""
    master, slave = pty_pair

    protocol = ModbusProtocol(port=master, baudrate=19200, timeout=2.0)
    await protocol.connect()

    # Read temperature limits (0x0033-0x0038)
    regs = await protocol.read_registers(slave_id=1, start_addr=0x0033, count=6)

    assert regs is not None
    assert len(regs) == 6

    # Verify limits
    assert regs[0] == 0x2300  # CH min: 35°C
    assert regs[1] == 0x5A00  # CH max: 90°C
    assert regs[2] == 0x2800  # DHW min: 40°C
    assert regs[3] == 0x4600  # DHW max: 70°C
    assert regs[4] == 0x3C00  # DHW setpoint: 60°C
    assert regs[5] == 0x6400  # Max modulation: 100%

    await protocol.disconnect()


@pytest.mark.asyncio
@pytest.mark.pty
async def test_read_full_block(modbus_slave, pty_pair) -> None:
    """Test reading a full block of registers (0x0010-0x0026)."""
    master, slave = pty_pair

    protocol = ModbusProtocol(port=master, baudrate=19200, timeout=2.0)
    await protocol.connect()

    # Read full block as coordinator would
    regs = await protocol.read_registers(slave_id=1, start_addr=0x0010, count=23)

    assert regs is not None
    assert len(regs) == 23

    # Verify first and last registers
    assert regs[0] == 0x0009  # STATUS
    assert regs[-1] == 0x3200  # CH setpoint active (50.0°C = 12800 / 256)

    await protocol.disconnect()


@pytest.mark.asyncio
@pytest.mark.pty
async def test_write_single_register(modbus_slave, pty_pair) -> None:
    """Test writing to a single register."""
    master, slave = pty_pair

    protocol = ModbusProtocol(port=master, baudrate=19200, timeout=2.0)
    await protocol.connect()

    # Write CH setpoint (0x0031)
    result = await protocol.write_register(
        slave_id=1,
        addr=0x0031,
        value=0x0C80,  # 50.0°C
    )

    # Give simulator time to process
    import asyncio
    await asyncio.sleep(0.1)

    assert result is True

    # Verify the simulator received the write
    updated_value = modbus_slave.get_register(0x0031)
    _LOGGER.info("After write, register 0x0031 = 0x%04X (expected 0x0C80)", updated_value if updated_value is not None else 0x0000)
    assert updated_value == 0x0C80

    await protocol.disconnect()


@pytest.mark.asyncio
@pytest.mark.pty
async def test_write_circuit_enable_register(modbus_slave, pty_pair) -> None:
    """Test writing to circuit enable register."""
    master, slave = pty_pair

    protocol = ModbusProtocol(port=master, baudrate=19200, timeout=2.0)
    await protocol.connect()

    # Read current value
    regs = await protocol.read_registers(slave_id=1, start_addr=0x0039, count=1)
    initial = regs[0] if regs else 0x0003

    _LOGGER.info("Initial circuit enable value: 0x%04X", initial)

    # Add delay to ensure simulator is ready
    import asyncio
    await asyncio.sleep(0.5)

    # Write new value (disable heating, enable DHW)
    result = await protocol.write_register(
        slave_id=1,
        addr=0x0039,
        value=0x0002,  # Only DHW enabled (bit 1)
    )

    import asyncio
    await asyncio.sleep(0.2)

    # Verify the write actually succeeded by checking the simulator
    updated = modbus_slave.get_register(0x0039)
    _LOGGER.info("Circuit enable after write: 0x%04X (expected 0x0002)", updated if updated is not None else 0x0000)
    
    # The write succeeded if the register was updated
    assert updated == 0x0002, f"Register not updated, got 0x{updated:04X}"

    await protocol.disconnect()


@pytest.mark.asyncio
@pytest.mark.pty
async def test_write_command_register(modbus_slave, pty_pair) -> None:
    """Test writing to command register."""
    master, slave = pty_pair

    protocol = ModbusProtocol(port=master, baudrate=19200, timeout=2.0)
    await protocol.connect()

    # Write to command register
    result = await protocol.write_register(
        slave_id=1,
        addr=0x0080,
        value=0x0002,  # Reboot command
    )
    assert result is True

    await protocol.disconnect()


@pytest.mark.asyncio
@pytest.mark.pty
async def test_concurrent_reads(modbus_slave, pty_pair) -> None:
    """Test concurrent read operations."""
    master, slave = pty_pair

    protocol = ModbusProtocol(port=master, baudrate=19200, timeout=2.0)
    await protocol.connect()

    # Launch multiple concurrent reads
    import asyncio

    async def read_task(addr: int, count: int):
        return await protocol.read_registers(slave_id=1, start_addr=addr, count=count)

    results = await asyncio.gather(
        read_task(0x0010, 4),  # Status
        read_task(0x0018, 5),  # Sensors
        read_task(0x0031, 3),  # Setpoints
    )

    # All reads should succeed
    assert all(r is not None for r in results)
    assert len(results[0]) == 4
    assert len(results[1]) == 5
    assert len(results[2]) == 3

    await protocol.disconnect()


@pytest.mark.asyncio
@pytest.mark.pty
async def test_reconnect_after_disconnect(modbus_slave, pty_pair) -> None:
    """Test disconnecting and reconnecting to the port."""
    master, slave = pty_pair

    protocol = ModbusProtocol(port=master, baudrate=19200, timeout=2.0)

    # First connection
    await protocol.connect()
    assert protocol.is_connected is True

    # Read some data
    regs = await protocol.read_registers(slave_id=1, start_addr=0x0010, count=4)
    assert regs is not None

    # Disconnect
    await protocol.disconnect()
    assert protocol.is_connected is False

    # Reconnect
    result = await protocol.connect()
    assert result is True
    assert protocol.is_connected is True

    # Read again
    regs = await protocol.read_registers(slave_id=1, start_addr=0x0010, count=4)
    assert regs is not None

    # Cleanup
    await protocol.disconnect()


@pytest.mark.asyncio
@pytest.mark.pty
async def test_read_with_custom_timeout(modbus_slave, pty_pair) -> None:
    """Test reading with a custom timeout value."""
    master, slave = pty_pair

    protocol = ModbusProtocol(port=master, baudrate=19200, timeout=2.0)
    await protocol.connect()

    # Read with shorter timeout
    regs = await protocol.read_registers(
        slave_id=1,
        start_addr=0x0010,
        count=4,
        timeout=0.5
    )
    assert regs is not None

    await protocol.disconnect()


@pytest.mark.asyncio
@pytest.mark.pty
async def test_simulator_statistics(modbus_slave, pty_pair) -> None:
    """Test that simulator correctly tracks request statistics."""
    master, slave = pty_pair

    protocol = ModbusProtocol(port=master, baudrate=19200, timeout=2.0)
    await protocol.connect()

    # Make several requests
    await protocol.read_registers(slave_id=1, start_addr=0x0010, count=4)
    await protocol.read_registers(slave_id=1, start_addr=0x0018, count=5)
    await protocol.read_registers(slave_id=1, start_addr=0x0031, count=3)

    # Check simulator statistics
    assert modbus_slave.request_count == 3

    await protocol.disconnect()
