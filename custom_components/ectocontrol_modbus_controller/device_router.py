"""Device router for Ectocontrol Modbus devices.

This module provides automatic device type detection and routing to the appropriate
gateway class based on the device type read from the generic device information.
"""
from __future__ import annotations

import logging
from typing import Union

_LOGGER = logging.getLogger(__name__)


async def create_device_gateway(
    protocol,
    slave_id: int,
    debug_modbus: bool = False
) -> Union["BoilerGateway", "ContactSensorGateway"]:
    """Detect device type and create appropriate gateway instance.

    This function reads the generic device information from registers 0x0000-0x0003
    to determine the device type, then creates and returns the appropriate gateway
    instance with device info already loaded.

    Supported Device Types:
        - 0x59: Contact Sensor Splitter (1-10 channels)
        - 0x14: OpenTherm Adapter v2 (boiler)
        - 0x15: eBus Adapter (boiler)
        - 0x16: Navien Adapter (boiler)

    Args:
        protocol: ModbusProtocol instance for communication
        slave_id: Modbus slave ID (1-32)

    Returns:
        ContactSensorGateway: For device type 0x59 (Contact Sensor Splitter)
        BoilerGateway: For device types 0x14, 0x15, 0x16 (boiler adapters)

    Raises:
        ValueError: If device info cannot be read or device type is not supported
    """
    # Read generic device info registers (0x0000-0x0003)
    regs = await protocol.read_registers(slave_id, 0x0000, 4)

    if regs is None or len(regs) < 4:
        _LOGGER.error("Failed to read device info registers for slave_id=%s", slave_id)
        raise ValueError(
            f"Failed to read device info for slave_id={slave_id}. "
            "Check device is connected and configured correctly."
        )

    # Extract device type (MSB of register 0x0003)
    device_type = (regs[3] >> 8) & 0xFF
    channel_count = regs[3] & 0xFF

    _LOGGER.info(
        "Device detected for slave_id=%s: type=0x%02X, channels=%d",
        slave_id,
        device_type,
        channel_count
    )

    # Route to appropriate gateway based on device type
    if device_type == 0x59:
        # Contact Sensor Splitter
        from .contact_gateway import ContactSensorGateway

        gateway = ContactSensorGateway(protocol, slave_id, debug_modbus=debug_modbus)
        _LOGGER.info("Creating ContactSensorGateway for slave_id=%s", slave_id)

    elif device_type in [0x14, 0x15, 0x16]:
        # Boiler adapters (OpenTherm v2, eBus, Navien)
        from .boiler_gateway import BoilerGateway

        gateway = BoilerGateway(protocol, slave_id, debug_modbus=debug_modbus)
        _LOGGER.info("Creating BoilerGateway for slave_id=%s (device type=0x%02X)", slave_id, device_type)

    else:
        # Unsupported device type
        _LOGGER.error(
            "Unsupported device type 0x%02X for slave_id=%s",
            device_type,
            slave_id
        )
        raise ValueError(
            f"Unsupported device type: 0x{device_type:02X} (slave_id={slave_id}). "
            f"Supported types: 0x59 (Contact Splitter), 0x14/0x15/0x16 (Boiler Adapters)"
        )

    # Read device info (UID, device type, channel count)
    try:
        success = await gateway.read_device_info()
        if not success:
            _LOGGER.error("Failed to read device info for slave_id=%s", slave_id)
            raise ValueError(
                f"Failed to read device info for slave_id={slave_id}. "
                "Device may not support the generic device info structure."
            )
    except Exception as err:
        _LOGGER.error("Error reading device info for slave_id=%s: %s", slave_id, err)
        raise ValueError(
            f"Error reading device info for slave_id={slave_id}: {err}"
        )

    # Log device details
    _LOGGER.info(
        "Device created for slave_id=%s: UID=0x%06X, type=%s, channels=%d",
        slave_id,
        gateway.device_uid,
        gateway.get_device_type_name(),
        gateway.channel_count
    )

    return gateway
