"""Constants for the Ectocontrol Modbus integration."""
from datetime import timedelta

DOMAIN = "ectocontrol_modbus_controller"
CONF_PORT = "port"
CONF_SLAVE_ID = "slave_id"
CONF_NAME = "name"
CONF_DEBUG_MODBUS = "debug_modbus"
CONF_POLLING_INTERVAL = "polling_interval"
CONF_RETRY_COUNT = "retry_count"
CONF_READ_TIMEOUT = "read_timeout"

# Modbus parameters
MODBUS_BAUDRATE = 19200
MODBUS_TIMEOUT = 2.0
MODBUS_RETRY_COUNT = 3
MODBUS_READ_TIMEOUT = 3.0

# Serial port patterns to include (USB adapters, RS-485 converters, hardware serial)
# Linux: ttyUSB* (USB-Serial), ttyACM* (USB CDC), ttyAMA* (Raspberry Pi UART)
# Windows: COM*
# macOS: cu.* or tty.*
SERIAL_PORT_PATTERNS = [
    "/dev/ttyUSB*",   # Linux USB-Serial adapters (FTDI, CP210x, CH340, etc.)
    "/dev/ttyACM*",   # Linux USB CDC devices (Arduino, etc.)
    "/dev/ttyAMA*",   # Raspberry Pi hardware UART
    "/dev/ttyS*",     # Linux hardware serial ports
    "COM*",           # Windows COM ports
    "/dev/cu.*",      # macOS serial ports (call-out)
    "/dev/tty.*",     # macOS serial ports (terminal)
]

# Generic Device Information Registers (0x0000-0x0003)
# Per MODBUS_PROTOCOL.md section 3.0 - common to all Ectocontrol devices
REGISTER_RESERVED = 0x0000
REGISTER_UID = 0x0001           # u24 (3 bytes): unique device identifier
REGISTER_ADDRESS = 0x0002       # MSB: reserved, LSB: device Modbus address (0x01-0x20)
REGISTER_TYPE_CHANNELS = 0x0003 # MSB: device type, LSB: channel count (1-10)

# Device Type Codes (from MODBUS_PROTOCOL.md section 3.0)
DEVICE_TYPE_OPENTHERM_V1 = 0x11     # OpenTherm Adapter v1 (discontinued)
DEVICE_TYPE_OPENTHERM_V2 = 0x14     # OpenTherm Adapter v2 (current)
DEVICE_TYPE_EBUS = 0x15             # eBus Adapter
DEVICE_TYPE_NAVIEN = 0x16           # Navien Adapter
DEVICE_TYPE_TEMP_SENSOR = 0x22      # Temperature Sensor
DEVICE_TYPE_HUMIDITY_SENSOR = 0x23  # Humidity Sensor
DEVICE_TYPE_CONTACT_SENSOR = 0x50   # Universal Contact Sensor
DEVICE_TYPE_CONTACT_SPLITTER = 0x59 # 10-channel Contact Sensor Splitter
DEVICE_TYPE_RELAY_2CH = 0xC0        # 2-channel Relay Control Block
DEVICE_TYPE_RELAY_10CH = 0xC1       # 10-channel Relay Control Block

DEVICE_TYPE_NAMES = {
    0x11: "OpenTherm Adapter v1",
    0x14: "OpenTherm Adapter v2",
    0x15: "eBus Adapter",
    0x16: "Navien Adapter",
    0x22: "Temperature Sensor",
    0x23: "Humidity Sensor",
    0x50: "Contact Sensor",
    0x59: "Contact Splitter",  # Updated: dynamic channel count (1-10)
    0x59: "Contact Splitter 10ch",
    0xC0: "Relay Block 2ch",
    0xC1: "Relay Block 10ch",
}

# Contact Sensor Splitter Registers (Device Type 0x59)
# Per Russian documentation MODBUS_PROTOCOL_RU.md section 3.2 "ДИСКРЕТНЫЕ ДАТЧИКИ"
# Bitfield registers for contact states (1-10 channels)
REGISTER_CONTACT_CHANNELS_1_8 = 0x0010   # Channels 1-8 bitfield (bits 0-7)
REGISTER_CONTACT_CHANNELS_9_10 = 0x0011  # Channels 9-10 bitfield (bits 0-2)

