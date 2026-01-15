import pytest

from custom_components.ectocontrol_modbus_controller.boiler_gateway import BoilerGateway


def test_adapter_type_codes():
    """Test adapter type extraction from REGISTER_STATUS (0x0010 bits 0-2)."""
    class DummyProtocol:
        pass

    gw = BoilerGateway(DummyProtocol(), slave_id=1)

    # Test OpenTherm adapter (0x00)
    gw.cache = {0x0010: 0x0000}  # bits 0-2 = 000
    assert gw.get_adapter_type() == 0x00
    assert gw.get_adapter_type_name() == "OpenTherm"

    # Test eBus adapter (0x01)
    gw.cache = {0x0010: 0x0001}  # bits 0-2 = 001
    assert gw.get_adapter_type() == 0x01
    assert gw.get_adapter_type_name() == "eBus"

    # Test Navien adapter (0x02)
    gw.cache = {0x0010: 0x0002}  # bits 0-2 = 010
    assert gw.get_adapter_type() == 0x02
    assert gw.get_adapter_type_name() == "Navien"

    # Test reserved code (0x03)
    gw.cache = {0x0010: 0x0003}  # bits 0-2 = 011
    assert gw.get_adapter_type() == 0x03
    assert gw.get_adapter_type_name() == "Unknown (0x03)"

    # Test with other bits set in status register
    gw.cache = {0x0010: 0x0008}  # bit 3 set (comm status)
    assert gw.get_adapter_type() == 0x00  # bits 0-2 still 000

    # Test missing register
    gw.cache = {}
    assert gw.get_adapter_type() is None
    assert gw.get_adapter_type_name() is None


def test_boiler_communication_status_bit():
    """Test boiler communication status bit interpretation from REGISTER_STATUS (0x0010 bit 3).

    Per Russian documentation (verified correct):
    - Bit 3 = 0: No response from boiler (disconnected)
    - Bit 3 = 1: Response received from boiler (connected)

    Note: English documentation has this inverted, but Russian docs are correct.
    """
    class DummyProtocol:
        pass

    gw = BoilerGateway(DummyProtocol(), slave_id=1)

    # Test no response (bit 3 = 0) - boiler not connected
    gw.cache = {0x0010: 0x0000}  # bit 3 = 0
    assert gw.get_is_boiler_connected() is False

    # Test response received (bit 3 = 1) - boiler connected
    gw.cache = {0x0010: 0x0008}  # bit 3 = 1
    assert gw.get_is_boiler_connected() is True

    # Test with adapter type also set (bits 0-2 = 001 for eBus, bit 3 = 1)
    gw.cache = {0x0010: 0x0009}  # bits 0-2 = 001, bit 3 = 1
    assert gw.get_adapter_type() == 0x01
    assert gw.get_is_boiler_connected() is True

    # Test with adapter type but no response (bits 0-2 = 001, bit 3 = 0)
    gw.cache = {0x0010: 0x0001}  # bits 0-2 = 001, bit 3 = 0
    assert gw.get_adapter_type() == 0x01
    assert gw.get_is_boiler_connected() is False

    # Test missing register
    gw.cache = {}
    assert gw.get_is_boiler_connected() is None


