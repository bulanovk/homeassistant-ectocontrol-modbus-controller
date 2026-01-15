import pytest
import asyncio

import modbus_tk.modbus as modbus

from custom_components.ectocontrol_modbus_controller.modbus_protocol import ModbusProtocol


@pytest.mark.asyncio
async def test_modbus_protocol_not_connected_returns_none_and_false():
    proto = ModbusProtocol(port="/dev/ttyS0")
    assert not proto.is_connected

    # read when not connected
    res = await proto.read_registers(1, 0x0010, 2)
    assert res is None

    # write when not connected
    ok = await proto.write_registers(1, 0x0010, [1, 2])
    assert ok is False


class FakeClient:
    def __init__(self, values=None, raise_modbus=False):
        self._values = values or [10, 20, 30]
        self.raise_modbus = raise_modbus

    def set_timeout(self, t):
        pass

    def close(self):
        pass

    def execute(self, slave, func, addr, count, *args):
        if self.raise_modbus:
            raise modbus.ModbusError("simulated")
        return tuple(self._values[:count])


@pytest.mark.asyncio
async def test_modbus_protocol_read_and_error_handling():
    proto = ModbusProtocol(port="/dev/ttyS0")
    proto.client = FakeClient(values=[1, 2, 3])

    res = await proto.read_registers(1, 0x0010, 3)
    assert res == [1, 2, 3]

    # simulate modbus error
    proto.client = FakeClient(raise_modbus=True)
    res2 = await proto.read_registers(1, 0x0010, 2)
    assert res2 is None
