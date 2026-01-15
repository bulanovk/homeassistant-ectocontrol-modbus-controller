import pytest

from unittest.mock import patch, MagicMock

from custom_components.ectocontrol_modbus_controller.boiler_gateway import BoilerGateway
from custom_components.ectocontrol_modbus_controller.coordinator import BoilerDataUpdateCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed


class ProtoNone:
    async def read_registers(self, *args, **kwargs):
        return None


@pytest.mark.asyncio
async def test_coordinator_raises_on_no_response():
    proto = ProtoNone()
    gw = BoilerGateway(proto, slave_id=9)

    # Mock frame.report_usage to avoid "Frame helper not set up" error in HA 2025.12+
    with patch("homeassistant.helpers.frame.report_usage"):
        coord = BoilerDataUpdateCoordinator(hass=MagicMock(), gateway=gw, name="test")

        with pytest.raises(UpdateFailed):
            await coord._async_update_data()