def test_gateway_scaling_and_invalid_values():
    class DummyProtocol:
        pass

    gw = BoilerGateway(DummyProtocol(), slave_id=1)

    # prepare cache with example registers
    gw.cache = {
        0x0012: 0x0000,     # uptime high word = 0
        0x0013: 0x0010,     # uptime low word = 16
        0x0018: 291,        # CH temp = 29.1°C
        0x0019: 450,        # DHW = 45.0°C
        0x001A: 12,  # pressure LSB=12 -> 1.2 bar
        0x001B: 0,   # flow LSB=0 -> 0.0 L/min
        0x001C: 75,  # modulation 75%
        0x001D: 0x0003,     # bits 0 and 1 set
        0x001E: 0x0000,
        0x0020: (0x00 << 8),
        0x0021: 0x1234,
        0x0022: 0x5678,
        0x0026: 0x0100,     # setpoint raw = 256 -> 1.0°C (256/256)
    }

    assert gw.get_adapter_uptime() == 16
    assert gw.get_ch_temperature() == pytest.approx(29.1)
    assert gw.get_dhw_temperature() == pytest.approx(45.0)
    assert gw.get_pressure() == pytest.approx(1.2)
    assert gw.get_flow_rate() == pytest.approx(0.0)
    assert gw.get_modulation_level() == 75
    assert gw.get_burner_on() is True
    assert gw.get_heating_enabled() is True
    assert gw.get_dhw_enabled() is False
    assert gw.get_main_error() == 0
    assert gw.get_manufacturer_code() == 0x1234
    assert gw.get_model_code() == 0x5678
    assert gw.get_ch_setpoint_active() == pytest.approx(1.0)


def test_adapter_uptime_edge_cases():
    class DummyProtocol:
        pass

    gw = BoilerGateway(DummyProtocol(), slave_id=1)

    # Test 32-bit value combining
    gw.cache = {
        0x0012: 0x0001,     # high word = 1
        0x0013: 0x0000,     # low word = 0
    }
    # uptime = (1 << 16) | 0 = 65536 seconds
    assert gw.get_adapter_uptime() == 65536

    # Test invalid marker (0xFFFFFFFF)
    gw.cache = {
        0x0012: 0xFFFF,
        0x0013: 0xFFFF,
    }
    assert gw.get_adapter_uptime() is None

    # Test missing high register
    gw.cache = {
        0x0013: 0x0001,
    }
    assert gw.get_adapter_uptime() is None

    # Test missing low register
    gw.cache = {
        0x0012: 0x0001,
    }
    assert gw.get_adapter_uptime() is None

def test_adapter_uptime_formatted():
    """Test human-readable uptime formatting."""
    class DummyProtocol:
        pass

    gw = BoilerGateway(DummyProtocol(), slave_id=1)

    # Test minutes only
    gw.cache = {
        0x0012: 0x0000,
        0x0013: 300,      # 5 minutes
    }
    assert gw.get_adapter_uptime() == 300
    assert gw.get_adapter_uptime_formatted() == "5m"

    # Test hours and minutes
    gw.cache = {
        0x0012: 0x0000,
        0x0013: 3665,     # 1h 1m 5s
    }
    assert gw.get_adapter_uptime() == 3665
    assert gw.get_adapter_uptime_formatted() == "1h 1m"

    # Test days, hours, minutes
    gw.cache = {
        0x0012: 0x0000,
        0x0013: 183000,   # 2d 2h 50m
    }
    assert gw.get_adapter_uptime() == 183000
    assert gw.get_adapter_uptime_formatted() == "2d 2h 50m"

    # Test large uptime
    gw.cache = {
        0x0012: 0x0000,
        0x0013: 864000,   # 10d 0h 0m
    }
    assert gw.get_adapter_uptime() == 864000
    assert gw.get_adapter_uptime_formatted() == "10d"

    # Test None (invalid) - returns "0m" instead of None
    gw.cache = {
        0x0012: 0xFFFF,
        0x0013: 0xFFFF,
    }
    assert gw.get_adapter_uptime_formatted() == "0m"

    # Test empty cache - returns "0m" instead of None
    gw.cache = {}
    assert gw.get_adapter_uptime_formatted() == "0m"


