"""Climate platform for Ectocontrol Modbus Controller."""
from __future__ import annotations

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    async_add_entities([
        BoilerClimate(coordinator),
        DHWClimate(coordinator),
    ])


class BoilerClimate(CoordinatorEntity, ClimateEntity):
    """Basic climate entity backed by BoilerGateway via coordinator."""

    _attr_has_entity_name = True
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Boiler"

    @property
    def unique_id(self) -> str:
        gateway = self.coordinator.gateway
        # UID MUST be available for Ectocontrol adapters
        if not gateway.device_uid:
            raise ValueError("Device UID not available")
        identifier = f"uid_{gateway.get_device_uid_hex()}"
        return f"{DOMAIN}_{identifier}_climate"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for entity association."""
        return self.coordinator.gateway.get_device_info()

    @property
    def current_temperature(self) -> float | None:
        return self.coordinator.gateway.get_ch_temperature()

    @property
    def target_temperature(self) -> float | None:
        value = self.coordinator.gateway.get_ch_setpoint()
        # If setpoint is not available, use a sensible default
        if value is None:
            # Return the midpoint of min/max temp as a safe default
            min_temp = self.min_temp
            max_temp = self.max_temp
            return (min_temp + max_temp) / 2
        return value

    @property
    def hvac_action(self) -> HVACAction | None:
        burner = self.coordinator.gateway.get_burner_on()
        return HVACAction.HEATING if burner else HVACAction.IDLE

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature supported by the boiler."""
        min_limit = self.coordinator.gateway.get_ch_min_limit()
        return min_limit if min_limit is not None else 5.0

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature supported by the boiler."""
        max_limit = self.coordinator.gateway.get_ch_max_limit()
        return max_limit if max_limit is not None else 85.0

    @property
    def hvac_mode(self) -> HVACMode:
        enabled = self.coordinator.gateway.get_heating_enable_switch()
        return HVACMode.HEAT if enabled else HVACMode.OFF

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.HEAT:
            await self.coordinator.gateway.set_circuit_enable_bit(0, True)
        else:
            await self.coordinator.gateway.set_circuit_enable_bit(0, False)
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs) -> None:
        if ATTR_TEMPERATURE in kwargs:
            temp = kwargs[ATTR_TEMPERATURE]
            raw = int(round(temp * 10))
            await self.coordinator.gateway.set_ch_setpoint(raw)
            await self.coordinator.async_request_refresh()


class DHWClimate(CoordinatorEntity, ClimateEntity):
    """DHW climate entity controlling domestic hot water."""

    _attr_has_entity_name = True
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "DHW"

    @property
    def unique_id(self) -> str:
        gateway = self.coordinator.gateway
        # UID MUST be available for Ectocontrol adapters
        if not gateway.device_uid:
            raise ValueError("Device UID not available")
        identifier = f"uid_{gateway.get_device_uid_hex()}"
        return f"{DOMAIN}_{identifier}_dhw_climate"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for entity association."""
        return self.coordinator.gateway.get_device_info()

    @property
    def current_temperature(self) -> float | None:
        return self.coordinator.gateway.get_dhw_temperature()

    @property
    def target_temperature(self) -> float | None:
        value = self.coordinator.gateway.get_dhw_setpoint()
        # If setpoint is not available, use a sensible default
        if value is None:
            # Return the midpoint of min/max temp as a safe default
            min_temp = self.min_temp
            max_temp = self.max_temp
            return (min_temp + max_temp) / 2
        return value

    @property
    def hvac_action(self) -> HVACAction | None:
        # DHW doesn't have a burner action; use HEATING if enabled
        enabled = self.coordinator.gateway.get_dhw_enable_switch()
        return HVACAction.HEATING if enabled else HVACAction.IDLE

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature supported by DHW."""
        min_limit = self.coordinator.gateway.get_dhw_min_limit()
        return min_limit if min_limit is not None else 30.0

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature supported by DHW."""
        max_limit = self.coordinator.gateway.get_dhw_max_limit()
        return max_limit if max_limit is not None else 65.0

    @property
    def hvac_mode(self) -> HVACMode:
        enabled = self.coordinator.gateway.get_dhw_enable_switch()
        return HVACMode.HEAT if enabled else HVACMode.OFF

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.HEAT:
            await self.coordinator.gateway.set_circuit_enable_bit(1, True)
        else:
            await self.coordinator.gateway.set_circuit_enable_bit(1, False)
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs) -> None:
        if ATTR_TEMPERATURE in kwargs:
            temp = kwargs[ATTR_TEMPERATURE]
            raw = int(temp) & 0xFF
            await self.coordinator.gateway.set_dhw_setpoint(raw)
            await self.coordinator.async_request_refresh()
