"""Integration tests for error handling with virtual serial ports.

These tests verify that the integration handles various error conditions
correctly when using real Modbus communication via PTY.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from custom_components.ectocontrol_modbus_controller import async_setup_entry
from custom_components.ectocontrol_modbus_controller.const import (
    DOMAIN, CONF_PORT, CONF_SLAVE_ID
)


@pytest.mark.asyncio
@pytest.mark.pty
async def test_gateway_handles_invalid_markers(modbus_slave, pty_pair, fake_hass, fake_config_entry, fake_device_registry) -> None:
    """Test that gateway returns None for invalid value markers."""
    master, slave = pty_pair

    fake_config_entry.data[CONF_PORT] = master
    fake_config_entry.data[CONF_SLAVE_ID] = 1

    # Set invalid markers in simulator
    modbus_slave.set_register(0x0018, 0x7FFF)  # Invalid marker for CH temp
    modbus_slave.set_register(0x001A, 0xFFFF)  # Invalid marker for pressure

    # Initialize protocol manager
    from custom_components.ectocontrol_modbus_controller.modbus_protocol_manager import ModbusProtocolManager
    fake_hass.data[DOMAIN]["protocol_manager"] = ModbusProtocolManager()

    with patch("custom_components.ectocontrol_modbus_controller.dr.async_get", return_value=fake_device_registry):
        result = await async_setup_entry(fake_hass, fake_config_entry)
        assert result is True

        # Get gateway
        inst = fake_hass.data[DOMAIN][fake_config_entry.entry_id]
        gateway = inst["gateway"]

        # Trigger coordinator update
        coordinator = inst["coordinator"]
        await coordinator._async_update_data()

        # Gateway should return None for invalid values
        ch_temp = gateway.get_ch_temperature()
        assert ch_temp is None

        pressure = gateway.get_pressure()
        assert pressure is None


@pytest.mark.asyncio
@pytest.mark.pty
async def test_gateway_handles_missing_registers(modbus_slave, pty_pair, fake_hass, fake_config_entry, fake_device_registry) -> None:
    """Test that gateway handles missing registers gracefully."""
    master, slave = pty_pair

    fake_config_entry.data[CONF_PORT] = master
    fake_config_entry.data[CONF_SLAVE_ID] = 1

    # Initialize protocol manager
    from custom_components.ectocontrol_modbus_controller.modbus_protocol_manager import ModbusProtocolManager
    fake_hass.data[DOMAIN]["protocol_manager"] = ModbusProtocolManager()

    with patch("custom_components.ectocontrol_modbus_controller.dr.async_get", return_value=fake_device_registry):
        result = await async_setup_entry(fake_hass, fake_config_entry)
        assert result is True

        # Get gateway with empty cache
        inst = fake_hass.data[DOMAIN][fake_config_entry.entry_id]
        gateway = inst["gateway"]
        gateway.cache = {}  # Empty cache

        # Getters should return None when registers not in cache
        ch_temp = gateway.get_ch_temperature()
        assert ch_temp is None

        pressure = gateway.get_pressure()
        assert pressure is None


@pytest.mark.asyncio
@pytest.mark.pty
async def test_coordinator_handles_poll_failure(modbus_slave, pty_pair, fake_hass, fake_config_entry, fake_device_registry) -> None:
    """Test coordinator behavior when polling fails."""
    master, slave = pty_pair

    fake_config_entry.data[CONF_PORT] = master
    fake_config_entry.data[CONF_SLAVE_ID] = 1

    # Initialize protocol manager
    from custom_components.ectocontrol_modbus_controller.modbus_protocol_manager import ModbusProtocolManager
    fake_hass.data[DOMAIN]["protocol_manager"] = ModbusProtocolManager()

    with patch("custom_components.ectocontrol_modbus_controller.dr.async_get", return_value=fake_device_registry):
        result = await async_setup_entry(fake_hass, fake_config_entry)
        assert result is True

        # Get coordinator
        inst = fake_hass.data[DOMAIN][fake_config_entry.entry_id]
        coordinator = inst["coordinator"]

        # First poll should succeed
        data = await coordinator._async_update_data()
        assert data is not None
        assert coordinator.last_update_success is True

        # Inject timeout
        modbus_slave.inject_error("timeout")

        # Next poll should fail with UpdateFailed exception
        from homeassistant.helpers.update_coordinator import UpdateFailed
        try:
            data = await coordinator._async_update_data()
            assert False, "Expected UpdateFailed exception"
        except UpdateFailed:
            pass  # Expected

        # Clear error
        modbus_slave.clear_errors()

        # Next poll should succeed
        data = await coordinator._async_update_data()
        assert data is not None
        assert coordinator.last_update_success is True
