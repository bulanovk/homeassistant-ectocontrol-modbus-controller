"""Async-friendly wrapper around modbus-tk RTU master.

Uses run_in_executor to wrap the synchronous `modbus_tk.modbus_rtu.RtuMaster` API.
"""
from __future__ import annotations

import asyncio
import logging
from typing import List, Optional, Callable

import serial
import modbus_tk.defines as cst
import modbus_tk.modbus as modbus
import modbus_tk.modbus_rtu as modbus_rtu

_LOGGER = logging.getLogger(__name__)


class DebugSerial:
    """Wrapper around serial.Serial that logs all raw bytes sent/received.

    This is useful for debugging Modbus communication issues.
    """

    def __init__(self, serial_instance: serial.Serial, name: str = "MODBUS"):
        self._serial = serial_instance
        self._name = name
        self._logger = logging.getLogger(f"{__name__}.{name}")
        self._last_tx: bytes = b""
        self._last_rx: bytes = b""
        self._last_rx_with_data: bytes = b""  # Store last non-empty RX

    def read(self, size: int = 1) -> bytes:
        """Read and log bytes from serial port."""
        data = self._serial.read(size)
        self._last_rx = data
        if data:
            self._last_rx_with_data = data  # Store for error reporting
            self._logger.debug("%s RX (%d bytes): %s", self._name, len(data), data.hex(" "))
        else:
            self._logger.debug("%s RX: timeout (0 bytes)", self._name)
        return data

    def write(self, data: bytes) -> int:
        """Write and log bytes to serial port."""
        self._last_tx = data
        self._logger.debug("%s TX (%d bytes): %s", self._name, len(data), data.hex(" "))
        return self._serial.write(data)

    def get_last_tx_rx(self) -> tuple[bytes, bytes]:
        """Get last TX and RX bytes for error reporting."""
        # Return the last non-empty RX if available, otherwise use last_rx
        rx_data = self._last_rx_with_data if self._last_rx_with_data else self._last_rx
        return self._last_tx, rx_data

    def flush(self) -> None:
        """Flush serial port buffers."""
        self._serial.flush()

    def flushInput(self) -> None:
        """Flush input buffer."""
        self._serial.flushInput()

    def flushOutput(self) -> None:
        """Flush output buffer."""
        self._serial.flushOutput()

    def close(self) -> None:
        """Close serial port."""
        self._serial.close()

    def isOpen(self) -> bool:
        """Check if serial port is open."""
        return self._serial.isOpen()

    def in_waiting(self) -> int:
        """Get number of bytes waiting in input buffer."""
        return getattr(self._serial, "in_waiting", getattr(self._serial, "inWaiting", lambda: 0)())

    @property
    def port(self) -> str:
        """Get port name."""
        return self._serial.port

    @property
    def baudrate(self) -> int:
        """Get baud rate."""
        return self._serial.baudrate

    @property
    def bytesize(self) -> int:
        """Get byte size."""
        return self._serial.bytesize

    @property
    def parity(self) -> str:
        """Get parity."""
        return self._serial.parity

    @property
    def stopbits(self) -> int:
        """Get stop bits."""
        return self._serial.stopbits

    @property
    def timeout(self) -> float:
        """Get timeout."""
        return self._serial.timeout

    @timeout.setter
    def timeout(self, value: float) -> None:
        """Set timeout."""
        self._serial.timeout = value

    def __getattr__(self, name: str):
        """Forward any other attributes to wrapped serial instance."""
        return getattr(self._serial, name)


