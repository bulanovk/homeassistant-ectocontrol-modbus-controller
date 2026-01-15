"""Tests for Ectocontrol Modbus entities."""

import pytest

from custom_components.ectocontrol_modbus_controller.sensor import BoilerSensor
from custom_components.ectocontrol_modbus_controller.binary_sensor import BoilerBinarySensor
from custom_components.ectocontrol_modbus_controller.switch import CircuitSwitch


class FakeGateway:
    """Fake gateway for testing."""

    def __init__(self):
        self.slave_id = 1
        self.cache = {0x001D: 0}
        self.last_set_raw = None
        self.circuit_written = None
        self.device_uid = 0x8ABCDEF  # Test UID (24-bit value in range 0x800000-0xFFFFFF)
        self.device_type = 0x14  # OpenTherm Adapter v2
        self.channel_count = 1
        # Add protocol mock for device_info tests
        self.protocol = type('obj', (object,), {'port': 'mock_port'})

    def get_device_uid_hex(self):
        """Return UID as hex string."""
        if self.device_uid is None:
            return None
        return f"{self.device_uid:06x}"

    def get_device_info(self):
        from homeassistant.helpers.device_registry import DeviceInfo
        return DeviceInfo(
            identifiers={("ectocontrol_modbus_controller", f"uid_{self.get_device_uid_hex()}")},
            name="Ectocontrol Test Adapter",
            manufacturer="Ectostroy",
            model="Test Model (Type A)",
            sw_version="1.0",
            hw_version="2.0",
        )

    def get_ch_temperature(self):
        return 21.5

    def get_dhw_temperature(self):
        return 45.0

    def get_pressure(self):
        return 1.2

    def get_flow_rate(self):
        return 3.4

    def get_modulation_level(self):
        return 50

    def get_outdoor_temperature(self):
        return 10

    def get_ch_setpoint_active(self):
        return 22.0

    def get_ch_setpoint(self):
        return 22.0

    def get_manufacturer_code(self):
        return 0x1234

    def get_model_code(self):
        return 0x5678

    def get_main_error(self):
        return 0

    def get_additional_error(self):
        return 0

    def get_ot_error(self):
        return None

    def get_is_boiler_connected(self):
        return True

    async def set_ch_setpoint(self, raw):
        self.last_set_raw = raw
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


def test_boiler_sensor_native_values() -> None:
    """Test sensor native_value property returns correct data."""
    gw = FakeGateway()
    coord = DummyCoordinator(gw)

    s = BoilerSensor(coord, "get_ch_temperature", "CH Temp", "°C")
    assert s.native_value == 21.5
    assert s.unique_id.endswith("get_ch_temperature")

    s2 = BoilerSensor(coord, "get_manufacturer_code", "MFG", "")
    assert s2.native_value == 0x1234


def test_binary_sensor_is_on() -> None:
    """Test binary sensor is_on property."""
    gw = FakeGateway()
    gw.get_burner_on = lambda: True
    coord = DummyCoordinator(gw)

    b = BoilerBinarySensor(coord, "get_burner_on", "Burner")
    assert b.is_on is True


def test_boiler_connection_sensor() -> None:
    """Test boiler connection binary sensor logic."""
    from homeassistant.components.binary_sensor import BinarySensorDeviceClass
    gw = FakeGateway()
    coord = DummyCoordinator(gw)

    b = BoilerBinarySensor(coord, "get_is_boiler_connected", "Boiler Connection")
    assert b.is_on is True
    assert b.device_class == BinarySensorDeviceClass.CONNECTIVITY


@pytest.mark.asyncio
async def test_switch_turn_on_off_and_state() -> None:
    """Test switch turn on/off actions and state."""
    gw = FakeGateway()
    # set bit 1 in states (DHW Enable)
    gw.cache[0x001D] = 2
    coord = DummyCoordinator(gw)

    sw = CircuitSwitch(coord, bit=1)
    assert sw.is_on is True

    await sw.async_turn_off()
    assert gw.circuit_written == (1, False)

    await sw.async_turn_on()
    assert gw.circuit_written == (1, True)


def test_boiler_sensor_device_info() -> None:
    """Test entity has device_info for proper device association."""
    import importlib
    const = importlib.import_module("custom_components.ectocontrol_modbus_controller.const")

    gw = FakeGateway()
    coord = DummyCoordinator(gw)

    s = BoilerSensor(coord, "get_ch_temperature", "CH Temp", "°C")
    device_info = s.device_info

    assert device_info is not None
    # After UID-only refactoring, identifiers use UID format
    assert device_info["identifiers"] == {(const.DOMAIN, f"uid_{gw.get_device_uid_hex()}")}


def test_boiler_sensor_has_entity_name() -> None:
    """Test entity has _attr_has_entity_name set to True."""
    gw = FakeGateway()
    coord = DummyCoordinator(gw)

    s = BoilerSensor(coord, "get_ch_temperature", "CH Temp", "°C")
    assert s._attr_has_entity_name is True


def test_boiler_sensor_unavailable_when_coordinator_fails() -> None:
    """Test entity shows unavailable when coordinator last_update_success is False."""
    gw = FakeGateway()
    coord = DummyCoordinator(gw)
    coord.last_update_success = False

    s = BoilerSensor(coord, "get_ch_temperature", "CH Temp", "°C")
    assert s.available is False
