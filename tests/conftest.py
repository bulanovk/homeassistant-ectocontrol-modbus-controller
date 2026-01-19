"""Pytest configuration and shared fixtures for Ectocontrol integration tests."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import pytest

# Import test utilities
from tests.modbus_slave_simulator import ModbusSlaveSimulator
from tests.pty_manager import PTYManager, check_socat_available

# Configure logging for tests
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

_LOGGER = logging.getLogger(__name__)


# ============================================================================
# socat availability check
# ============================================================================

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "pty: marks tests as requiring socat PTY support (deselect with '-m \"not pty\"')"
    )


def pytest_collection_modifyitems(config, items):
    """Automatically skip PTY tests if socat is not available."""
    # Check if socat is available (sync check)
    try:
        loop = asyncio.get_event_loop()
        socat_available = loop.run_until_complete(check_socat_available())
    except Exception:
        socat_available = False

    if not socat_available:
        skip_marker = pytest.mark.skip(
            reason="socat is not installed. Install with: sudo apt-get install socat"
        )
        for item in items:
            if "pty" in item.keywords:
                item.add_marker(skip_marker)


# ============================================================================
# Shared fixtures
# ============================================================================

@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def pty_pair():
    """Create a socat PTY pair for testing.

    This fixture creates a virtual serial port pair using socat.
    The master PTY is typically used by the integration (ModbusProtocol),
    and the slave PTY is used by the simulator.

    Yields:
        (master_port, slave_port) tuple of PTY device paths
        Example: ("/dev/pts/0", "/dev/pts/1")

    Cleanup:
        Automatically closes the PTY pair after the test
    """
    manager = PTYManager()

    try:
        master, slave = await manager.create_pair()
        _LOGGER.debug("Created PTY pair: master=%s, slave=%s", master, slave)

        yield master, slave

    finally:
        await manager.close()
        _LOGGER.debug("Closed PTY pair")


@pytest.fixture
async def pty_pair_debug():
    """Create a socat PTY pair with debug output enabled.

    Same as pty_pair, but enables socat debug logging for troubleshooting.

    Yields:
        (master_port, slave_port) tuple
    """
    manager = PTYManager()

    try:
        master, slave = await manager.create_pair(debug=True)
        _LOGGER.debug("Created debug PTY pair: master=%s, slave=%s", master, slave)

        yield master, slave

    finally:
        await manager.close()
        _LOGGER.debug("Closed PTY pair")


@pytest.fixture
def modbus_slave(pty_pair):
    """Create a Modbus slave simulator on a PTY.

    This fixture creates a Modbus RTU slave simulator that listens
    on the slave PTY. The simulator implements the Ectocontrol
    register map for testing.

    Uses threading to run the simulator in the background, avoiding
    pytest-asyncio event loop issues.

    Args:
        pty_pair: PTY pair fixture (automatically injected)

    Yields:
        ModbusSlaveSimulator instance

    Example:
        >>> async def test_read(modbus_slave):
        ...     # Write to simulator registers
        ...     modbus_slave.set_register(0x0018, 0x00A6)
        ...     # Read from simulator
        ...     value = modbus_slave.get_register(0x0018)
        ...     assert value == 0x00A6

    Cleanup:
        Automatically stops the simulator after the test
    """
    import threading
    import time

    master, slave = pty_pair

    # Create slave simulator with default settings
    simulator = ModbusSlaveSimulator(port=slave, slave_id=1, device_type=0x14)

    # Run simulator in a thread to avoid pytest-asyncio issues
    stop_event = threading.Event()
    simulator_thread = None

    def run_simulator():
        """Run simulator in thread with event loop."""
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(simulator.start())
        finally:
            loop.close()

    simulator_thread = threading.Thread(target=run_simulator, daemon=True)
    simulator_thread.start()

    # Give simulator time to start and initialize serial port
    # Serial port opening can take time
    time.sleep(1.0)

    yield simulator

    # Cleanup
    simulator.stop()
    stop_event.set()
    if simulator_thread and simulator_thread.is_alive():
        simulator_thread.join(timeout=2.0)
        _LOGGER.debug("Modbus slave simulator stopped")


@pytest.fixture
def default_registers():
    """Provide default register values for testing.

    Returns a dictionary of register addresses to values that
    represent a typical OpenTherm Adapter v2 with a boiler.

    Returns:
        dict[int, int]: Register map

    Example:
        >>> def test_registers(default_registers):
        ...     assert default_registers[0x0010] == 0x0009
    """
    return {
        # Device info
        0x0000: 0x0000,  # Reserved
        0x0001: 0x8ABC,  # UID high
        0x0002: 0xDE00,  # UID low
        0x0003: 0x1404,  # Device type 0x14, channels 4

        # Status
        0x0010: 0x0009,  # OpenTherm, boiler connected
        0x0011: 0x012C,  # HW=1, SW=44
        0x0012: 0x0000,  # Uptime high
        0x0013: 0x001E,  # Uptime low (30s)

        # Sensors
        0x0018: 0x00A6,  # CH temp 16.6°C
        0x0019: 0x0158,  # DHW temp 34.8°C
        0x001A: 0x1200,  # Pressure 1.8 bar
        0x001B: 0x0E00,  # Flow 1.4 L/min
        0x001C: 0x4600,  # Modulation 70%
        0x001D: 0x0007,  # States: burner, heating, DHW on
        0x001E: 0x0000,  # Main error: none
        0x001F: 0x0000,  # Add error: none
        0x0020: 0x000A,  # Outdoor temp 10°C

        # Setpoints & limits
        0x0026: 0x0C80,  # CH setpoint active 50.0°C
        0x0031: 0x0C80,  # CH setpoint 50.0°C
        0x0033: 0x2300,  # CH min 35°C
        0x0034: 0x5A00,  # CH max 90°C
        0x0035: 0x2800,  # DHW min 40°C
        0x0036: 0x4600,  # DHW max 70°C
        0x0037: 0x3C00,  # DHW setpoint 60°C
        0x0038: 0x6400,  # Max modulation 100%
        0x0039: 0x0003,  # Heating + DHW enabled

        # Register status (all valid)
        **{addr + 0x30: 0x0000 for addr in range(0x0010, 0x0040)},
    }


@pytest.fixture
def fake_hass():
    """Create a fake Home Assistant instance for testing.

    Returns a minimal HA-like object with the required attributes
    for integration testing.

    Returns:
        FakeHass instance with data, services, config, and bus attributes
    """
    from unittest.mock import MagicMock
    from custom_components.ectocontrol_modbus_controller.const import DOMAIN

    class FakeHass:
        """Minimal Home Assistant mock for testing."""

        def __init__(self):
            self.data = {DOMAIN: {}}
            self.services = MagicMock()
            self.config = MagicMock()
            self.config.config_dir = "/tmp/config"
            self.config_entries = MagicMock()
            self.loop = asyncio.get_event_loop()
            self.loop_thread_id = None
            self.bus = MagicMock()
            self.bus.async_listen_once = MagicMock()

        async def async_add_executor_job(self, func, *args):
            """Add a job to the executor."""
            return await asyncio.get_event_loop().run_in_executor(None, func, *args)

    return FakeHass()


@pytest.fixture
def fake_config_entry():
    """Create a fake config entry for testing.

    Returns a config entry object with typical Ectocontrol settings.

    Returns:
        FakeConfigEntry instance
    """
    from custom_components.ectocontrol_modbus_controller.const import (
        CONF_PORT, CONF_SLAVE_ID, CONF_NAME, CONF_POLLING_INTERVAL,
        CONF_RETRY_COUNT, CONF_DEBUG_MODBUS
    )

    class FakeConfigEntry:
        """Minimal config entry mock for testing."""

        def __init__(self, entry_id="test_entry_id", port="/dev/ttyUSB0", slave_id=1):
            self.entry_id = entry_id
            self.data = {
                CONF_PORT: port,
                CONF_SLAVE_ID: slave_id,
                CONF_NAME: "Test Boiler",
                CONF_POLLING_INTERVAL: 15,
                CONF_RETRY_COUNT: 3,
                CONF_DEBUG_MODBUS: False,
            }
            self.options = {}
            self._unload_callbacks = []

        async def async_on_unload(self, callback):
            """Register an unload callback."""
            self._unload_callbacks.append(callback)

    return FakeConfigEntry()


@pytest.fixture
def fake_device_registry():
    """Create a fake device registry for testing.

    Returns a minimal device registry mock.

    Returns:
        FakeDeviceRegistry instance
    """
    class FakeDeviceEntry:
        def __init__(self, device_id="test_device_id"):
            self.id = device_id

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

    return FakeDeviceRegistry()
