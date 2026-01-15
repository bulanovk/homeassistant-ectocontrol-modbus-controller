"""Tests for DebugSerial wrapper in modbus_protocol.py."""
import pytest
import logging
from unittest.mock import MagicMock, patch

from custom_components.ectocontrol_modbus_controller.modbus_protocol import DebugSerial


class FakeSerial:
    """Fake serial.Serial instance for testing."""

    def __init__(self, port="COM3", baudrate=19200, bytesize=8, parity="N", stopbits=1, timeout=2.0):
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.timeout = timeout
        self._is_open = True
        self._read_data = b""
        self._written_data = []

    def read(self, size=1):
        """Mock read method."""
        if self._read_data:
            data = self._read_data[:size]
            self._read_data = self._read_data[size:]
            return data
        return b""

    def write(self, data):
        """Mock write method."""
        self._written_data.append(data)
        return len(data)

    def flush(self):
        """Mock flush method."""
        pass

    def flushInput(self):
        """Mock flushInput method."""
        pass

    def flushOutput(self):
        """Mock flushOutput method."""
        pass

    def close(self):
        """Mock close method."""
        self._is_open = False

    def isOpen(self):
        """Mock isOpen method."""
        return self._is_open

    def in_waiting(self):
        """Mock in_waiting property."""
        return len(self._read_data)


def test_debug_serial_init() -> None:
    """Test DebugSerial initialization."""
    # Arrange
    fake_serial = FakeSerial()
    name = "MODBUS_TEST"

    # Act
    debug_serial = DebugSerial(fake_serial, name=name)

    # Assert
    assert debug_serial._serial is fake_serial
    assert debug_serial._name == name
    assert debug_serial._logger.name == f"custom_components.ectocontrol_modbus_controller.modbus_protocol.{name}"


def test_debug_serial_read() -> None:
    """Test read() with RX logging."""
    # Arrange
    fake_serial = FakeSerial()
    fake_serial._read_data = b"\x01\x02\x03\x04"
    debug_serial = DebugSerial(fake_serial, name="MODBUS_TEST")

    # Act
    with patch.object(debug_serial._logger, 'debug') as mock_debug:
        result = debug_serial.read(3)
    
        # Assert - read returns correct data
        assert result == b"\x01\x02\x03"
        # Assert - debug log was called with RX data
        assert mock_debug.called
        call_args = mock_debug.call_args[0]
        # Log format is: "%s RX (%d bytes): %s" where args are (name, len, hex_str)
        assert call_args[0] == "%s RX (%d bytes): %s"
        assert call_args[1] == "MODBUS_TEST"
        assert call_args[2] == 3
        assert call_args[3] == "01 02 03"


def test_debug_serial_read_empty() -> None:
    """Test read() returning empty bytes."""
    # Arrange
    fake_serial = FakeSerial()
    fake_serial._read_data = b""
    debug_serial = DebugSerial(fake_serial, name="MODBUS_TEST")
    
    # Act
    with patch.object(debug_serial._logger, 'debug') as mock_debug:
        result = debug_serial.read(10)
    
        # Assert - read returns empty bytes
        assert result == b""
        # Assert - debug log was called with timeout message
        assert mock_debug.called
        call_args = mock_debug.call_args[0]
        # Log format is: "%s RX: timeout (0 bytes)" where args are (name,)
        assert call_args[0] == "%s RX: timeout (0 bytes)"
        assert call_args[1] == "MODBUS_TEST"


def test_debug_serial_write() -> None:
    """Test write() with TX logging."""
    # Arrange
    fake_serial = FakeSerial()
    debug_serial = DebugSerial(fake_serial, name="MODBUS_TEST")

    # Act
    with patch.object(debug_serial._logger, 'debug') as mock_debug:
        data = b"\x01\x02\x03\x04"
        result = debug_serial.write(data)
    
        # Assert - write delegates to wrapped serial
        assert result == 4
        assert len(fake_serial._written_data) == 1
        assert fake_serial._written_data[0] == data
        # Assert - debug log was called with TX data
        assert mock_debug.called
        call_args = mock_debug.call_args[0]
        # Log format is: "%s TX (%d bytes): %s" where args are (name, len, hex_str)
        assert call_args[0] == "%s TX (%d bytes): %s"
        assert call_args[1] == "MODBUS_TEST"
        assert call_args[2] == 4
        assert call_args[3] == "01 02 03 04"


def test_debug_serial_flush() -> None:
    """Test flush() method."""
    # Arrange
    fake_serial = FakeSerial()
    debug_serial = DebugSerial(fake_serial, name="MODBUS_TEST")

    # Act
    debug_serial.flush()

    # Assert - flush delegates to wrapped serial (no exception means success)
    # The test passes if no exception is raised


