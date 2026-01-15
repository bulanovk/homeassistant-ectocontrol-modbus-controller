"""Tests for ModbusProtocol connect/disconnect and error paths."""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio

from custom_components.ectocontrol_modbus_controller.modbus_protocol import ModbusProtocol


class FakeSerial:
    def __init__(self):
        pass


class FakeRtuMaster:
    def __init__(self, ser):
        self.ser = ser
        self._timeout = 2.0
        self.opened = True

    def set_timeout(self, t):
        self._timeout = t

    def open(self):
        self.opened = True

    def close(self):
        self.opened = False

    def execute(self, slave, func, addr, count, *args):
        return tuple([i for i in range(count)])


@pytest.mark.asyncio
async def test_modbus_protocol_connect_sync_success(monkeypatch):
    """Test _connect_sync successfully creates and opens serial/RTU master."""
    # Mock serial.Serial and modbus_rtu.RtuMaster
    mock_serial = MagicMock()
    mock_master = MagicMock()

    def fake_serial_init(*args, **kwargs):
        return mock_serial

    def fake_rtu_master_init(ser):
        return mock_master

    monkeypatch.setattr("serial.Serial", fake_serial_init)
    monkeypatch.setattr("modbus_tk.modbus_rtu.RtuMaster", fake_rtu_master_init)

    proto = ModbusProtocol(port="/dev/ttyUSB0", baudrate=19200)

    # call _connect_sync
    result = proto._connect_sync()
    assert result == mock_master


@pytest.mark.asyncio
async def test_modbus_protocol_connect_failure(monkeypatch):
    """Test connect returns False when _connect_sync raises exception."""
    def fake_connect(*args, **kwargs):
        raise RuntimeError("Serial port open failed")

    monkeypatch.setattr("serial.Serial", fake_connect)

    proto = ModbusProtocol(port="/invalid")
    ok = await proto.connect()
    assert ok is False
    assert proto.client is None


@pytest.mark.asyncio
async def test_modbus_protocol_disconnect_with_exception(monkeypatch):
    """Test disconnect handles close() exceptions gracefully."""
    mock_client = MagicMock()

    def fake_close():
        raise RuntimeError("close failed")

    mock_client.close = fake_close
    proto = ModbusProtocol(port="/dev/ttyUSB0")
    proto.client = mock_client

    # should not raise
    await proto.disconnect()
    assert proto.client is None


@pytest.mark.asyncio
async def test_modbus_protocol_write_register_single(monkeypatch):
    """Test write_register calls write_registers with single value."""
    mock_client = MagicMock()
    mock_client.execute = MagicMock(return_value=None)

    proto = ModbusProtocol(port="/dev/ttyUSB0")
    proto.client = mock_client

    ok = await proto.write_register(slave_id=1, addr=0x0010, value=42)
    assert ok is True
    mock_client.execute.assert_called_once()
