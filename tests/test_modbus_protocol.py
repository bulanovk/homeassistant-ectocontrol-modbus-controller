import asyncio
from unittest.mock import MagicMock, patch, call

import pytest
import modbus_tk.defines as cst
import modbus_tk.modbus

from custom_components.ectocontrol_modbus_controller.modbus_protocol import ModbusProtocol


@pytest.mark.asyncio
async def test_connect_and_disconnect(monkeypatch):
    mock_master = MagicMock()
    mock_master.open = MagicMock()
    mock_master.close = MagicMock()

    async def fake_connect(self):
        return True

    # Patch _connect_sync to return our mock master
    with patch.object(ModbusProtocol, "_connect_sync", return_value=mock_master):
        protocol = ModbusProtocol("/dev/ttyUSB0")
        ok = await protocol.connect()
        assert ok
        assert protocol.is_connected
        await protocol.disconnect()
        assert not protocol.is_connected


@pytest.mark.asyncio
async def test_read_registers_returns_list(monkeypatch):
    protocol = ModbusProtocol("/dev/ttyUSB0")
    mock_master = MagicMock()
    # execute should return a sequence of ints
    mock_master.execute = MagicMock(return_value=(291,))
    protocol.client = mock_master

    res = await protocol.read_registers(1, 0x0018, 1)
    assert res == [291]


@pytest.mark.asyncio
async def test_write_register_uses_multiple_registers_function():
    """Test that write_register uses WRITE_MULTIPLE_REGISTERS (0x10) with single value.

    WRITE_MULTIPLE_REGISTERS is used instead of WRITE_SINGLE_REGISTER (0x06) for
    better adapter compatibility, as some adapters don't support function 0x06.
    """
    protocol = ModbusProtocol("/dev/ttyUSB0")
    mock_master = MagicMock()
    mock_master.execute = MagicMock()
    protocol.client = mock_master

    # Write a single register
    result = await protocol.write_register(1, 0x0031, 220)

    # Verify the write succeeded
    assert result is True

    # Verify execute was called with WRITE_MULTIPLE_REGISTERS (0x10)
    mock_master.execute.assert_called_once()
    args = mock_master.execute.call_args[0]
    assert args[0] == 1  # slave_id
    assert args[1] == cst.WRITE_MULTIPLE_REGISTERS  # function code 0x10
    assert args[2] == 0x0031  # register address
    assert args[3] == 1  # quantity = 1 register
    assert args[4] == [220]  # list with single value


@pytest.mark.asyncio
async def test_write_register_suppresses_error_when_verify_response_false():
    """Test that write_register returns True on error if verify_response is False."""
    protocol = ModbusProtocol("/dev/ttyUSB0")
    mock_master = MagicMock()
    # Simulate an error (e.g. invalid response length 0)
    mock_master.execute.side_effect = modbus_tk.modbus.ModbusInvalidResponseError("Response length is invalid 0")
    protocol.client = mock_master

    # Should return True because verify_response=False
    result = await protocol.write_register(1, 0x0080, 2, verify_response=False)
    assert result is True

    # Should return False if verify_response=True (default)
    mock_master.execute.side_effect = modbus_tk.modbus.ModbusInvalidResponseError("Response length is invalid 0")
    result = await protocol.write_register(1, 0x0080, 2, verify_response=True)
    assert result is False
