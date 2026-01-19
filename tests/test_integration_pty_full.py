"""Full integration tests with real Modbus communication via PTY.

These tests exercise the complete integration stack from ModbusProtocol
through BoilerGateway to entities, using virtual serial ports.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from custom_components.ectocontrol_modbus_controller import async_setup_entry
from custom_components.ectocontrol_modbus_controller.const import (
    DOMAIN, CONF_PORT, CONF_SLAVE_ID
)
from custom_components.ectocontrol_modbus_controller.boiler_gateway import BoilerGateway
from custom_components.ectocontrol_modbus_controller.coordinator import BoilerDataUpdateCoordinator


@pytest.mark.asyncio
@pytest.mark.pty
async def test_full_setup_with_virtual_port(modbus_slave, pty_pair, fake_hass, fake_config_entry, fake_device_registry) -> None:
    """Test complete integration setup with virtual serial port."""
    master, slave = pty_pair

    # Update config entry to use virtual port
    fake_config_entry.data[CONF_PORT] = master
    fake_config_entry.data[CONF_SLAVE_ID] = 1

    # Initialize protocol manager
    from custom_components.ectocontrol_modbus_controller.modbus_protocol_manager import ModbusProtocolManager
    fake_hass.data[DOMAIN]["protocol_manager"] = ModbusProtocolManager()

    # Patch device registry
    with patch("custom_components.ectocontrol_modbus_controller.dr.async_get", return_value=fake_device_registry):
        result = await async_setup_entry(fake_hass, fake_config_entry)
        assert result is True

        # Verify components were created
        inst = fake_hass.data[DOMAIN][fake_config_entry.entry_id]
        assert inst is not None
        assert "gateway" in inst
        assert "coordinator" in inst

        # Verify gateway type
        gateway = inst["gateway"]
        assert isinstance(gateway, BoilerGateway)

        # Verify coordinator type
        coordinator = inst["coordinator"]
        assert isinstance(coordinator, BoilerDataUpdateCoordinator)


@pytest.mark.asyncio
@pytest.mark.pty
async def test_coordinator_poll(modbus_slave, pty_pair, fake_hass, fake_config_entry, fake_device_registry) -> None:
    """Test coordinator polling with virtual port."""
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


@pytest.mark.asyncio
@pytest.mark.pty
async def test_gateway_getters(modbus_slave, pty_pair, fake_hass, fake_config_entry, fake_device_registry) -> None:
    """Test BoilerGateway getters with virtual port."""
    master, slave = pty_pair

    fake_config_entry.data[CONF_PORT] = master
    fake_config_entry.data[CONF_SLAVE_ID] = 1

    # Initialize protocol manager
    from custom_components.ectocontrol_modbus_controller.modbus_protocol_manager import ModbusProtocolManager
    fake_hass.data[DOMAIN]["protocol_manager"] = ModbusProtocolManager()

    with patch("custom_components.ectocontrol_modbus_controller.dr.async_get", return_value=fake_device_registry):
        result = await async_setup_entry(fake_hass, fake_config_entry)
        assert result is True

        # Get gateway
        inst = fake_hass.data[DOMAIN][fake_config_entry.entry_id]
        gateway = inst["gateway"]

        # Trigger coordinator update to populate cache
        coordinator = inst["coordinator"]
        await coordinator._async_update_data()

        # Test temperature getters
        ch_temp = gateway.get_ch_temperature()
        assert ch_temp is not None
        assert abs(ch_temp - 16.6) < 0.1

        dhw_temp = gateway.get_dhw_temperature()
        assert dhw_temp is not None
        assert abs(dhw_temp - 34.8) < 0.5  # Allow for rounding tolerance

        # Test pressure getter
        pressure = gateway.get_pressure()
        assert pressure is not None
        assert abs(pressure - 1.8) < 0.1

        # Test flow getter
        flow = gateway.get_flow_rate()
        assert flow is not None
        assert abs(flow - 1.4) < 0.1

        # Test modulation getter
        modulation = gateway.get_modulation_level()
        assert modulation is not None
        assert modulation == 70

        # Test state getters
        burner_on = gateway.get_burner_on()
        assert burner_on is True

        heating_enabled = gateway.get_heating_enabled()
        assert heating_enabled is True

        dhw_enabled = gateway.get_dhw_enabled()
        assert dhw_enabled is True

        # Test CH setpoint active (read by coordinator)
        ch_setpoint_active = gateway.get_ch_setpoint_active()
        assert ch_setpoint_active is not None
        assert abs(ch_setpoint_active - 50.0) < 1.0  # 0x0C80 / 256 = 50.0°C


@pytest.mark.asyncio
@pytest.mark.pty
async def test_gateway_write_helpers(modbus_slave, pty_pair, fake_hass, fake_config_entry, fake_device_registry) -> None:
    """Test BoilerGateway write helpers with virtual port."""
    master, slave = pty_pair

    fake_config_entry.data[CONF_PORT] = master
    fake_config_entry.data[CONF_SLAVE_ID] = 1

    # Initialize protocol manager
    from custom_components.ectocontrol_modbus_controller.modbus_protocol_manager import ModbusProtocolManager
    fake_hass.data[DOMAIN]["protocol_manager"] = ModbusProtocolManager()

    with patch("custom_components.ectocontrol_modbus_controller.dr.async_get", return_value=fake_device_registry):
        result = await async_setup_entry(fake_hass, fake_config_entry)
        assert result is True

        # Get gateway
        inst = fake_hass.data[DOMAIN][fake_config_entry.entry_id]
        gateway = inst["gateway"]

        # Test writing CH setpoint
        result = await gateway.set_ch_setpoint(450)  # 45.0°C
        assert result is True

        # Give simulator time to process
        import asyncio
        await asyncio.sleep(0.1)

        # Verify write was received
        updated = modbus_slave.get_register(0x0031)
        assert updated == 450


@pytest.mark.asyncio
@pytest.mark.pty
async def test_device_info_updates(modbus_slave, pty_pair, fake_hass, fake_config_entry, fake_device_registry) -> None:
    """Test that device info is read correctly during setup."""
    master, slave = pty_pair

    fake_config_entry.data[CONF_PORT] = master
    fake_config_entry.data[CONF_SLAVE_ID] = 1

    # Initialize protocol manager
    from custom_components.ectocontrol_modbus_controller.modbus_protocol_manager import ModbusProtocolManager
    fake_hass.data[DOMAIN]["protocol_manager"] = ModbusProtocolManager()

    with patch("custom_components.ectocontrol_modbus_controller.dr.async_get", return_value=fake_device_registry):
        result = await async_setup_entry(fake_hass, fake_config_entry)
        assert result is True

        # Get gateway
        inst = fake_hass.data[DOMAIN][fake_config_entry.entry_id]
        gateway = inst["gateway"]

        # Trigger coordinator update to populate cache
        coordinator = inst["coordinator"]
        await coordinator._async_update_data()

        # Verify device info was read
        assert gateway.device_uid == 0x8ABCDE
        assert gateway.device_type == 0x14


@pytest.mark.asyncio
@pytest.mark.pty
async def test_register_status_monitoring(modbus_slave, pty_pair, fake_hass, fake_config_entry, fake_device_registry) -> None:
    """Test that register status monitoring works when status registers are read."""
    master, slave = pty_pair

    fake_config_entry.data[CONF_PORT] = master
    fake_config_entry.data[CONF_SLAVE_ID] = 1

    # Initialize protocol manager
    from custom_components.ectocontrol_modbus_controller.modbus_protocol_manager import ModbusProtocolManager
    fake_hass.data[DOMAIN]["protocol_manager"] = ModbusProtocolManager()

    with patch("custom_components.ectocontrol_modbus_controller.dr.async_get", return_value=fake_device_registry):
        result = await async_setup_entry(fake_hass, fake_config_entry)
        assert result is True

        # Get gateway
        inst = fake_hass.data[DOMAIN][fake_config_entry.entry_id]
        gateway = inst["gateway"]

        # Manually add status register to cache (simulating a read)
        gateway.cache[0x0048] = 0x0000  # Status for 0x0018

        # Check register status for CH temperature (should be valid)
        ch_temp_status = gateway.get_register_status(0x0018)
        assert ch_temp_status == 0x0000  # Valid


@pytest.mark.asyncio
@pytest.mark.pty
async def test_device_uid_required(modbus_slave, pty_pair, fake_hass, fake_config_entry, fake_device_registry) -> None:
    """Test that device UID is available after setup."""
    master, slave = pty_pair

    fake_config_entry.data[CONF_PORT] = master
    fake_config_entry.data[CONF_SLAVE_ID] = 1

    # Initialize protocol manager
    from custom_components.ectocontrol_modbus_controller.modbus_protocol_manager import ModbusProtocolManager
    fake_hass.data[DOMAIN]["protocol_manager"] = ModbusProtocolManager()

    with patch("custom_components.ectocontrol_modbus_controller.dr.async_get", return_value=fake_device_registry):
        result = await async_setup_entry(fake_hass, fake_config_entry)
        assert result is True

        # Get gateway
        inst = fake_hass.data[DOMAIN][fake_config_entry.entry_id]
        gateway = inst["gateway"]

        # UID should be available
        assert gateway.device_uid is not None
        assert gateway.device_uid == 0x8ABCDE
