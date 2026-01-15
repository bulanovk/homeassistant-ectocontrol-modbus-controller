import pytest

from unittest.mock import patch, MagicMock

from custom_components.ectocontrol_modbus_controller.boiler_gateway import BoilerGateway
from custom_components.ectocontrol_modbus_controller.coordinator import BoilerDataUpdateCoordinator


class DummyProtocol:
    def __init__(self, regs=None):
        # regs should be a list of ints length 23
        self._regs = regs or [i for i in range(23)]

    async def read_registers(self, slave_id, start_addr, count, timeout=None):
        # Handle both the main data read (0x0010, 23) and circuit enable read (0x0039, 1)
        if start_addr == 0x0010:
            assert count == 23
            return list(self._regs[:count])
        elif start_addr == 0x0039:
            assert count == 1
            return [0x01]  # Return circuit enable register value
        else:
            raise AssertionError(f"Unexpected address: 0x{start_addr:04X}")


@pytest.mark.asyncio
async def test_coordinator_updates_gateway_cache():
    proto = DummyProtocol(regs=[100 + i for i in range(23)])
    gw = BoilerGateway(proto, slave_id=7)

    # Mock frame.report_usage to avoid "Frame helper not set up" error in HA 2025.12+
    with patch("homeassistant.helpers.frame.report_usage"):
        coord = BoilerDataUpdateCoordinator(hass=MagicMock(), gateway=gw, name="test")

        data = await coord._async_update_data()

        # verify returned mapping and gateway cache
        assert isinstance(data, dict)
        assert gw.cache == data
        assert data[0x0010] == 100
        assert data[0x0010 + 22] == 100 + 22