class ModbusProtocol:
    """Async wrapper for modbus-tk RTU master.

    Methods return `None` or `False` on error to simplify callers.
    """

    def __init__(
        self,
        port: str,
        baudrate: int = 19200,
        timeout: float = 2.0,
        debug_modbus: bool = False,
    ):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.debug_modbus = debug_modbus
        self.client = None
        self._lock = asyncio.Lock()
        self._debug_serial: Optional[DebugSerial] = None

    def _get_last_tx_rx(self) -> tuple[bytes, bytes]:
        """Get last TX/RX bytes if debug mode is enabled."""
        if self._debug_serial:
            return self._debug_serial.get_last_tx_rx()
        return b"", b""

    def _connect_sync(self):
        ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=self.timeout,
        )
        if self.debug_modbus:
            # Extract base port name for logger (e.g., "pts2" from "/dev/pts/2")
            port_name = self.port.replace("/", "_").strip("_")
            self._debug_serial = DebugSerial(ser, name=f"MODBUS_{port_name}")
            ser = self._debug_serial
            _LOGGER.info("Modbus debug logging enabled for %s", self.port)
        master = modbus_rtu.RtuMaster(ser)
        master.set_timeout(self.timeout)
        master.open()
        return master

    async def connect(self) -> bool:
        loop = asyncio.get_event_loop()
        try:
            self.client = await loop.run_in_executor(None, self._connect_sync)
            _LOGGER.debug("Modbus connected on %s", self.port)
            return True
        except Exception as exc:  # pragma: no cover - intentional broad catch
            _LOGGER.error("Failed to open Modbus port %s: %s", self.port, exc)
            self.client = None
            return False

    async def disconnect(self) -> None:
        if not self.client:
            return
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self.client.close)
        except Exception:
            _LOGGER.debug("Error closing modbus client", exc_info=True)
        finally:
            self.client = None

    @property
    def is_connected(self) -> bool:
        return self.client is not None

    async def read_registers(
        self, slave_id: int, start_addr: int, count: int, timeout: Optional[float] = None
    ) -> Optional[List[int]]:
        """Read holding registers (function 0x03).

        Returns list of register values or None on error.
        """
        if not self.client:
            _LOGGER.warning("Modbus client not connected")
            return None

        async with self._lock:
            loop = asyncio.get_event_loop()
            try:
                if timeout is not None:
                    self.client.set_timeout(timeout)
                result = await loop.run_in_executor(
                    None,
                    self.client.execute,
                    slave_id,
                    cst.READ_HOLDING_REGISTERS,
                    start_addr,
                    count,
                )
                return list(result)
            except modbus.ModbusError as exc:
                tx, rx = self._get_last_tx_rx()
                tx_hex = tx.hex(" ") if tx else "N/A"
                rx_hex = rx.hex(" ") if rx else "N/A"

                # Parse Modbus exception response if available
                exception_msg = str(exc)
                if rx and len(rx) >= 2:
                    # Check if it's an exception response (function code | 0x80)
                    if rx[1] & 0x80:
                        exception_code = rx[2] if len(rx) > 2 else 0
                        exception_msgs = {
                            0x01: "Illegal function",
                            0x02: "Illegal data address",
                            0x03: "Illegal data value",
                            0x04: "Slave device failure",
                        }
                        exception_msg = f"{exception_msgs.get(exception_code, f'Exception code {exception_code}')} - slave responded with error"
                        _LOGGER.error(
                            "Modbus error reading from port %s - Request: slave_id=%s, start_addr=0x%04X, count=%d - Error: %s | TX: %s | RX: %s (device returned exception response)",
                            self.port, slave_id, start_addr, count, exception_msg, tx_hex, rx_hex
                        )
                    else:
                        _LOGGER.error(
                            "Modbus error reading from port %s - Request: slave_id=%s, start_addr=0x%04X, count=%d - Error: %s | TX: %s | RX: %s",
                            self.port, slave_id, start_addr, count, exc, tx_hex, rx_hex
                        )
                else:
                    _LOGGER.error(
                        "Modbus error reading from port %s - Request: slave_id=%s, start_addr=0x%04X, count=%d - Error: %s | TX: %s | RX: %s",
                        self.port, slave_id, start_addr, count, exc, tx_hex, rx_hex
                    )
                return None
            except Exception as exc:  # pragma: no cover
                tx, rx = self._get_last_tx_rx()
                tx_hex = tx.hex(" ") if tx else "N/A"
                rx_hex = rx.hex(" ") if rx else "N/A"
                _LOGGER.error(
                    "Unexpected error reading registers from port %s - Request: slave_id=%s, start_addr=0x%04X, count=%d - Error: %s | TX: %s | RX: %s",
                    self.port, slave_id, start_addr, count, exc, tx_hex, rx_hex
                )
                return None

    async def read_input_registers(
        self, slave_id: int, start_addr: int, count: int
    ) -> Optional[List[int]]:
        if not self.client:
            return None
        async with self._lock:
            loop = asyncio.get_event_loop()
            try:
                result = await loop.run_in_executor(
                    None,
                    self.client.execute,
                    slave_id,
                    cst.READ_INPUT_REGISTERS,
                    start_addr,
                    count,
                )
                return list(result)
            except Exception as exc:  # pragma: no cover
                tx, rx = self._get_last_tx_rx()
                tx_hex = tx.hex(" ") if tx else "N/A"
                rx_hex = rx.hex(" ") if rx else "N/A"
                _LOGGER.error(
                    "Error reading input registers from port %s - Request: slave_id=%s, start_addr=0x%04X, count=%d - Error: %s | TX: %s | RX: %s",
                    self.port, slave_id, start_addr, count, exc, tx_hex, rx_hex
                )
                return None

    async def write_registers(self, slave_id: int, start_addr: int, values: List[int]) -> bool:
        """Write multiple holding registers (function 0x10)."""
        if not self.client:
            _LOGGER.warning("Modbus client not connected")
            return False

        async with self._lock:
            loop = asyncio.get_event_loop()
            try:
                await loop.run_in_executor(
                    None,
                    self.client.execute,
                    slave_id,
                    cst.WRITE_MULTIPLE_REGISTERS,
                    start_addr,
                    len(values),
                    values,
                )
                return True
            except modbus.ModbusError as exc:
                tx, rx = self._get_last_tx_rx()
                tx_hex = tx.hex(" ") if tx else "N/A"
                rx_hex = rx.hex(" ") if rx else "N/A"
                _LOGGER.error(
                    "Modbus error writing to port %s - Request: slave_id=%s, start_addr=0x%04X, values=%s - Error: %s | TX: %s | RX: %s",
                    self.port, slave_id, start_addr, values, exc, tx_hex, rx_hex
                )
                return False
            except Exception as exc:  # pragma: no cover
                tx, rx = self._get_last_tx_rx()
                tx_hex = tx.hex(" ") if tx else "N/A"
                rx_hex = rx.hex(" ") if rx else "N/A"
                _LOGGER.error(
                    "Unexpected error writing registers to port %s - Request: slave_id=%s, start_addr=0x%04X, values=%s - Error: %s | TX: %s | RX: %s",
                    self.port, slave_id, start_addr, values, exc, tx_hex, rx_hex
                )
                return False

    async def write_register(
        self,
        slave_id: int,
        addr: int,
        value: int,
        timeout: Optional[float] = None,
        verify_response: bool = True
    ) -> bool:
        """Write a single holding register using WRITE_MULTIPLE_REGISTERS (function 0x10).

        Note: Some adapters don't support WRITE_SINGLE_REGISTER (0x06), so we use
        WRITE_MULTIPLE_REGISTERS (0x10) with a single value for compatibility.
        """
        if not self.client:
            _LOGGER.warning("Modbus client not connected")
            return False

        _LOGGER.debug("write_register called: slave_id=%d addr=0x%04X value=0x%04X",
                      slave_id, addr, value)

        async with self._lock:
            loop = asyncio.get_event_loop()
            try:
                if timeout is not None:
                    self.client.set_timeout(timeout)

                # Use WRITE_MULTIPLE_REGISTERS (0x10) with single value for better compatibility
                await loop.run_in_executor(
                    None,
                    self.client.execute,
                    slave_id,
                    cst.WRITE_MULTIPLE_REGISTERS,
                    addr,
                    1,  # quantity = 1 register
                    [value],
                )
                return True
            except (modbus.ModbusError, modbus.ModbusInvalidResponseError) as exc:
                tx, rx = self._get_last_tx_rx()
                tx_hex = tx.hex(" ") if tx else "N/A"
                rx_hex = rx.hex(" ") if rx else "N/A"
                if not verify_response:
                    _LOGGER.debug(
                        "Ignoring Modbus error for port %s (verify_response=False) - Request: slave_id=%s, addr=0x%04X, value=%s - Error: %s | TX: %s | RX: %s",
                        self.port, slave_id, addr, value, exc, tx_hex, rx_hex
                    )
                    return True
                _LOGGER.error(
                    "Modbus error writing to port %s - Request: slave_id=%s, addr=0x%04X, value=%s - Error: %s | TX: %s | RX: %s",
                    self.port, slave_id, addr, value, exc, tx_hex, rx_hex
                )
                return False
            except Exception as exc:
                tx, rx = self._get_last_tx_rx()
                tx_hex = tx.hex(" ") if tx else "N/A"
                rx_hex = rx.hex(" ") if rx else "N/A"
                _LOGGER.error(
                    "Unexpected error writing register to port %s - Request: slave_id=%s, addr=0x%04X, value=%s - Error: %s | TX: %s | RX: %s",
                    self.port, slave_id, addr, value, exc, tx_hex, rx_hex
                )
                return False
