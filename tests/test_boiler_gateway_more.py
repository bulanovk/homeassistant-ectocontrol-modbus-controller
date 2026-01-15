import pytest

from custom_components.ectocontrol_modbus_controller.boiler_gateway import BoilerGateway


class FakeProto:
    def __init__(self):
        self.writes = []
        self.reads = {}

    async def write_register(self, slave_id, addr, value, **kwargs):
        self.writes.append((slave_id, addr, value, kwargs))
        return True

    async def read_registers(self, slave_id, addr, count):
        # return configured read value or zeros
        return [self.reads.get(addr, 0)]


@pytest.mark.asyncio
async def test_boiler_gateway_edge_cases_and_writes():
    proto = FakeProto()
    gw = BoilerGateway(proto, slave_id=5)

    # pressure lsb 0xFF -> None
    gw.cache = {0x001A: 0xFF}
    assert gw.get_pressure() is None

    # flow lsb 0xFF -> None
    gw.cache = {0x001B: 0xFF}
    assert gw.get_flow_rate() is None

    # modulation lsb 0xFF -> None
    gw.cache = {0x001C: 0xFF}
    assert gw.get_modulation_level() is None

    # states bits: ensure bits parsed correctly
    gw.cache = {0x001D: 0b00000110}  # burner off, heating on, dhw on
    assert gw.get_burner_on() is False
    assert gw.get_heating_enabled() is True
    assert gw.get_dhw_enabled() is True

    # main/additional error 0xFFFF -> None
    gw.cache = {0x001E: 0xFFFF, 0x001F: 0xFFFF}
    assert gw.get_main_error() is None
    assert gw.get_additional_error() is None

    # outdoor temp 0x7F -> None
    gw.cache = {0x0020: (0x7F << 8)}
    assert gw.get_outdoor_temperature() is None

    # outdoor negative -5 -> 0xFB as msb
    gw.cache = {0x0020: (0xFB << 8)}
    assert gw.get_outdoor_temperature() == -5

    # ch setpoint active negative: raw >= 0x8000
    gw.cache = {0x0026: 0xFF00}  # -256 -> -1.0
    assert gw.get_ch_setpoint_active() == pytest.approx(-1.0)

    # ch setpoint active invalid marker
    gw.cache = {0x0026: 0x7FFF}
    assert gw.get_ch_setpoint_active() is None

    # test write helpers
    ok = await gw.set_ch_setpoint(123)
    assert ok is True
    assert proto.writes[-1][0] == 5
    assert proto.writes[-1][1] == 0x0031
    assert proto.writes[-1][2] == 123
    assert proto.writes[-1][3].get('verify_response') is False

    # test set_circuit_enable_bit uses cached value for read-modify-write
    gw.cache = {0x0039: 0x0001}  # bit 0 already set
    ok2 = await gw.set_circuit_enable_bit(2, True)
    assert ok2 is True
    # reboot and reset commands
    ok3 = await gw.reboot_adapter()
    assert proto.writes[-1][1] == 0x0080
    assert proto.writes[-1][2] == 2
    assert proto.writes[-1][3].get('verify_response') is False

    ok4 = await gw.reset_boiler_errors()
    assert proto.writes[-1][1] == 0x0080
    assert proto.writes[-1][2] == 3
    # reset errors also uses verify_response=False (both commands read result register separately)
    assert proto.writes[-1][3].get('verify_response') is False
    assert ok3 is True and ok4 is True


def test_is_boiler_connected_logic():
    """Test boiler connection status bit interpretation.

    Per Russian documentation (verified correct):
    - Bit 3 = 0: No response from boiler (disconnected)
    - Bit 3 = 1: Response received from boiler (connected)
    """
    class DummyProtocol:
        pass
    gw = BoilerGateway(DummyProtocol(), slave_id=1)

    # 1. No data in cache -> None
    assert gw.get_is_boiler_connected() is None

    # 2. Bit 3 clear (0x0000) -> No response -> False
    gw.cache = {0x0010: 0x0000}
    assert gw.get_is_boiler_connected() is False

    # 3. Bit 3 set (0x0008) -> Response received -> True
    gw.cache = {0x0010: 0x0008}
    assert gw.get_is_boiler_connected() is True

    # 4. Other bits set (e.g. 0x1000 or 0x0800) shouldn't affect it
    gw.cache = {0x0010: 0x1800}  # Bit 12 and Bit 11 set, Bit 3 clear
    assert gw.get_is_boiler_connected() is False

    gw.cache = {0x0010: 0x1808}  # Bit 12, Bit 11, and Bit 3 set
    assert gw.get_is_boiler_connected() is True