def test_ot_error_sensor():
    """Test OpenTherm error sensor (only for OpenTherm adapters)."""
    class DummyProtocol:
        pass

    gw = BoilerGateway(DummyProtocol(), slave_id=1)

    # Test OpenTherm adapter (0x00) - should return error value
    gw.cache = {
        0x0010: 0x0000,     # Adapter type = OpenTherm
        0x0023: 0x0500,     # OT error = 5 (MSB = 0x05)
    }
    assert gw.get_ot_error() == 5

    # Test negative error value (signed i8)
    gw.cache = {
        0x0010: 0x0000,     # Adapter type = OpenTherm
        0x0023: 0xFE00,     # OT error = -2 (MSB = 0xFE)
    }
    assert gw.get_ot_error() == -2

    # Test invalid marker (0x7F)
    gw.cache = {
        0x0010: 0x0000,     # Adapter type = OpenTherm
        0x0023: 0x7F00,     # OT error = 0x7F (invalid)
    }
    assert gw.get_ot_error() is None

    # Test eBus adapter (0x01) - should return None
    gw.cache = {
        0x0010: 0x0001,     # Adapter type = eBus
        0x0023: 0x0500,     # OT error value present
    }
    assert gw.get_ot_error() is None  # Not an OpenTherm adapter

    # Test Navien adapter (0x02) - should return None
    gw.cache = {
        0x0010: 0x0002,     # Adapter type = Navien
        0x0023: 0x0500,     # OT error value present
    }
    assert gw.get_ot_error() is None  # Not an OpenTherm adapter

    # Test missing register
    gw.cache = {
        0x0010: 0x0000,     # Adapter type = OpenTherm
    }
    assert gw.get_ot_error() is None  # Register not available


def test_register_health_monitoring():
    """Test register status/health monitoring (0x0040-0x006F)."""
    class DummyProtocol:
        pass

    gw = BoilerGateway(DummyProtocol(), slave_id=1)

    # Test valid data (status = 0)
    gw.cache = {
        0x0018: 291,        # CH temp = 29.1°C
        0x0048: 0x0000,     # Status = valid (0)
    }
    assert gw.get_register_status(0x0018) == 0
    assert gw.is_register_valid(0x0018) is True
    assert gw.get_ch_temperature() == 29.1

    # Test not supported (status = -1)
    gw.cache = {
        0x0018: 0x0000,
        0x0048: 0xFFFF,     # Status = -1 (not supported)
    }
    assert gw.get_register_status(0x0018) == -1
    assert gw.is_register_valid(0x0018) is False
    assert gw.get_ch_temperature() is None  # Should return None due to status check

    # Test read/write error (status = -2)
    gw.cache = {
        0x0018: 0x0000,
        0x0048: 0xFFFE,     # Status = -2 (read/write error)
    }
    assert gw.get_register_status(0x0018) == -2
    assert gw.is_register_valid(0x0018) is False
    assert gw.get_ch_temperature() is None  # Should return None due to status check

    # Test not initialized (status = 1)
    gw.cache = {
        0x0018: 0x0000,
        0x0048: 0x0001,     # Status = 1 (not initialized)
    }
    assert gw.get_register_status(0x0018) == 1
    assert gw.is_register_valid(0x0018) is False
    assert gw.get_ch_temperature() is None  # Should return None due to status check

    # Test status register not available (fallback to assume valid)
    gw.cache = {
        0x0018: 291,        # CH temp = 29.1°C
        # 0x0048 not in cache
    }
    assert gw.get_register_status(0x0018) is None
    assert gw.is_register_valid(0x0018) is True  # Fallback: assume valid
    assert gw.get_ch_temperature() == 29.1  # Should return value

    # Test outside valid range (below 0x0010)
    assert gw.get_register_status(0x000F) is None

    # Test outside valid range (above 0x003F)
    assert gw.get_register_status(0x0040) is None

    # Test status description
    assert gw._get_register_status_description(0) == "Data valid"
    assert gw._get_register_status_description(1) == "Not initialized"
    assert gw._get_register_status_description(-1) == "Not supported by boiler"
    assert gw._get_register_status_description(-2) == "Read/write error"
    assert gw._get_register_status_description(99) == "Unknown status: 99"