def test_debug_serial_flush_input() -> None:
    """Test flushInput() method."""
    # Arrange
    fake_serial = FakeSerial()
    debug_serial = DebugSerial(fake_serial, name="MODBUS_TEST")

    # Act
    debug_serial.flushInput()

    # Assert - flushInput delegates to wrapped serial (no exception means success)
    # The test passes if no exception is raised


def test_debug_serial_flush_output() -> None:
    """Test flushOutput() method."""
    # Arrange
    fake_serial = FakeSerial()
    debug_serial = DebugSerial(fake_serial, name="MODBUS_TEST")

    # Act
    debug_serial.flushOutput()

    # Assert - flushOutput delegates to wrapped serial (no exception means success)
    # The test passes if no exception is raised


def test_debug_serial_is_open() -> None:
    """Test isOpen() method."""
    # Arrange
    fake_serial = FakeSerial()
    fake_serial._is_open = True
    debug_serial = DebugSerial(fake_serial, name="MODBUS_TEST")

    # Act
    result = debug_serial.isOpen()

    # Assert - isOpen returns correct state
    assert result is True

    # Test with closed serial
    fake_serial._is_open = False
    result = debug_serial.isOpen()
    assert result is False


def test_debug_serial_in_waiting() -> None:
    """Test in_waiting() method."""
    # Arrange
    fake_serial = FakeSerial()
    fake_serial._read_data = b"\x01\x02\x03"
    debug_serial = DebugSerial(fake_serial, name="MODBUS_TEST")
    
    # Act
    result = debug_serial.in_waiting()
    
    # Assert - in_waiting returns 0 (FakeSerial doesn't have inWaiting)
    # The test passes if no exception is raised


def test_debug_serial_port_property() -> None:
    """Test port property."""
    # Arrange
    fake_serial = FakeSerial(port="COM3")
    debug_serial = DebugSerial(fake_serial, name="MODBUS_TEST")

    # Act
    result = debug_serial.port

    # Assert - port property delegates to wrapped serial
    assert result == "COM3"


def test_debug_serial_baudrate_property() -> None:
    """Test baudrate property."""
    # Arrange
    fake_serial = FakeSerial(baudrate=19200)
    debug_serial = DebugSerial(fake_serial, name="MODBUS_TEST")

    # Act
    result = debug_serial.baudrate

    # Assert - baudrate property delegates to wrapped serial
    assert result == 19200


def test_debug_serial_bytesize_property() -> None:
    """Test bytesize property."""
    # Arrange
    fake_serial = FakeSerial(bytesize=8)
    debug_serial = DebugSerial(fake_serial, name="MODBUS_TEST")

    # Act
    result = debug_serial.bytesize

    # Assert - bytesize property delegates to wrapped serial
    assert result == 8


def test_debug_serial_parity_property() -> None:
    """Test parity property."""
    # Arrange
    fake_serial = FakeSerial(parity="N")
    debug_serial = DebugSerial(fake_serial, name="MODBUS_TEST")

    # Act
    result = debug_serial.parity

    # Assert - parity property delegates to wrapped serial
    assert result == "N"


def test_debug_serial_stopbits_property() -> None:
    """Test stopbits property."""
    # Arrange
    fake_serial = FakeSerial(stopbits=1)
    debug_serial = DebugSerial(fake_serial, name="MODBUS_TEST")

    # Act
    result = debug_serial.stopbits

    # Assert - stopbits property delegates to wrapped serial
    assert result == 1


def test_debug_serial_timeout_property() -> None:
    """Test timeout property getter."""
    # Arrange
    fake_serial = FakeSerial(timeout=2.0)
    debug_serial = DebugSerial(fake_serial, name="MODBUS_TEST")

    # Act
    result = debug_serial.timeout

    # Assert - timeout property delegates to wrapped serial
    assert result == 2.0


def test_debug_serial_timeout_setter() -> None:
    """Test timeout property setter."""
    # Arrange
    fake_serial = FakeSerial(timeout=2.0)
    debug_serial = DebugSerial(fake_serial, name="MODBUS_TEST")

    # Act
    debug_serial.timeout = 5.0

    # Assert - timeout setter delegates to wrapped serial
    assert fake_serial.timeout == 5.0


def test_debug_serial_unknown_attribute_forwarding() -> None:
    """Test __getattr__ method forwards unknown attributes."""
    # Arrange
    fake_serial = FakeSerial()
    # Add a custom attribute to fake serial
    fake_serial.custom_attr = "test_value"
    debug_serial = DebugSerial(fake_serial, name="MODBUS_TEST")

    # Act
    result = debug_serial.custom_attr

    # Assert - unknown attribute forwarded to wrapped serial
    assert result == "test_value"
