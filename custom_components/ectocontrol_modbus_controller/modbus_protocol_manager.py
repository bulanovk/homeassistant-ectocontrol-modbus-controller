"""ModbusProtocolManager: Shared ModbusProtocol instances per serial port.

This manager implements a singleton pattern where each physical serial port
has exactly one ModbusProtocol instance, shared across multiple config entries
(coordinators) via reference counting.

Key benefits:
- Multiple slaves on same port share one serial connection
- Reference counting ensures proper lifecycle management
- Thread-safe protocol access and creation
"""
from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional, Tuple

from .modbus_protocol import ModbusProtocol

_LOGGER = logging.getLogger(__name__)


class ModbusProtocolManager:
    """Manages shared ModbusProtocol instances with reference counting.

    Each serial port has exactly one ModbusProtocol instance, shared by all
    config entries (coordinators) that use that port. Reference counting
    ensures the protocol is closed when the last user releases it.
    """

    def __init__(self):
        """Initialize the protocol manager."""
        self._protocols: Dict[str, Tuple[ModbusProtocol, int]] = {}
        """Map of port -> (protocol_instance, reference_count)"""

        self._lock = asyncio.Lock()
        """Lock for thread-safe access to _protocols dict"""

        _LOGGER.debug("ModbusProtocolManager initialized")

    async def get_protocol(
        self,
        port: str,
        baudrate: int = 19200,
        timeout: float = 2.0,
        debug_modbus: bool = False,
    ) -> ModbusProtocol:
        """Get or create a shared ModbusProtocol instance for the given port.

        This method is thread-safe and can be called concurrently from multiple
        config entries. The first call creates the protocol, subsequent calls
        increment the reference count.

        Args:
            port: Serial port device path (e.g., "COM1", "/dev/ttyUSB0")
            baudrate: Baud rate (default 19200)
            timeout: Read timeout in seconds (default 2.0)
            debug_modbus: Enable raw hex logging (default False)

        Returns:
            Shared ModbusProtocol instance (already connected)

        Raises:
            Exception: If connection fails
        """
        async with self._lock:
            # Check if protocol already exists for this port
            if port in self._protocols:
                protocol, ref_count = self._protocols[port]
                self._protocols[port] = (protocol, ref_count + 1)

                _LOGGER.debug(
                    "Protocol for %s already exists (ref_count: %d -> %d)",
                    port,
                    ref_count,
                    ref_count + 1,
                )

                # Verify protocol is still connected
                if not protocol.is_connected:
                    _LOGGER.warning(
                        "Protocol for %s was disconnected, reconnecting",
                        port
                    )
                    connected = await protocol.connect()
                    if not connected:
                        _LOGGER.error("Failed to reconnect protocol for %s", port)
                        raise ConnectionError(f"Failed to reconnect to {port}")

                return protocol

            # Create new protocol instance
            _LOGGER.info(
                "Creating new ModbusProtocol for %s (baudrate=%d, timeout=%s, debug=%s)",
                port,
                baudrate,
                timeout,
                debug_modbus,
            )

            protocol = ModbusProtocol(
                port=port,
                baudrate=baudrate,
                timeout=timeout,
                debug_modbus=debug_modbus,
            )

            # Connect to the serial port
            connected = await protocol.connect()
            if not connected:
                _LOGGER.error("Failed to connect ModbusProtocol for %s", port)
                raise ConnectionError(f"Failed to connect to {port}")

            # Store with reference count = 1
            self._protocols[port] = (protocol, 1)

            _LOGGER.info(
                "ModbusProtocol for %s created and connected (ref_count=1)",
                port
            )

            return protocol

    async def release_protocol(self, port: str) -> None:
        """Release a reference to the protocol for the given port.

        Decrements the reference count. If the count reaches zero, the protocol
        is disconnected and removed from the manager.

        This method is idempotent - calling it multiple times for the same port
        is safe (extra calls are ignored).

        Args:
            port: Serial port device path
        """
        async with self._lock:
            if port not in self._protocols:
                _LOGGER.warning(
                    "Attempted to release protocol for %s, but not found in manager",
                    port
                )
                return

            protocol, ref_count = self._protocols[port]

            _LOGGER.debug(
                "Releasing protocol for %s (ref_count: %d -> %d)",
                port,
                ref_count,
                ref_count - 1,
            )

            if ref_count > 1:
                # Still other users, just decrement ref count
                self._protocols[port] = (protocol, ref_count - 1)
            else:
                # Last user, close and remove protocol
                _LOGGER.info(
                    "Last reference for %s released, closing protocol",
                    port
                )
                await protocol.disconnect()
                del self._protocols[port]

                _LOGGER.info(
                    "ModbusProtocol for %s closed and removed from manager",
                    port
                )

    async def close_all(self) -> None:
        """Close all protocol instances.

        Called during Home Assistant shutdown to ensure all serial ports are
        properly closed. This is a cleanup method and should only be called
        during shutdown or testing.
        """
        async with self._lock:
            if not self._protocols:
                _LOGGER.debug("No protocols to close")
                return

            _LOGGER.info(
                "Closing %d protocol(s) during shutdown",
                len(self._protocols)
            )

            ports_to_close = list(self._protocols.keys())

            for port in ports_to_close:
                protocol, ref_count = self._protocols[port]

                _LOGGER.debug(
                    "Closing protocol for %s (ref_count was %d)",
                    port,
                    ref_count
                )

                await protocol.disconnect()

            # Clear all entries
            self._protocols.clear()

            _LOGGER.info("All protocols closed")

    def is_port_in_use(self, port: str) -> bool:
        """Check if a port has active references.

        This is a synchronous method (does not acquire lock) and provides
        a quick check for UI validation.

        Args:
            port: Serial port device path

        Returns:
            True if port has active references, False otherwise
        """
        return port in self._protocols

    def get_reference_count(self, port: str) -> int:
        """Get the current reference count for a port.

        This is a synchronous method (does not acquire lock) and provides
        a quick check for debugging/logging.

        Args:
            port: Serial port device path

        Returns:
            Reference count (0 if port not in use)
        """
        if port not in self._protocols:
            return 0
        _, ref_count = self._protocols[port]
        return ref_count

    def get_active_ports(self) -> list[str]:
        """Get list of ports with active references.

        This is a synchronous method (does not acquire lock) and provides
        a quick check for debugging/logging.

        Returns:
            List of port names with ref_count > 0
        """
        return list(self._protocols.keys())

    async def get_protocol_info(self) -> Dict[str, int]:
        """Get information about all active protocols.

        Returns a dict mapping port names to reference counts. This is
        primarily useful for diagnostics and debugging.

        Returns:
            Dict of {port: reference_count}
        """
        async with self._lock:
            return {
                port: ref_count
                for port, (_, ref_count) in self._protocols.items()
            }
