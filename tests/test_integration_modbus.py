"""Integration-style tests mocking modbus_tk RtuMaster for end-to-end flows.

This test patches `modbus_tk.modbus_rtu.RtuMaster` to simulate a device
responding to read/write requests for the register block 0x0010..0x0026.

It then calls `async_setup_entry` to create protocol/gateway/coordinator,
triggers a coordinator update, and asserts that entity getters return
expected values.
"""
import asyncio
import pytest
from unittest.mock import MagicMock, patch

from custom_components.ectocontrol_modbus_controller.const import DOMAIN, CONF_PORT, CONF_SLAVE_ID


def _fake_run_callback_threadsafe(loop, callback):
    """Fake run_callback_threadsafe that just runs the callback."""
    from concurrent.futures import Future
    future = Future()
    try:
        callback()
        future.set_result(None)
    except Exception as e:
        future.set_exception(e)
    return future


class FakeDeviceEntry:
    def __init__(self):
        self.id = "test_device_id"


class FakeDeviceRegistry:
    def __init__(self):
        self._devices = {}

    def async_get_or_create(self, **kwargs):
        entry = FakeDeviceEntry()
        self._devices[entry.id] = entry
        return entry

    def async_get_device(self, identifiers=None, connections=None):
        return None

    def async_update_device(self, device_id, **kwargs):
        pass


class FakeRtuMaster:
    def __init__(self, serial):
        # store last write calls
        self._writes = []
        self._timeout = None

    def execute(self, slave, function_code, address, quantity_or_value=None, unit=None):
        # Simplified execute behavior mapping to our ModbusProtocol wrapper
        # We'll support reading holding registers (function_code 3) and writing single register (16 simulated)
        if function_code == 3:
            # return a list of register values for the requested block
            # simulate registers 0x0010..0x0026 = 23 registers
            # We'll return a deterministic pattern so tests can assert values
            count = quantity_or_value
            base = address

            # Special handling for device info registers (0x0000-0x0003)
            if address == 0x0000 and count >= 4:
                # Return valid boiler device type (0x14) with UID in valid range
                return [
                    0x0000,  # Reserved
                    0x8ABC,  # UID high 16 bits
                    0xDE00,  # UID low 8 bits (0xDE in MSB)
                    0x1404,  # Device type 0x14, channel count 4
                ]

            return [base + i for i in range(count)]
        if function_code in (6, 16):
            # single or multiple writes
            self._writes.append((address, quantity_or_value))
            return True
        raise NotImplementedError("Function code not simulated: %s" % function_code)

    def set_timeout(self, timeout):
        self._timeout = timeout

    def open(self):
        return True

    def close(self):
        return True


@pytest.mark.asyncio
async def test_full_setup_and_coordinator_poll(tmp_path) -> None:
    """Run a full setup and coordinator poll with mocked RtuMaster."""
    # patch serial.Serial and modbus_tk.modbus_rtu.RtuMaster used in ModbusProtocol._connect_sync
    with patch("serial.Serial") as MockSerial, \
         patch("modbus_tk.modbus_rtu.RtuMaster", new=FakeRtuMaster), \
         patch("custom_components.ectocontrol_modbus_controller.dr.async_get") as mock_get_dr, \
         patch("homeassistant.helpers.frame._hass") as mock_frame_hass, \
         patch("homeassistant.helpers.frame.run_callback_threadsafe", _fake_run_callback_threadsafe):

        mock_get_dr.return_value = FakeDeviceRegistry()

        # import inside patch context to ensure classes use patched RtuMaster
        from custom_components.ectocontrol_modbus_controller import async_setup_entry
        from custom_components.ectocontrol_modbus_controller.modbus_protocol import ModbusProtocol
        from custom_components.ectocontrol_modbus_controller.boiler_gateway import BoilerGateway
        from custom_components.ectocontrol_modbus_controller.coordinator import BoilerDataUpdateCoordinator

        # prepare hass-like dicts/mocks
        class FakeHass:
            def __init__(self):
                self.data = {DOMAIN: {}}
                self.services = MagicMock()
                self.config = MagicMock()
                self.config.config_dir = "/tmp/config"
                self.loop_thread_id = None
                self.loop = asyncio.get_event_loop()
                self.bus = MagicMock()
                self.bus.async_listen_once = MagicMock()

        hass = FakeHass()
        mock_frame_hass.hass = hass

        # Initialize protocol manager (normally done in async_setup)
        from custom_components.ectocontrol_modbus_controller.modbus_protocol_manager import ModbusProtocolManager
        hass.data[DOMAIN]["protocol_manager"] = ModbusProtocolManager()

        # create a fake config entry object
        class FakeEntry:
            def __init__(self, entry_id="entry1", port="/dev/ttyUSB0", slave=1):
                self.entry_id = entry_id
                self.data = {CONF_PORT: port, CONF_SLAVE_ID: slave}
                self._unload_callbacks = []

            async def async_on_unload(self, callback):
                """Register an unload callback."""
                self._unload_callbacks.append(callback)

        entry = FakeEntry()

        # run setup
        result = await async_setup_entry(hass, entry)
        assert result is True

        # retrieve created components
        inst = hass.data[DOMAIN][entry.entry_id]
        gateway: BoilerGateway = inst["gateway"]
        coordinator: BoilerDataUpdateCoordinator = inst["coordinator"]
        # Protocol is managed by protocol manager, get it from there
        protocol = await hass.data[DOMAIN]["protocol_manager"].get_protocol(port=entry.data[CONF_PORT])

        # ensure we can connect via protocol (which uses FakeRtuMaster behind the scenes)
        await protocol.connect()
        # read a block directly via gateway protocol to simulate coordinator read
        regs = await protocol.read_registers(entry.data[CONF_SLAVE_ID], 0x0010, 23)
        assert len(regs) == 23
        # values are base+offset as implemented in FakeRtuMaster.execute
        assert regs[0] == 0x0010
        assert regs[-1] == 0x0010 + 22

        # put some data into gateway cache as coordinator would do
        gateway.cache = {0x0010 + i: regs[i] for i in range(len(regs))}

        # validate some gateway getters map correctly
        # get_ch_temperature expects raw register to be interpreted; our fake returns integer base
        ch_temp = gateway.get_ch_temperature()
        assert isinstance(ch_temp, (int, float))

        # trigger coordinator update cycle to exercise _async_update_data
        data = await coordinator._async_update_data()
        # data should be a dict with keys 0x0010..0x0026
        assert isinstance(data, dict)
        assert 0x0010 in data
        assert data[0x0010] == 0x0010

        # test write path: set CH setpoint through gateway uses protocol.write_registers
        # ensure protocol.write_registers doesn't raise
        await gateway.set_ch_setpoint(30.0)

        await protocol.disconnect()
