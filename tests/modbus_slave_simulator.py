"""Modbus RTU slave simulator for Ectocontrol device testing.

This module implements a lightweight Modbus RTU slave that simulates
Ectocontrol devices (boiler controllers, contact sensors, etc.) for
integration testing with virtual serial ports (socat PTY).

Supports standard Modbus function codes:
- 0x03: Read Holding Registers
- 0x06: Write Single Register (optional)
- 0x10: Write Multiple Registers (optional)
"""
from __future__ import annotations

import asyncio
import logging
import struct
from typing import Optional

import serial

_LOGGER = logging.getLogger(__name__)


class ModbusSlaveSimulator:
    """Simulated Ectocontrol Modbus RTU slave device.

    This simulator listens on a serial port and responds to Modbus
    RTU requests. It implements the Ectocontrol register map for
    testing the integration without physical hardware.
    """

    def __init__(self, port: str, slave_id: int = 1, device_type: int = 0x14):
        """Initialize the Modbus slave simulator.

        Args:
            port: Serial port device path (e.g., /dev/pts/1)
            slave_id: Modbus slave ID (1-32)
            device_type: Ectocontrol device type code (default: 0x14 = OpenTherm Adapter v2)
        """
        self.port = port
        self.slave_id = slave_id
        self.device_type = device_type
        self.registers: dict[int, int] = {}
        self.running = False

        # Error injection flags
        self._timeout_mode = False
        self._corrupt_crc = False
        self._malformed_response = False
        self._wrong_slave_id_response = False

        # Initialize register map
        self._init_registers()

        # Statistics
        self._request_count = 0
        self._error_count = 0

    def _init_registers(self) -> None:
        """Initialize register map with default values for OpenTherm Adapter v2."""
        # Generic device info (0x0000-0x0003)
        # Per Russian documentation MODBUS_PROTOCOL_RU.md:
        #   UID is 3 bytes in big-endian order: MSB (byte 1), mid (byte 2), LSB (byte 3)
        #   Register 0x0000: RSVD (MSB), UID MSB (LSB)
        #   Register 0x0001: UID middle (MSB), UID LSB (LSB)
        # Example: UID = 0x8ABCDE → bytes 8A BC DE (big-endian)
        #   Register 0x0000 = 0x008A (RSVD=0x00, UID MSB=0x8A)
        #   Register 0x0001 = 0xBCDE (UID mid=0xBC, LSB=0xDE)
        self.registers = {
            0x0000: 0x008A,  # RSVD (0x00) + UID byte 1 MSB (0x8A)
            0x0001: 0xBCDE,  # UID byte 3 MSB (0xBC) + byte 2 (0xDE)
            0x0002: 0x0000,  # Not used for UID in protocol
            0x0003: (self.device_type << 8) | 0x04,  # Device type + channel count
        }

        # Status & diagnostics (0x0010-0x0013)
        self.registers.update({
            0x0010: 0x0009,  # Status: OpenTherm (0), boiler connected (bit 3)
            0x0011: 0x012C,  # Version: HW=1, SW=44
            0x0012: 0x0000,  # Uptime high (0 seconds)
            0x0013: 0x001E,  # Uptime low (30 seconds)
        })

        # Boiler sensors (0x0018-0x0026)
        self.registers.update({
            0x0018: 0x00A6,  # CH temp: 16.6°C (166 / 10)
            0x0019: 0x0158,  # DHW temp: 34.8°C (348 / 10)
            0x001A: 0x0012,  # Pressure: 1.8 bar (18 / 10, LSB)
            0x001B: 0x000E,  # Flow: 1.4 L/min (14 / 10, LSB)
            0x001C: 0x0046,  # Modulation: 70% (LSB)
            0x001D: 0x0007,  # States: burner on (bit 0), heating on (bit 1), DHW on (bit 2)
            0x001E: 0x0000,  # Main error: no error
            0x001F: 0x0000,  # Additional error: no error
            0x0020: 0x000A,  # Outdoor temp: 10°C (MSB, signed)
            0x0021: 0x0000,  # Manufacturer code: 0 (Ectostroy)
            0x0022: 0x0000,  # Model code: 0
            0x0023: 0x0000,  # OpenTherm error: no error
            0x0024: 0x0000,  # Reserved
            0x0025: 0x0000,  # Reserved
            0x0026: 0x3200,  # CH setpoint active: 50.0°C (12800 / 256)
        })

        # Temperature limits & setpoints (0x0031-0x0039)
        self.registers.update({
            0x0031: 0x0314,  # CH setpoint: 50.0°C (500 / 10)
            0x0032: 0x0314,  # Emergency CH setpoint: 50.0°C
            0x0033: 0x2300,  # CH min limit: 35°C (MSB)
            0x0034: 0x5A00,  # CH max limit: 90°C (MSB)
            0x0035: 0x2800,  # DHW min limit: 40°C (MSB)
            0x0036: 0x4600,  # DHW max limit: 70°C (MSB)
            0x0037: 0x3C00,  # DHW setpoint: 60°C (MSB)
            0x0038: 0x6400,  # Max modulation: 100% (MSB)
            0x0039: 0x0003,  # Circuit enable: heating on (bit 0), DHW on (bit 1)
        })

        # Command registers (0x0080-0x0081)
        self.registers.update({
            0x0080: 0x0001,  # Command: no command (default)
            0x0081: 0x0001,  # Command result: no command
        })

        # Register status monitoring (0x0040-0x006F)
        # Status for register R is at address R + 0x30
        for addr in range(0x0010, 0x0040):
            self.registers[addr + 0x30] = 0x0000  # All valid

    def set_register(self, addr: int, value: int) -> None:
        """Set a register value (for test control).

        Args:
            addr: Register address
            value: 16-bit register value
        """
        self.registers[addr] = value & 0xFFFF
        _LOGGER.debug("Simulator: Set register 0x%04X = 0x%04X", addr, value)

    def get_register(self, addr: int) -> Optional[int]:
        """Get a register value.

        Args:
            addr: Register address

        Returns:
            Register value or None if not found
        """
        return self.registers.get(addr)

    def inject_error(self, error_type: str) -> None:
        """Inject an error condition for testing.

        Args:
            error_type: Type of error to inject:
                - "timeout": Simulate timeout (don't respond)
                - "corrupt_crc": Send invalid CRC in response
                - "malformed": Send malformed response
                - "wrong_slave": Respond with wrong slave ID
        """
        if error_type == "timeout":
            self._timeout_mode = True
        elif error_type == "corrupt_crc":
            self._corrupt_crc = True
        elif error_type == "malformed":
            self._malformed_response = True
        elif error_type == "wrong_slave":
            self._wrong_slave_id_response = True
        else:
            _LOGGER.warning("Unknown error type: %s", error_type)

    def clear_errors(self) -> None:
        """Clear all error injection flags."""
        self._timeout_mode = False
        self._corrupt_crc = False
        self._malformed_response = False
        self._wrong_slave_id_response = False

    async def start(self) -> None:
        """Start the Modbus slave simulator.

        This method runs in a loop, listening for Modbus requests
        and responding to them. Run this as a background task.
        """
        _LOGGER.info("Starting Modbus slave simulator on %s (slave_id=%d)",
                     self.port, self.slave_id)

        try:
            ser = serial.Serial(
                port=self.port,
                baudrate=19200,
                bytesize=8,
                parity="N",
                stopbits=1,
                timeout=0.1,  # Short timeout for non-blocking reads
            )
            self.running = True
        except Exception as exc:
            _LOGGER.error("Failed to open serial port %s: %s", self.port, exc)
            raise

        try:
            while self.running:
                # Read and process one request
                request = self._read_frame(ser)
                if request is None:
                    # Log periodically to show simulator is alive
                    self._debug_counter = getattr(self, '_debug_counter', 0) + 1
                    if self._debug_counter % 50 == 0:  # Log every 50 iterations
                        _LOGGER.debug("Simulator: Waiting for request... (in_waiting=%d)", ser.in_waiting)
                    continue

                self._request_count += 1
                _LOGGER.info("Simulator: Received %d bytes, function=0x%02X", len(request), request[1] if len(request) > 1 else 0)

                # Check for timeout mode
                if self._timeout_mode:
                    _LOGGER.debug("Simulator: Timeout mode, not responding")
                    continue

                # Process request and generate response
                response = self._process_request(request)

                if response:
                    ser.write(response)
                    _LOGGER.debug("Simulator: Sent %d bytes", len(response))
                else:
                    _LOGGER.debug("Simulator: No response (request not for us or error)")

        finally:
            ser.close()
            _LOGGER.info("Modbus slave simulator stopped")

    def stop(self) -> None:
        """Stop the simulator."""
        _LOGGER.info("Stopping Modbus slave simulator")
        self.running = False

    def _read_frame(self, ser: serial.Serial) -> Optional[bytes]:
        """Read a complete Modbus RTU frame.

        Args:
            ser: Serial port object

        Returns:
            Complete frame including CRC, or None if incomplete/timeout
        """
        # Read slave ID (1 byte)
        if ser.in_waiting == 0:
            return None

        slave_id = ser.read(1)
        if not slave_id:
            return None

        # Read function code (1 byte)
        func_code = ser.read(1)
        if not func_code:
            return None

        # Parse frame based on function code
        func = func_code[0]

        if func == 0x03:  # Read Holding Registers
            # Request: slave(1) + func(1) + start(2) + count(2) + CRC(2) = 8 bytes
            remaining = ser.read(6)
            if len(remaining) < 6:
                return None
            return slave_id + func_code + remaining

        elif func == 0x06:  # Write Single Register
            # Request: slave(1) + func(1) + addr(2) + value(2) + CRC(2) = 8 bytes
            remaining = ser.read(6)
            if len(remaining) < 6:
                return None
            return slave_id + func_code + remaining

        elif func == 0x10:  # Write Multiple Registers
            # Read address (2 bytes), quantity (2 bytes), and byte count (1 byte)
            header = ser.read(5)
            if len(header) < 5:
                return None

            # Extract byte count (5th byte after address and quantity)
            byte_count = header[4]
            
            # Debug: log what we received so far
            frame_so_far = slave_id + func_code + header
            _LOGGER.info("Simulator: WM header so far (%d bytes): %s", len(frame_so_far), frame_so_far.hex(' '))
            
            # Read data + CRC (byte_count + 2)
            # Use read() with timeout to ensure we get all bytes
            remaining = bytearray()
            bytes_needed = byte_count + 2
            
            while len(remaining) < bytes_needed:
                chunk = ser.read(bytes_needed - len(remaining))
                if not chunk:
                    break
                remaining.extend(chunk)
            
            if len(remaining) < bytes_needed:
                _LOGGER.warning("WM: Expected %d bytes, got %d", bytes_needed, len(remaining))
                return None

            full_frame = slave_id + func_code + header + bytes(remaining)
            _LOGGER.info("Simulator: WM full frame (%d bytes): %s", len(full_frame), full_frame.hex(' '))

            return slave_id + func_code + header + bytes(remaining)

        else:
            # Unknown function code, try to read a reasonable amount
            remaining = ser.read(10)
            return slave_id + func_code + remaining

    def _process_request(self, request: bytes) -> Optional[bytes]:
        """Process a Modbus request and generate response.

        Args:
            request: Complete Modbus RTU request frame

        Returns:
            Response frame or None if error
        """
        if len(request) < 4:
            return None

        slave_id = request[0]
        func_code = request[1]

        # Check if request is for us
        if slave_id != self.slave_id:
            _LOGGER.debug("Simulator: Request for slave %d, we are %d",
                         slave_id, self.slave_id)
            return None

        # Route to function handler
        if func_code == 0x03:
            return self._handle_read_holding_registers(request)
        elif func_code == 0x06:
            return self._handle_write_single_register(request)
        elif func_code == 0x10:
            return self._handle_write_multiple_registers(request)
        else:
            # Unsupported function code - return exception response
            return self._build_exception_response(func_code, 0x01)

    def _handle_read_holding_registers(self, request: bytes) -> Optional[bytes]:
        """Handle function code 0x03 (Read Holding Registers).

        Args:
            request: Request frame (8 bytes)

        Returns:
            Response frame
        """
        if len(request) != 8:
            return None

        # Parse request
        start_addr = (request[2] << 8) | request[3]
        count = (request[4] << 8) | request[5]

        _LOGGER.debug("Simulator: Read holding registers addr=0x%04X count=%d",
                     start_addr, count)

        # Build response data
        data = []
        for i in range(count):
            reg_addr = start_addr + i
            value = self.registers.get(reg_addr, 0x0000)
            data.append((value >> 8) & 0xFF)  # MSB
            data.append(value & 0xFF)        # LSB

        # Build response frame (without CRC)
        response = bytes([
            self.slave_id,      # Slave ID
            0x03,               # Function code
            len(data),          # Byte count
            *data,              # Register data
        ])

        # Add CRC
        crc = self._calculate_crc(response)
        return response + crc

    def _handle_write_single_register(self, request: bytes) -> Optional[bytes]:
        """Handle function code 0x06 (Write Single Register).

        Args:
            request: Request frame (8 bytes)

        Returns:
            Response frame (echo of request)
        """
        if len(request) != 8:
            return None

        # Parse request
        addr = (request[2] << 8) | request[3]
        value = (request[4] << 8) | request[5]

        _LOGGER.debug("Simulator: Write single register addr=0x%04X value=0x%04X",
                     addr, value)

        # Update register
        self.registers[addr] = value

        # Response echoes the request (without CRC)
        response = request[:6]
        crc = self._calculate_crc(response)
        return response + crc

    def _handle_write_multiple_registers(self, request: bytes) -> Optional[bytes]:
        """Handle function code 0x10 (Write Multiple Registers).

        Args:
            request: Request frame (variable length)

        Returns:
            Response frame
        """
        if len(request) < 11:
            _LOGGER.warning("Write multiple registers request too short: %d bytes", len(request))
            return None

        # Parse request
        slave_id = request[0]
        func_code = request[1]
        start_addr = (request[2] << 8) | request[3]
        count = (request[4] << 8) | request[5]
        byte_count = request[6]

        _LOGGER.info("Simulator: Write multiple regs slave=%d addr=0x%04X count=%d byte_count=%d",
                     slave_id, start_addr, count, byte_count)

        # Extract register values
        data = request[7:7 + byte_count]

        # Update registers
        for i in range(count):
            reg_addr = start_addr + i
            if i * 2 + 1 < len(data):
                value = (data[i * 2] << 8) | data[i * 2 + 1]
                self.registers[reg_addr] = value
                _LOGGER.info("Simulator: Set register 0x%04X = 0x%04X (data[%d]=%s)",
                             reg_addr, value, i, data.hex(' '))

        # Build response (echo address and count)
        response = bytes([
            self.slave_id,      # Slave ID
            0x10,               # Function code
            (start_addr >> 8) & 0xFF,
            start_addr & 0xFF,
            (count >> 8) & 0xFF,
            count & 0xFF,
        ])

        crc = self._calculate_crc(response)
        return response + crc

    def _build_exception_response(self, func_code: int, exception_code: int) -> bytes:
        """Build a Modbus exception response.

        Args:
            func_code: Original function code
            exception_code: Exception code (0x01-0x04)

        Returns:
            Exception response frame
        """
        response = bytes([
            self.slave_id,              # Slave ID
            func_code | 0x80,           # Function code + error bit
            exception_code,             # Exception code
        ])

        crc = self._calculate_crc(response)
        return response + crc

    @staticmethod
    def _calculate_crc(frame: bytes) -> bytes:
        """Calculate Modbus CRC-16 (IBM polynomial).

        Args:
            frame: Frame data (without CRC)

        Returns:
            2-byte CRC (little-endian)
        """
        crc = 0xFFFF

        for byte in frame:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1

        return bytes([crc & 0xFF, (crc >> 8) & 0xFF])

    @property
    def request_count(self) -> int:
        """Get number of requests received."""
        return self._request_count

    @property
    def error_count(self) -> int:
        """Get number of errors encountered."""
        return self._error_count
