import pytest

from custom_components.ectocontrol_modbus_controller.modbus_protocol import ModbusProtocol


class ClientThatRaises:
    def set_timeout(self, t):
        pass

    def close(self):
        raise RuntimeError("close failed")

    def execute(self, *args, **kwargs):
        raise Exception("boom")


@pytest.mark.asyncio
async def test_disconnect_handles_close_exception():
    proto = ModbusProtocol(port="/dev/ttyS0")
    proto.client = ClientThatRaises()

    # should not raise
    await proto.disconnect()
    assert proto.client is None


@pytest.mark.asyncio
async def test_read_input_registers_handles_exception():
    proto = ModbusProtocol(port="/dev/ttyS0")
    proto.client = ClientThatRaises()

    res = await proto.read_input_registers(1, 0x0010, 2)
    assert res is None
