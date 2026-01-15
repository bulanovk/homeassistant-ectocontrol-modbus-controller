"""Config flow for Ectocontrol Modbus Controller integration.

This integration uses a Hub-based architecture:
- One Hub entry per serial port (e.g., "Hub - COM3")
- Multiple Slave entries as children of the Hub (e.g., "Slave 1", "Slave 2")
- Hub stores port configuration and advanced settings
- Slaves store only slave_id and optional friendly name
"""
from __future__ import annotations

import asyncio
import logging
from fnmatch import fnmatch
from typing import Any

import serial.tools.list_ports
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_PORT,
    CONF_SLAVE_ID,
    CONF_NAME,
    CONF_DEBUG_MODBUS,
    CONF_POLLING_INTERVAL,
    CONF_RETRY_COUNT,
    CONF_READ_TIMEOUT,
    SERIAL_PORT_PATTERNS,
    DEFAULT_SCAN_INTERVAL,
    MODBUS_RETRY_COUNT,
    MODBUS_READ_TIMEOUT,
)
from .modbus_protocol import ModbusProtocol

_LOGGER = logging.getLogger(__name__)

# Hub entry stores port-level settings
HUB_ENTRY_FLAG = "hub_entry"
CONF_SLAVES = "slaves"  # List of slave configs in hub data


class EctocontrolConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Ectocontrol Modbus Controller."""

    VERSION = 1

    def __init__(self) -> None:
        self._errors: dict[str, str] = {}
        self._ports: list[str] = []

    @staticmethod
    def async_get_options_flow(config_entry):
        """Create options flow."""
        return EctocontrolOptionsFlow(config_entry)

    def _build_schema(self, defaults: dict[str, Any] | None = None) -> vol.Schema:
        """Build the form schema dynamically based on available ports."""
        if defaults is None:
            defaults = {}

        # Build the port schema field conditionally based on available ports
        if self._ports:
            port_schema = {
                vol.Required(
                    CONF_PORT, default=defaults.get(CONF_PORT, self._ports[0])
                ): vol.In(self._ports)
            }
        else:
            port_schema = {
                vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, "")): str
            }

        schema_dict = {
            **port_schema,
            vol.Required(
                CONF_SLAVE_ID, default=defaults.get(CONF_SLAVE_ID, 1)
            ): vol.Coerce(int),
            vol.Optional(
                CONF_NAME, default=defaults.get(CONF_NAME, "")
            ): str,
            vol.Optional(
                CONF_POLLING_INTERVAL,
                default=defaults.get(CONF_POLLING_INTERVAL, DEFAULT_SCAN_INTERVAL.seconds),
            ): vol.All(int, vol.Range(min=5, max=300)),
            vol.Optional(
                CONF_RETRY_COUNT,
                default=defaults.get(CONF_RETRY_COUNT, MODBUS_RETRY_COUNT),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0, max=10.0, step=1.0, mode="box"
                )
            ),
            vol.Optional(
                CONF_READ_TIMEOUT,
                default=defaults.get(CONF_READ_TIMEOUT, MODBUS_READ_TIMEOUT),
            ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=60.0)),
            vol.Optional(
                CONF_DEBUG_MODBUS, default=defaults.get(CONF_DEBUG_MODBUS, False)
            ): bool,
        }
        return vol.Schema(schema_dict)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        """Handle reconfiguration of the integration."""
        errors: dict[str, str] = {}

        # Get current entry from context
        entry = self._get_reconfigure_entry()
        current_data = entry.data

        # List all available serial ports and filter by supported patterns
        try:
            all_ports = await asyncio.to_thread(serial.tools.list_ports.comports)
            self._ports = [
                p.device for p in all_ports
                if any(fnmatch(p.device, pattern) for pattern in SERIAL_PORT_PATTERNS)
            ]
        except Exception as e:
            _LOGGER.error("Failed to list serial ports: %s", e)
            self._ports = []

        if user_input is not None:
            # Validate slave_id
            try:
                slave = int(user_input[CONF_SLAVE_ID])
                if not (1 <= slave <= 32):
                    errors[CONF_SLAVE_ID] = "invalid_range"
            except (ValueError, KeyError):
                errors[CONF_SLAVE_ID] = "invalid_number"

            if errors:
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=self._build_reconfigure_schema(current_data),
                    errors=errors,
                )

            # Check for EXACT duplicates (same port AND same slave_id)
            # Multiple slaves on same port are now supported
            for existing_entry in self.hass.config_entries.async_entries(DOMAIN):
                if (existing_entry.entry_id != entry.entry_id and
                    existing_entry.data.get(CONF_PORT) == user_input[CONF_PORT] and
                    existing_entry.data.get(CONF_SLAVE_ID) == slave):
                    errors[CONF_SLAVE_ID] = "already_configured"
                    return self.async_show_form(
                        step_id="reconfigure",
                        data_schema=self._build_reconfigure_schema(current_data),
                        errors=errors,
                    )

            # Test connection with new settings
            try:
                protocol = ModbusProtocol(
                    user_input[CONF_PORT],
                    debug_modbus=current_data.get(CONF_DEBUG_MODBUS, False)
                )
                connected = await protocol.connect()
                if not connected:
                    errors["base"] = "cannot_connect"
                    await protocol.disconnect()
                    return self.async_show_form(
                        step_id="reconfigure",
                        data_schema=self._build_reconfigure_schema(current_data),
                        errors=errors,
                    )

                try:
                    regs = await protocol.read_registers(
                        slave, 0x0010, 1,
                        timeout=current_data.get(CONF_READ_TIMEOUT, MODBUS_READ_TIMEOUT)
                    )
                finally:
                    await protocol.disconnect()

                if regs is None:
                    errors["base"] = "cannot_connect"
                    return self.async_show_form(
                        step_id="reconfigure",
                        data_schema=self._build_reconfigure_schema(current_data),
                        errors=errors,
                    )
            except Exception as e:
                _LOGGER.error("Connection test failed: %s", e)
                errors["base"] = "cannot_connect"
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=self._build_reconfigure_schema(current_data),
                    errors=errors,
                )

            # Success: update entry and reload
            return self.async_update_reload_and_abort(
                entry,
                data_updates={
                    CONF_PORT: user_input[CONF_PORT],
                    CONF_SLAVE_ID: slave,
                    CONF_NAME: user_input.get(CONF_NAME),
                },
            )

        # Show form with current values as defaults
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._build_reconfigure_schema(current_data),
            errors=errors,
        )

    def _build_reconfigure_schema(self, current_data: dict[str, Any]) -> vol.Schema:
        """Build schema for reconfigure flow (core settings only)."""
        # Build the port schema field conditionally based on available ports
        if self._ports:
            port_schema = {
                vol.Required(
                    CONF_PORT, default=current_data.get(CONF_PORT, self._ports[0])
                ): vol.In(self._ports)
            }
        else:
            port_schema = {
                vol.Required(CONF_PORT, default=current_data.get(CONF_PORT, "")): str
            }

        return vol.Schema({
            **port_schema,
            vol.Required(
                CONF_SLAVE_ID, default=current_data.get(CONF_SLAVE_ID, 1)
            ): vol.Coerce(int),
            vol.Optional(
                CONF_NAME, default=current_data.get(CONF_NAME, "")
            ): str,
        })

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step where user provides port and slave id."""
        # List all available serial ports and filter by supported patterns
        try:
            all_ports = await asyncio.to_thread(serial.tools.list_ports.comports)
            self._ports = [
                p.device for p in all_ports
                if any(fnmatch(p.device, pattern) for pattern in SERIAL_PORT_PATTERNS)
            ]
        except Exception as e:
            _LOGGER.error("Failed to list serial ports: %s", e)
            self._ports = []

        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=self._build_schema(), errors={}
            )

        # Validate slave id
        try:
            slave = int(user_input[CONF_SLAVE_ID])
            if not (1 <= slave <= 32):
                self._errors[CONF_SLAVE_ID] = "invalid_range"
        except (ValueError, KeyError):
            self._errors[CONF_SLAVE_ID] = "invalid_number"

        # Validate retry count
        try:
            retry_count = int(user_input.get(CONF_RETRY_COUNT, MODBUS_RETRY_COUNT))
            if retry_count < 0 or retry_count > 10:
                self._errors[CONF_RETRY_COUNT] = "invalid_range"
        except (ValueError, KeyError):
            self._errors[CONF_RETRY_COUNT] = "invalid_number"

        # Validate read timeout
        try:
            read_timeout = float(user_input.get(CONF_READ_TIMEOUT, MODBUS_READ_TIMEOUT))
            if not (0.1 <= read_timeout <= 60.0):
                self._errors[CONF_READ_TIMEOUT] = "invalid_range"
        except (ValueError, KeyError):
            self._errors[CONF_READ_TIMEOUT] = "invalid_number"

        if self._errors:
            return self.async_show_form(
                step_id="user",
                data_schema=self._build_schema(user_input),
                errors=self._errors,
            )

        # Check for EXACT duplicates (same port AND same slave_id)
        # Multiple slaves on same port are now supported
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if (
                entry.data.get(CONF_PORT) == user_input[CONF_PORT]
                and entry.data.get(CONF_SLAVE_ID) == slave
            ):
                self._errors[CONF_SLAVE_ID] = "already_configured"
                return self.async_show_form(
                    step_id="user",
                    data_schema=self._build_schema(user_input),
                    errors=self._errors,
                )

        # Show warning if other slaves exist on same port (info only)
        existing_slaves_on_port = [
            e.data.get(CONF_SLAVE_ID)
            for e in self.hass.config_entries.async_entries(DOMAIN)
            if e.data.get(CONF_PORT) == user_input[CONF_PORT]
        ]
        if existing_slaves_on_port:
            _LOGGER.info(
                "Adding slave_id=%s to port %s which already has slaves: %s",
                slave,
                user_input[CONF_PORT],
                existing_slaves_on_port,
            )

        # Attempt connection and basic read
        try:
            debug_modbus = user_input.get(CONF_DEBUG_MODBUS, False)
            polling_interval = user_input.get(
                CONF_POLLING_INTERVAL, DEFAULT_SCAN_INTERVAL.seconds
            )
            retry_count = user_input.get(CONF_RETRY_COUNT, MODBUS_RETRY_COUNT)
            read_timeout = user_input.get(CONF_READ_TIMEOUT, MODBUS_READ_TIMEOUT)

            protocol = ModbusProtocol(user_input[CONF_PORT], debug_modbus=debug_modbus)
            connected = await protocol.connect()
            if not connected:
                self._errors["base"] = "cannot_connect"
                await protocol.disconnect()
                return self.async_show_form(
                    step_id="user",
                    data_schema=self._build_schema(user_input),
                    errors=self._errors,
                )

            try:
                regs = await protocol.read_registers(slave, 0x0010, 1, timeout=read_timeout)
            finally:
                await protocol.disconnect()

            if regs is None:
                self._errors["base"] = "cannot_connect"
                return self.async_show_form(
                    step_id="user",
                    data_schema=self._build_schema(user_input),
                    errors=self._errors,
                )
        except Exception as e:
            _LOGGER.error("Connection test failed: %s", e)
            self._errors["base"] = "cannot_connect"
            return self.async_show_form(
                step_id="user",
                data_schema=self._build_schema(user_input),
                errors=self._errors,
            )

        # Extract port name for title
        port = user_input[CONF_PORT]
        port_name = port.split("/")[-1]  # Get last part of path

        # Build title - use port-based naming for visual grouping in UI
        friendly_name = user_input.get(CONF_NAME)
        if friendly_name:
            title = f"{port_name} - {friendly_name}"
        else:
            # Format: "COM3 - Slave 1" - this groups entries by port when sorted alphabetically
            title = f"{port_name} - Slave {slave}"

        # Create entry - device nesting will be handled by device registry
        return self.async_create_entry(
            title=title,
            data={
                CONF_PORT: user_input[CONF_PORT],
                CONF_SLAVE_ID: slave,
                CONF_NAME: user_input.get(CONF_NAME),
                CONF_DEBUG_MODBUS: debug_modbus,
                CONF_POLLING_INTERVAL: polling_interval,
                CONF_RETRY_COUNT: retry_count,
                CONF_READ_TIMEOUT: read_timeout,
            },
        )


class EctocontrolOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Ectocontrol Modbus Controller."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Handle options flow initial step."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self._config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_POLLING_INTERVAL,
                    default=options.get(CONF_POLLING_INTERVAL, DEFAULT_SCAN_INTERVAL.seconds),
                ): vol.All(int, vol.Range(min=5, max=300)),
                vol.Optional(
                    CONF_RETRY_COUNT,
                    default=options.get(CONF_RETRY_COUNT, MODBUS_RETRY_COUNT),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.0, max=10.0, step=1.0, mode="box"
                    )
                ),
                vol.Optional(
                    CONF_READ_TIMEOUT,
                    default=options.get(CONF_READ_TIMEOUT, MODBUS_READ_TIMEOUT),
                ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=60.0)),
                vol.Optional(
                    CONF_DEBUG_MODBUS,
                    default=options.get(CONF_DEBUG_MODBUS, False),
                ): bool,
            }),
        )
