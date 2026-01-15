"""Tests for entity platforms covering missing branches."""
import pytest

from custom_components.ectocontrol_modbus_controller.sensor import BoilerSensor
from custom_components.ectocontrol_modbus_controller.binary_sensor import BoilerBinarySensor
from custom_components.ectocontrol_modbus_controller.switch import CircuitSwitch


class DummyCoordinator:
    """Dummy coordinator for testing."""

    def __init__(self, gateway):
        self.gateway = gateway
        self.last_update_success = True  # Add for availability tests

    async def async_request_refresh(self):
        pass


class DummyGateway:
    """Dummy gateway for testing."""

    def __init__(self):
        self.slave_id = 1
        self.cache = {}
        self.device_uid = 0x8ABCDEF  # Test UID (24-bit value in range 0x800000-0xFFFFFF)
        # Add protocol mock for device_info tests
        self.protocol = type('obj', (object,), {'port': 'mock_port'})

    def get_device_uid_hex(self):
        """Return UID as hex string."""
        if self.device_uid is None:
            return None
        return f"{self.device_uid:06x}"

    def get_pressure(self):
        return None

    def get_flow_rate(self):
        return None

    def get_ch_temperature(self):
        return 20.0

    def get_burner_on(self):
        return False

    def get_heating_enabled(self):
        return True

    def get_dhw_enabled(self):
        return False

    def get_heating_enable_switch(self):
        return True

    def get_dhw_enable_switch(self):
        return False


def test_sensor_entity_attributes() -> None:
    """Test sensor entity attributes and unique_id."""
    gw = DummyGateway()
    coord = DummyCoordinator(gw)

    sensor = BoilerSensor(coord, "get_ch_temperature", "Test", "°C")
    assert sensor._attr_name == "Test"
    assert sensor._attr_native_unit_of_measurement == "°C"
    assert "get_ch_temperature" in sensor.unique_id


def test_binary_sensor_entity_attributes() -> None:
    """Test binary sensor entity attributes and unique_id."""
    gw = DummyGateway()
    coord = DummyCoordinator(gw)

    binary = BoilerBinarySensor(coord, "get_burner_on", "Burner")
    assert binary._attr_name == "Burner"
    assert "get_burner_on" in binary.unique_id


def test_switch_entity_cache_none() -> None:
    """Test switch when cache register is None."""
    gw = DummyGateway()
    coord = DummyCoordinator(gw)
    gw.cache = {}  # 0x001D not in cache

    switch = CircuitSwitch(coord, bit=1)
    assert switch.is_on is None


@pytest.mark.asyncio
async def test_switch_turn_on() -> None:
    """Test switch turn_on calls set_circuit_enable_bit."""
    gw = DummyGateway()
    gw.last_bit_call = None

    async def fake_set_bit(bit, enabled):
        gw.last_bit_call = (bit, enabled)
        return True

    gw.set_circuit_enable_bit = fake_set_bit
    coord = DummyCoordinator(gw)

    switch = CircuitSwitch(coord, bit=1)
    await switch.async_turn_on()
    assert gw.last_bit_call == (1, True)


def test_switch_with_state_getter() -> None:
    """Test switch uses state_getter lambda instead of reading cache directly."""
    gw = DummyGateway()
    coord = DummyCoordinator(gw)

    # Heating Enable switch (bit 0) should use get_heating_enable_switch()
    heating_switch = CircuitSwitch(
        coord, bit=0, name="Heating Enable",
        state_getter=lambda g: g.get_heating_enable_switch()
    )
    assert heating_switch.is_on is True  # get_heating_enable_switch returns True

    # DHW Enable switch (bit 1) should use get_dhw_enable_switch()
    dhw_switch = CircuitSwitch(
        coord, bit=1, name="DHW Enable",
        state_getter=lambda g: g.get_dhw_enable_switch()
    )
    assert dhw_switch.is_on is False  # get_dhw_enable_switch returns False

    # When state_getter returns None, is_on should return None
    def getter_returning_none(g):
        return None

    none_switch = CircuitSwitch(
        coord, bit=0, state_getter=getter_returning_none
    )
    assert none_switch.is_on is None