# Adapter Type Codes from REGISTER_STATUS (0x0010 bits 0-2)
# Per Russian documentation (MODBUS_PROTOCOL_RU.md) - more specific than English docs
ADAPTER_TYPE_OPENTHERM = 0x00     # 000 = Opentherm
ADAPTER_TYPE_EBUS = 0x01          # 001 = eBus
ADAPTER_TYPE_NAVIEN = 0x02        # 010 = Navien
# 0x03-0x07 = Reserved

ADAPTER_TYPE_NAMES = {
    0x00: "OpenTherm",
    0x01: "eBus",
    0x02: "Navien",
}

# Communication Status Bit (REGISTER_STATUS bit 3)
# Per Russian documentation (VERIFIED CORRECT):
# - Bit 3 = 0: No response from boiler (disconnected/error)
# - Bit 3 = 1: Response received from boiler (connected/OK)
# Note: English documentation has this bit inverted, but Russian docs are correct.
STATUS_BIT_NO_RESPONSE = 0x00    # No response from boiler
STATUS_BIT_RESPONSE_RECEIVED = 0x01  # Response received (connected)

# Status & Diagnostics Register addresses (0x0010+)
REGISTER_STATUS = 0x0010
REGISTER_VERSION = 0x0011
REGISTER_UPTIME = 0x0012
REGISTER_CH_TEMP = 0x0018
REGISTER_DHW_TEMP = 0x0019
REGISTER_PRESSURE = 0x001A
REGISTER_FLOW = 0x001B
REGISTER_MODULATION = 0x001C
REGISTER_STATES = 0x001D
REGISTER_MAIN_ERROR = 0x001E
REGISTER_ADD_ERROR = 0x001F
REGISTER_OUTDOOR_TEMP = 0x0020
REGISTER_MFG_CODE = 0x0021
REGISTER_MODEL_CODE = 0x0022
REGISTER_OT_ERROR = 0x0023
REGISTER_CH_SETPOINT_ACTIVE = 0x0026

REGISTER_CH_SETPOINT = 0x0031
REGISTER_EMERGENCY_CH = 0x0032
REGISTER_CH_MIN = 0x0033
REGISTER_CH_MAX = 0x0034
REGISTER_DHW_MIN = 0x0035
REGISTER_DHW_MAX = 0x0036
REGISTER_DHW_SETPOINT = 0x0037
REGISTER_MAX_MODULATION = 0x0038
REGISTER_CIRCUIT_ENABLE = 0x0039

REGISTER_COMMAND = 0x0080
REGISTER_COMMAND_RESULT = 0x0081

# Register Status/Health Monitoring (0x0040-0x006F)
# Per Russian documentation: 48 registers providing status for registers 0x0010-0x003F
# Status for register R is at address R + 0x30
REGISTER_STATUS_BASE = 0x0040

# Register Status Codes (from Russian documentation)
# Per MODBUS_PROTOCOL_RU.md - registers 0x0040-0x006F (i16, RO)
REG_STATUS_VALID = 0               # Data valid (read) / Accepted by boiler (write)
REG_STATUS_NOT_INITIALIZED = 1      # No data read yet / No value set for writing
REG_STATUS_NOT_SUPPORTED = -1       # Register not supported by boiler
REG_STATUS_READ_WRITE_ERROR = -2    # Read/write error to boiler

# Command Result Codes (from Russian documentation)
# Per MODBUS_PROTOCOL_RU.md - register 0x0081 (i16, RO)
CMD_RESULT_SUCCESS = 0              # Command executed successfully
CMD_RESULT_NO_COMMAND = 1           # No command (default value)
CMD_RESULT_PROCESSING = 2           # Command processing in progress
CMD_RESULT_TIMEOUT = -1             # No response received within timeout
CMD_RESULT_NOT_SUPPORTED_ADAPTER = -2   # Command not supported by adapter
CMD_RESULT_NOT_SUPPORTED_BOILER = -3    # Device ID not supported by boiler
CMD_RESULT_EXECUTION_ERROR = -5     # Command execution error
# -32768 to -6: Reserved

DEFAULT_SCAN_INTERVAL = timedelta(seconds=15)
