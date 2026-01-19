"""Tests for Contact Sensor Gateway."""
import pytest
from custom_components.ectocontrol_modbus_controller.contact_gateway import ContactSensorGateway


class FakeProtocol:
    """Fake ModbusProtocol for testing."""

    def __init__(self):
        self.read_calls = []
        self.read_values = {}

    async def read_registers(self, slave_id, start_addr, count):
        """Simulate reading registers."""
        self.read_calls.append((slave_id, start_addr, count))
        key = (slave_id, start_addr, count)
        return self.read_values.get(key)


class FakeCoordinator:
    """Fake coordinator for testing."""

    def __init__(self, gateway):
        self.gateway = gateway
        self.refreshed = False

    async def async_request_refresh(self):
        self.refreshed = True


@pytest.fixture
def fake_protocol():
    """Create a fake protocol instance."""
    return FakeProtocol()


@pytest.fixture
def fake_gateway(fake_protocol):
    """Create a fake gateway instance."""
    gateway = ContactSensorGateway(fake_protocol, slave_id=1)
    return gateway


class TestContactSensorGatewayDeviceInfo:
    """Tests for device info reading."""

    @pytest.mark.asyncio
    async def test_read_device_info_success_10ch(self, fake_protocol, fake_gateway):
        """Test successful device info read for 10-channel device."""
        # Simulate device info response
        # Per Russian documentation: UID is in bytes 1-3 (LSB to MSB order)
        # UID byte 1 (LSB) = register 0x0000 LSB
        # UID byte 2 (middle) = register 0x0001 MSB
        # UID byte 3 (MSB) = register 0x0001 LSB
        # Example: UID = 0x8ABCDE → reg[0x0000]=0x00DE, reg[0x0001]=0xABCD
        fake_protocol.read_values[(1, 0x0000, 4)] = [
            0x00DE,  # RSVD (0x00) + UID byte 1 LSB (0xDE)
            0xABCD,  # UID byte 3 MSB (0xAB) + UID byte 2 (0xCD)
            0x0000,  # Not used for UID
            0x590A,  # Device type 0x59, channel count 0x0A (10)
        ]

        result = await fake_gateway.read_device_info()

        assert result is True
        assert fake_gateway.device_uid == 0x8ABCDE  # Correct UID parsing
        assert fake_gateway.device_type == 0x59
        assert fake_gateway.channel_count == 10

    @pytest.mark.asyncio
    async def test_read_device_info_success_4ch(self, fake_protocol, fake_gateway):
        """Test successful device info read for 4-channel device."""
        # UID = 0x812345 → reg[0x0000]=0x0045, reg[0x0001]=0x8123
        fake_protocol.read_values[(1, 0x0000, 4)] = [
            0x0045,  # RSVD (0x00) + UID byte 1 LSB (0x45)
            0x8123,  # UID byte 3 MSB (0x81) + UID byte 2 (0x23)
            0x0000,  # Not used for UID
            0x5904,  # Device type 0x59, channel count 0x04
        ]

        result = await fake_gateway.read_device_info()

        assert result is True
        assert fake_gateway.device_uid == 0x812345  # Correct UID parsing
        assert fake_gateway.device_type == 0x59
        assert fake_gateway.channel_count == 4

    @pytest.mark.asyncio
    async def test_read_device_info_invalid_uid(self, fake_protocol, fake_gateway):
        """Test device info read with invalid UID."""
        # UID = 0x007FFF → below 0x800000 (invalid)
        fake_protocol.read_values[(1, 0x0000, 4)] = [
            0x00FF,  # RSVD (0x00) + UID byte 1 LSB (0xFF)
            0x007F,  # UID byte 3 MSB (0x00) + UID byte 2 (0x7F)
            0x0000,  # Not used for UID
            0x5904,  # Device type 0x59, channel count 4
        ]

        result = await fake_gateway.read_device_info()

        assert result is False
        # UID will still be stored but validation fails
        assert fake_gateway.device_uid == 0x7FFF00  # (0x7FFF << 8) | 0x00

    @pytest.mark.asyncio
    async def test_read_device_info_no_response(self, fake_protocol, fake_gateway):
        """Test device info read when device doesn't respond."""
        fake_protocol.read_values[(1, 0x0000, 4)] = None

        result = await fake_gateway.read_device_info()

        assert result is False
        assert fake_gateway.device_uid is None
        assert fake_gateway.device_type is None
        assert fake_gateway.channel_count is None


