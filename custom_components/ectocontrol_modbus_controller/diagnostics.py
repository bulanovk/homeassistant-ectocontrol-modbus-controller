"""Diagnostics support for Ectocontrol Modbus Controller integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry) -> dict[str, Any]:
    """Return diagnostics for the config entry (gateway cache and protocol info)."""
    _LOGGER.debug("Fetching diagnostics for config entry: %s", entry.entry_id)
    _LOGGER.debug("Config entry title: %s", entry.title)

    store = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not store:
        return {"error": "entry_not_setup"}

    gateway = store.get("gateway")
    protocol = store.get("protocol")
    coordinator = store.get("coordinator")

    slave_id = getattr(gateway, "slave_id", None)
    cache = getattr(gateway, "cache", {})
    port = getattr(protocol, "port", None)
    baudrate = getattr(protocol, "baudrate", None)
    coordinator_name = getattr(coordinator, "name", None)

    _LOGGER.debug("Gateway slave_id: %s", slave_id)
    _LOGGER.debug("Protocol port: %s, baudrate: %s", port, baudrate)
    _LOGGER.debug("Coordinator name: %s", coordinator_name)
    _LOGGER.debug("Cache size: %d registers", len(cache))

    diagnostics_data = {
        "slave_id": slave_id,
        "cache": cache,
        "protocol": {"port": port, "baudrate": baudrate},
        "coordinator_name": coordinator_name,
    }

    _LOGGER.debug("Diagnostics data prepared: %s", diagnostics_data)
    return diagnostics_data
