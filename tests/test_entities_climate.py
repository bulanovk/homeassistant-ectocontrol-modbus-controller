"""Tests for the BoilerClimate and DHWClimate entities."""
from homeassistant.components.climate import HVACAction, HVACMode

from custom_components.ectocontrol_modbus_controller.climate import BoilerClimate, DHWClimate
import pytest


class FakeGateway:
    """Fake gateway for testing."""

    def __init__(self):
        self.slave_id = 1
        self.last_set_raw = None
        self.circuit_written = None
        self.device_uid = 0x8ABCDEF  # Test UID (24-bit value in range 0x800000-0xFFFFFF)
        # Add protocol mock for device_info tests
        self.protocol = type('obj', (object,), {'port': 'mock_port'})
        # Initialize shared cache
        self._ch_setpoint_cache = None

    def get_device_uid_hex(self):
        """Return UID as hex string."""
        if self.device_uid is None:
            return None
        return f"{self.device_uid:06x}"

    def get_ch_temperature(self):
        return 19.5

    def get_ch_setpoint(self):
        return 21.0

    def get_ch_min_limit(self):
        return 30.0

    def get_ch_max_limit(self):
        return 80.0

    def get_burner_on(self):
        return True

    def get_heating_enabled(self):
        return False

    def get_dhw_temperature(self):
        return 45.0

    def get_dhw_setpoint(self):
        return 50.0

    def get_dhw_min_limit(self):
        return 30.0

    def get_dhw_max_limit(self):
        return 65.0

    def get_dhw_enable_switch(self):
        return True

    async def set_ch_setpoint(self, raw):
        self.last_set_raw = raw
        return True

    async def set_dhw_setpoint(self, raw):
        self.last_set_dhw_raw = raw
        return True

    async def set_circuit_enable_bit(self, bit, enabled):
        self.circuit_written = (bit, enabled)
        return True


class DummyCoordinator:
    """Dummy coordinator for testing."""

    def __init__(self, gateway):
        self.gateway = gateway
        self.last_update_success = True  # Add for availability tests

    async def async_request_refresh(self):
        self.refreshed = True


def test_climate_properties() -> None:
    """Test climate entity properties."""
    gw = FakeGateway()
    coord = DummyCoordinator(gw)

    c = BoilerClimate(coord)
    assert c.current_temperature == 19.5
    assert c.target_temperature == 21.0
    # hvac_action should be HEATING when burner_on True
    assert c.hvac_action.name.lower() == "heating"
    # verify min/max temperature settings for UI slider (from gateway)
    assert c.min_temp == 30.0
    assert c.max_temp == 80.0
    assert c.target_temperature_step == 1


def test_climate_properties_with_none_limits() -> None:
    """Test climate entity with None min/max limits (fallback values)."""
    gw = FakeGateway()
    # Override to return None (simulating unsupported/unavailable)
    gw.get_ch_min_limit = lambda: None
    gw.get_ch_max_limit = lambda: None
    coord = DummyCoordinator(gw)

    c = BoilerClimate(coord)
    # Should fallback to default values when None
    assert c.min_temp == 5.0
    assert c.max_temp == 85.0


def test_climate_target_temperature_fallback() -> None:
    """Test climate entity returns fallback target temperature when get_ch_setpoint returns None."""
    gw = FakeGateway()
    # Override to return None (simulating unavailable setpoint)
    gw.get_ch_setpoint = lambda: None
    coord = DummyCoordinator(gw)

    c = BoilerClimate(coord)
    # Should return midpoint of min/max temp as fallback
    expected_fallback = (c.min_temp + c.max_temp) / 2
    assert c.target_temperature == expected_fallback


@pytest.mark.asyncio
async def test_climate_set_temperature_and_mode() -> None:
    """Test climate set_temperature and set_hvac_mode actions."""
    gw = FakeGateway()
    coord = DummyCoordinator(gw)

    c = BoilerClimate(coord)

    await c.async_set_temperature(temperature=23.2)
    # climate uses raw = int(round(temp * 10)) per implementation
    assert gw.last_set_raw == int(round(23.2 * 10))

    # set hvac mode to HEAT should enable circuit bit 0
    await c.async_set_hvac_mode(c._attr_hvac_modes[0])
    assert gw.circuit_written == (0, True)


@pytest.mark.asyncio
async def test_climate_temperature_persists_when_register_unavailable() -> None:
    """Test that set temperature persists even when register returns None (GitHub issue)."""
    gw = FakeGateway()

    # Mock set_ch_setpoint to update the gateway cache
    original_set = gw.set_ch_setpoint
    async def mock_set_ch_setpoint(raw):
        gw._ch_setpoint_cache = raw / 10.0  # Update gateway cache
        return await original_set(raw)
    gw.set_ch_setpoint = mock_set_ch_setpoint

    # Simulate register being unavailable (returns cached value)
    gw.get_ch_setpoint = lambda: gw._ch_setpoint_cache
    coord = DummyCoordinator(gw)

    c = BoilerClimate(coord)

    # Initially should return fallback (midpoint of min/max) when cache is None
    initial_temp = c.target_temperature
    expected_fallback = (c.min_temp + c.max_temp) / 2
    assert initial_temp == expected_fallback

    # User sets temperature to 55.0
    await c.async_set_temperature(temperature=55.0)

    # Gateway cache should be updated
    assert gw._ch_setpoint_cache == 55.0

    # Target temperature should now return 55.0 (from gateway cache), not the fallback
    assert c.target_temperature == 55.0

    # Simulate card close/reopen by creating a new read
    # Still should return 55.0, not fallback to 45.0
    assert c.target_temperature == 55.0

    # Verify the write was actually sent to the gateway
    assert gw.last_set_raw == int(round(55.0 * 10))