class TestContactSensorGatewayBitfieldExtraction:
    """Tests for bitfield extraction from registers 0x0010-0x0011."""

    def test_get_channel_state_channel_1_closed(self, fake_gateway):
        """Test reading channel 1 state (closed)."""
        fake_gateway.cache[0x0010] = 0x0001  # Bit 0 set
        fake_gateway.channel_count = 4

        state = fake_gateway.get_channel_state(1)

        assert state is True  # Closed

    def test_get_channel_state_channel_1_open(self, fake_gateway):
        """Test reading channel 1 state (open)."""
        fake_gateway.cache[0x0010] = 0x0000  # Bit 0 clear
        fake_gateway.channel_count = 4

        state = fake_gateway.get_channel_state(1)

        assert state is False  # Open

    def test_get_channel_state_multiple_channels(self, fake_gateway):
        """Test reading multiple channels from bitfield."""
        # Channels 1, 3, 5 closed; 2, 4, 6, 7, 8 open
        fake_gateway.cache[0x0010] = 0x0015  # Binary: 0000000000010101
        fake_gateway.channel_count = 8

        assert fake_gateway.get_channel_state(1) is True   # Bit 0
        assert fake_gateway.get_channel_state(2) is False  # Bit 1
        assert fake_gateway.get_channel_state(3) is True   # Bit 2
        assert fake_gateway.get_channel_state(4) is False  # Bit 3
        assert fake_gateway.get_channel_state(5) is True   # Bit 4
        assert fake_gateway.get_channel_state(6) is False  # Bit 5
        assert fake_gateway.get_channel_state(7) is False  # Bit 6
        assert fake_gateway.get_channel_state(8) is False  # Bit 7

    def test_get_channel_state_channel_9_closed(self, fake_gateway):
        """Test reading channel 9 state (closed, from register 0x0011)."""
        fake_gateway.cache[0x0010] = 0x00FF  # All channels 1-8 closed
        fake_gateway.cache[0x0011] = 0x0001  # Channel 9 closed (bit 0)
        fake_gateway.channel_count = 10

        state = fake_gateway.get_channel_state(9)

        assert state is True  # Closed

    def test_get_channel_state_channel_10_closed(self, fake_gateway):
        """Test reading channel 10 state (closed, from register 0x0011)."""
        fake_gateway.cache[0x0010] = 0x00FF  # All channels 1-8 closed
        fake_gateway.cache[0x0011] = 0x0002  # Channel 10 closed (bit 1)
        fake_gateway.channel_count = 10

        state = fake_gateway.get_channel_state(10)

        assert state is True  # Closed

    def test_get_channel_state_all_10_channels_closed(self, fake_gateway):
        """Test all 10 channels closed."""
        fake_gateway.cache[0x0010] = 0x00FF  # Channels 1-8 closed
        fake_gateway.cache[0x0011] = 0x0007  # Channels 9-10 closed (bits 0-1 set)
        fake_gateway.channel_count = 10

        # All channels should be closed
        for channel in range(1, 11):
            assert fake_gateway.get_channel_state(channel) is True

    def test_get_channel_state_all_10_channels_open(self, fake_gateway):
        """Test all 10 channels open."""
        fake_gateway.cache[0x0010] = 0x0000  # Channels 1-8 open
        fake_gateway.cache[0x0011] = 0x0000  # Channels 9-10 open
        fake_gateway.channel_count = 10

        # All channels should be open
        for channel in range(1, 11):
            assert fake_gateway.get_channel_state(channel) is False

    def test_get_channel_state_invalid_channel_too_low(self, fake_gateway):
        """Test channel number too low."""
        fake_gateway.channel_count = 4

        with pytest.raises(ValueError, match="Channel must be 1-10"):
            fake_gateway.get_channel_state(0)

    def test_get_channel_state_invalid_channel_too_high(self, fake_gateway):
        """Test channel number too high."""
        fake_gateway.channel_count = 4

        with pytest.raises(ValueError, match="Channel must be 1-10"):
            fake_gateway.get_channel_state(11)

    def test_get_channel_state_beyond_device_channel_count(self, fake_gateway):
        """Test channel beyond device's actual channel count."""
        fake_gateway.cache[0x0010] = 0xFFFF
        fake_gateway.channel_count = 4

        # Channel 5 doesn't exist on this 4-channel device
        assert fake_gateway.get_channel_state(5) is None

    def test_get_channel_state_register_not_available(self, fake_gateway):
        """Test when bitfield register not in cache."""
        fake_gateway.cache = {}  # Empty cache
        fake_gateway.channel_count = 4

        # Register 0x0010 not in cache
        assert fake_gateway.get_channel_state(1) is None


class TestContactSensorGatewayHelpers:
    """Tests for helper methods."""

    def test_get_channel_count(self, fake_gateway):
        """Test getting channel count."""
        fake_gateway.channel_count = 4
        assert fake_gateway.get_channel_count() == 4

        fake_gateway.channel_count = None
        assert fake_gateway.get_channel_count() == 0

    def test_get_device_uid_hex(self, fake_gateway):
        """Test getting UID as hex string."""
        fake_gateway.device_uid = 0x8ABCDEF

        assert fake_gateway.get_device_uid_hex() == "8abcdef"

        fake_gateway.device_uid = None
        assert fake_gateway.get_device_uid_hex() is None

    def test_get_device_type_name(self, fake_gateway):
        """Test getting device type name."""
        fake_gateway.device_type = 0x59

        # Will return from DEVICE_TYPE_NAMES or fallback
        name = fake_gateway.get_device_type_name()
        assert "Contact" in name or "Splitter" in name

    def test_get_device_info(self, fake_gateway):
        """Test getting device info structure."""
        fake_gateway.device_uid = 0x8ABCDEF
        fake_gateway.device_type = 0x59
        fake_gateway.channel_count = 4

        device_info = fake_gateway.get_device_info()

        # The method returns a DeviceInfo object (dict-like)
        # Check it has the correct structure
        assert "identifiers" in device_info or hasattr(device_info, "identifiers")
        assert "name" in device_info or hasattr(device_info, "name")
        assert "manufacturer" in device_info or hasattr(device_info, "manufacturer")
        assert "serial_number" in device_info or hasattr(device_info, "serial_number")
        
        # Check that the device name includes channel count
        if "name" in device_info:
            assert "4ch" in device_info["name"]
        elif hasattr(device_info, "name"):
            assert "4ch" in device_info.name
        
        # Check manufacturer
        if "manufacturer" in device_info:
            assert device_info["manufacturer"] == "Ectocontrol"
        elif hasattr(device_info, "manufacturer"):
            assert device_info.manufacturer == "Ectocontrol"
        
        # Check serial number
        if "serial_number" in device_info:
            assert device_info["serial_number"] == "8abcdef"
        elif hasattr(device_info, "serial_number"):
            assert device_info.serial_number == "8abcdef"
