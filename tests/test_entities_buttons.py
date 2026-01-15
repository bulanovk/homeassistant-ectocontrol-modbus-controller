"""Tests for button entities."""
import pytest

from custom_components.ectocontrol_modbus_controller.button import RebootAdapterButton, ResetErrorsButton


class FakeGateway:
    """Fake gateway for testing."""

    def __init__(self):
        self.slave_id = 2
        self.reboot_called = False
        self.reset_called = False
        self.device_uid = 0x8ABCDEF  # Test UID (24-bit value in range 0x800000-0xFFFFFF)
        # Add protocol mock for device_info tests
        self.protocol = type('obj', (object,), {'port': 'mock_port'})

    def get_device_uid_hex(self):
        """Return UID as hex string."""
        if self.device_uid is None:
            return None
        return f"{self.device_uid:06x}"

    async def reboot_adapter(self):
        self.reboot_called = True
        return True

    async def reset_boiler_errors(self):
        self.reset_called = True
        return True


class DummyCoordinator:
    """Dummy coordinator for testing."""

    def __init__(self, gateway):
        self.gateway = gateway
        self.last_update_success = True  # Add for availability tests
        self.refreshed = False

    async def async_request_refresh(self):
        self.refreshed = True


@pytest.mark.asyncio
async def test_buttons_press_triggers_commands_and_refresh() -> None:
    """Test button press triggers commands and coordinator refresh."""
    gw = FakeGateway()
    coord = DummyCoordinator(gw)

    reboot_btn = RebootAdapterButton(coord)
    reset_btn = ResetErrorsButton(coord)

    await reboot_btn.async_press()
    assert gw.reboot_called is True

    await reset_btn.async_press()
    assert gw.reset_called is True


@pytest.mark.asyncio
async def test_reboot_button_async_press() -> None:
    """Test RebootButton.async_press() method."""
    # Arrange
    gw = FakeGateway()
    coord = DummyCoordinator(gw)
    reboot_btn = RebootAdapterButton(coord)

    # Act
    await reboot_btn.async_press()

    # Assert - gateway reboot_adapter() was called
    assert gw.reboot_called is True
    # Assert - coordinator async_request_refresh() was called
    assert coord.refreshed is True


@pytest.mark.asyncio
async def test_reset_errors_button_async_press() -> None:
    """Test ResetButton.async_press() method."""
    # Arrange
    gw = FakeGateway()
    coord = DummyCoordinator(gw)
    reset_btn = ResetErrorsButton(coord)

    # Act
    await reset_btn.async_press()

    # Assert - gateway reset_boiler_errors() was called
    assert gw.reset_called is True
    # Assert - coordinator async_request_refresh() was called
    assert coord.refreshed is True
