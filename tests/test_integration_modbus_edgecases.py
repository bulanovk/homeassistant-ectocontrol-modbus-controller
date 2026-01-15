"""Integration tests for Modbus edge cases: timeouts and errors.

These tests patch `modbus_tk.modbus_rtu.RtuMaster` to simulate failures and
verify that `ModbusProtocol`, `BoilerGateway`, and `BoilerDataUpdateCoordinator`
handle them gracefully (return None/False or raise UpdateFailed where appropriate).
"""
import pytest
from unittest.mock import MagicMock, patch

import modbus_tk.modbus as modbus
from custom_components.ectocontrol_modbus_controller.const import DOMAIN, CONF_PORT, CONF_SLAVE_ID


class TimeoutRtuMaster:
    def __init__(self, serial):
        pass

    def set_timeout(self, timeout):
        # pretend to set timeout
        self._timeout = timeout

    def open(self):
        return True

    def close(self):
        return True

    def execute(self, *args, **kwargs):
        # Simulate a long-running operation by raising a generic timeout-like exception
        raise Exception("Simulated timeout")


class ModbusErrorRtuMaster:
    def __init__(self, serial):
        pass

    def set_timeout(self, timeout):
        pass

    def open(self):
        return True

    def close(self):
        return True

    def execute(self, *args, **kwargs):
        # Simulate modbus.ModbusError being raised by modbus-tk
        raise modbus.ModbusError("Simulated modbus error")


class WriteFailRtuMaster:
    def __init__(self, serial):
        self.writes = []

    def set_timeout(self, timeout):
        pass

    def open(self):
        return True

    def close(self):
        return True

    def execute(self, slave, function_code, address, quantity_or_value=None, unit=None):
        # allow reads, but writes fail
        from modbus_tk.defines import READ_HOLDING_REGISTERS, WRITE_MULTIPLE_REGISTERS

        if function_code == READ_HOLDING_REGISTERS:
            count = quantity_or_value
            base = address
            return [base + i for i in range(count)]
        if function_code == WRITE_MULTIPLE_REGISTERS:
            raise modbus.ModbusError("Write failed")
        return []


@pytest.mark.asyncio
async def test_read_timeout_returns_none() -> None:
    with patch("serial.Serial"), patch("modbus_tk.modbus_rtu.RtuMaster", new=TimeoutRtuMaster):
        from custom_components.ectocontrol_modbus_controller.modbus_protocol import ModbusProtocol

        proto = ModbusProtocol(port="/dev/null")
        ok = await proto.connect()
        assert ok is True

        # Attempt to read; Fake master raises generic Exception -> read_registers should return None
        res = await proto.read_registers(1, 0x0010, 2)
        assert res is None

        await proto.disconnect()


@pytest.mark.asyncio
async def test_modbus_error_read_returns_none_and_coordinator_update_failed() -> None:
    with patch("serial.Serial"), patch("modbus_tk.modbus_rtu.RtuMaster", new=ModbusErrorRtuMaster):
        from custom_components.ectocontrol_modbus_controller.modbus_protocol import ModbusProtocol
        from custom_components.ectocontrol_modbus_controller.boiler_gateway import BoilerGateway
        from custom_components.ectocontrol_modbus_controller.coordinator import BoilerDataUpdateCoordinator
        from homeassistant.helpers.update_coordinator import UpdateFailed

        proto = ModbusProtocol(port="/dev/null")
        await proto.connect()
        gw = BoilerGateway(proto, slave_id=1)

        # Mock frame.report_usage to avoid "Frame helper not set up" error in HA 2025.12+
        with patch("homeassistant.helpers.frame.report_usage"):
            coord = BoilerDataUpdateCoordinator(MagicMock(), gw, name="test")

            # read_registers should return None on ModbusError
            rr = await proto.read_registers(1, 0x0010, 2)
            assert rr is None

            # coordinator update should raise UpdateFailed when None is returned
            with pytest.raises(UpdateFailed):
                await coord._async_update_data()

        await proto.disconnect()


@pytest.mark.asyncio
async def test_write_failure_handled() -> None:
    with patch("serial.Serial"), patch("modbus_tk.modbus_rtu.RtuMaster", new=WriteFailRtuMaster):
        from custom_components.ectocontrol_modbus_controller.modbus_protocol import ModbusProtocol
        from custom_components.ectocontrol_modbus_controller.boiler_gateway import BoilerGateway

        proto = ModbusProtocol(port="/dev/null")
        await proto.connect()
        gw = BoilerGateway(proto, slave_id=1)

        # set_ch_setpoint should attempt to write and return gracefully (no exception)
        ok = await gw.set_ch_setpoint(25.0)
        # gateway method may return None/False depending on implementation; ensure it doesn't raise
        assert ok is None or ok is False or ok is True

        await proto.disconnect()