@pytest.mark.asyncio
async def test_climate_temperature_cache_updates_when_register_available() -> None:
    """Test that gateway cache updates when register becomes available after being None."""
    gw = FakeGateway()

    # Mock set_ch_setpoint to update the gateway cache
    original_set = gw.set_ch_setpoint
    async def mock_set_ch_setpoint(raw):
        gw._ch_setpoint_cache = raw / 10.0  # Update gateway cache
        return await original_set(raw)
    gw.set_ch_setpoint = mock_set_ch_setpoint

    # Start with register unavailable
    gw.get_ch_setpoint = lambda: gw._ch_setpoint_cache
    coord = DummyCoordinator(gw)

    c = BoilerClimate(coord)

    # User sets temperature when register is unavailable
    await c.async_set_temperature(temperature=60.0)
    # Gateway cache should be updated by set_ch_setpoint
    assert gw._ch_setpoint_cache == 60.0
    # Climate should read from gateway cache
    assert c.target_temperature == 60.0

    # Now simulate register becoming available with different value
    # (e.g., boiler actually set to 65.0)
    # Update gateway cache directly (simulating coordinator refresh)
    gw._ch_setpoint_cache = 65.0
    # Climate should read the updated gateway cache value
    assert c.target_temperature == 65.0

    # Gateway cache should persist
    assert gw._ch_setpoint_cache == 65.0


# ========== DHW Climate Tests ==========


def test_dhw_climate_properties() -> None:
    """Test DHW climate entity properties."""
    gw = FakeGateway()
    coord = DummyCoordinator(gw)

    c = DHWClimate(coord)
    assert c.current_temperature == 45.0
    assert c.target_temperature == 50.0
    assert c.hvac_action == HVACAction.HEATING
    assert c.min_temp == 30.0
    assert c.max_temp == 65.0
    assert c.target_temperature_step == 1


def test_dhw_climate_properties_with_none_limits() -> None:
    """Test DHW climate entity with None min/max limits (fallback values)."""
    gw = FakeGateway()
    # Override to return None (simulating unsupported/unavailable)
    gw.get_dhw_min_limit = lambda: None
    gw.get_dhw_max_limit = lambda: None
    coord = DummyCoordinator(gw)

    c = DHWClimate(coord)
    # Should fallback to default values when None
    assert c.min_temp == 30.0
    assert c.max_temp == 65.0


def test_dhw_climate_target_temperature_fallback() -> None:
    """Test DHW climate entity returns fallback target temperature when get_dhw_setpoint returns None."""
    gw = FakeGateway()
    # Override to return None (simulating unavailable setpoint)
    gw.get_dhw_setpoint = lambda: None
    coord = DummyCoordinator(gw)

    c = DHWClimate(coord)
    # Should return midpoint of min/max temp as fallback
    expected_fallback = (c.min_temp + c.max_temp) / 2
    assert c.target_temperature == expected_fallback


@pytest.mark.asyncio
async def test_dhw_climate_set_temperature_and_mode() -> None:
    """Test DHW climate set_temperature and set_hvac_mode actions."""
    gw = FakeGateway()
    coord = DummyCoordinator(gw)

    c = DHWClimate(coord)

    await c.async_set_temperature(temperature=55.0)
    # DHW uses raw = int(temp) & 0xFF per implementation
    assert gw.last_set_dhw_raw == 55

    # set hvac mode to HEAT should enable circuit bit 1
    await c.async_set_hvac_mode(HVACMode.HEAT)
    assert gw.circuit_written == (1, True)

    # set hvac mode to OFF should disable circuit bit 1
    await c.async_set_hvac_mode(HVACMode.OFF)
    assert gw.circuit_written == (1, False)


def test_dhw_climate_hvac_mode() -> None:
    """Test DHW climate hvac_mode property."""
    gw = FakeGateway()
    coord = DummyCoordinator(gw)

    c = DHWClimate(coord)

    # When DHW enable switch is True
    assert c.hvac_mode == HVACMode.HEAT

    # When DHW enable switch is False
    gw.get_dhw_enable_switch = lambda: False
    assert c.hvac_mode == HVACMode.OFF


def test_dhw_climate_hvac_action() -> None:
    """Test DHW climate hvac_action property."""
    gw = FakeGateway()
    coord = DummyCoordinator(gw)

    c = DHWClimate(coord)

    # When DHW enable switch is True
    assert c.hvac_action == HVACAction.HEATING

    # When DHW enable switch is False
    gw.get_dhw_enable_switch = lambda: False
    assert c.hvac_action == HVACAction.IDLE
