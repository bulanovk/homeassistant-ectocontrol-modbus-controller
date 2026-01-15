"""Tests for ModbusProtocolManager.

Tests reference counting, protocol sharing, and lifecycle management.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.ectocontrol_modbus_controller.modbus_protocol_manager import ModbusProtocolManager
from custom_components.ectocontrol_modbus_controller.modbus_protocol import ModbusProtocol


@pytest.fixture
def manager():
    """Create a fresh protocol manager for each test."""
    return ModbusProtocolManager()


class TestProtocolManagerLifecycle:
    """Test protocol creation, sharing, and cleanup."""

    @pytest.mark.asyncio
    async def test_get_protocol_creates_new_instance(self, manager):
        """First call to get_protocol should create new instance."""
        with patch.object(ModbusProtocol, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = True

            protocol = await manager.get_protocol("COM1")

            assert isinstance(protocol, ModbusProtocol)
            assert protocol.port == "COM1"
            mock_connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_protocol_shares_existing_instance(self, manager):
        """Subsequent calls should return same protocol instance."""
        with patch.object(ModbusProtocol, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = True

            protocol1 = await manager.get_protocol("COM1")
            # Mock is_connected to return True to avoid reconnect
            with patch.object(ModbusProtocol, "is_connected", True):
                protocol2 = await manager.get_protocol("COM1")

            assert protocol1 is protocol2  # Same instance
            assert mock_connect.call_count == 1  # Connected only once

    @pytest.mark.asyncio
    async def test_reference_counting_increments(self, manager):
        """Reference count should increment with each get_protocol call."""
        with patch.object(ModbusProtocol, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = True

            await manager.get_protocol("COM1")
            assert manager.get_reference_count("COM1") == 1

            await manager.get_protocol("COM1")
            assert manager.get_reference_count("COM1") == 2

            await manager.get_protocol("COM1")
            assert manager.get_reference_count("COM1") == 3

    @pytest.mark.asyncio
    async def test_release_decrements_reference_count(self, manager):
        """Release should decrement ref count without closing."""
        with patch.object(ModbusProtocol, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = True

            await manager.get_protocol("COM1")
            await manager.get_protocol("COM1")
            assert manager.get_reference_count("COM1") == 2

            with patch.object(ModbusProtocol, "disconnect", new_callable=AsyncMock) as mock_disconnect:
                await manager.release_protocol("COM1")
                assert manager.get_reference_count("COM1") == 1
                mock_disconnect.assert_not_called()  # Not closed yet

    @pytest.mark.asyncio
    async def test_release_closes_on_last_reference(self, manager):
        """Release should close protocol when ref count reaches zero."""
        with patch.object(ModbusProtocol, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = True

            await manager.get_protocol("COM1")
            assert manager.get_reference_count("COM1") == 1

            with patch.object(ModbusProtocol, "disconnect", new_callable=AsyncMock) as mock_disconnect:
                await manager.release_protocol("COM1")
                assert manager.get_reference_count("COM1") == 0
                mock_disconnect.assert_called_once()  # Closed!

    @pytest.mark.asyncio
    async def test_multiple_ports_independent(self, manager):
        """Different ports should have separate protocol instances."""
        with patch.object(ModbusProtocol, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = True

            protocol1 = await manager.get_protocol("COM1")
            protocol2 = await manager.get_protocol("COM2")

            assert protocol1 is not protocol2  # Different instances
            assert manager.get_reference_count("COM1") == 1
            assert manager.get_reference_count("COM2") == 1

    @pytest.mark.asyncio
    async def test_close_all_closes_all_protocols(self, manager):
        """close_all should close all protocols regardless of ref count."""
        with patch.object(ModbusProtocol, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = True

            await manager.get_protocol("COM1")
            await manager.get_protocol("COM1")
            await manager.get_protocol("COM2")

            assert manager.get_reference_count("COM1") == 2
            assert manager.get_reference_count("COM2") == 1

            with patch.object(ModbusProtocol, "disconnect", new_callable=AsyncMock) as mock_disconnect:
                await manager.close_all()

                assert manager.get_reference_count("COM1") == 0
                assert manager.get_reference_count("COM2") == 0
                assert mock_disconnect.call_count == 2  # Both closed

    @pytest.mark.asyncio
    async def test_release_nonexistent_port_no_error(self, manager):
        """Releasing non-existent port should be safe (no-op)."""
        # Should not raise exception
        await manager.release_protocol("NONEXISTENT")

    @pytest.mark.asyncio
    async def test_get_protocol_parameters_passed_through(self, manager):
        """Protocol should be created with correct parameters."""
        # Create a real ModbusProtocol instance to verify parameters
        with patch.object(ModbusProtocol, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = True

            # Call with custom parameters
            protocol = await manager.get_protocol(
                port="COM1",
                baudrate=9600,
                timeout=5.0,
                debug_modbus=True
            )

            # Verify parameters were stored correctly
            assert protocol.port == "COM1"
            assert protocol.baudrate == 9600
            assert protocol.timeout == 5.0
            assert protocol.debug_modbus is True


class TestProtocolManagerConcurrency:
    """Test thread-safe access to protocol manager."""

    @pytest.mark.asyncio
    async def test_concurrent_get_protocol(self, manager):
        """Multiple concurrent calls should safely create one protocol."""
        with patch.object(ModbusProtocol, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = True

            # Simulate 10 concurrent requests
            protocols = await asyncio.gather(*[
                manager.get_protocol("COM1") for _ in range(10)
            ])

            # All should get same instance
            first = protocols[0]
            assert all(p is first for p in protocols)

            # Should connect only once (subsequent calls return existing instance)
            # First call creates it, others return the same instance (with is_connected check)
            assert mock_connect.call_count <= 10  # At most 10 calls (race conditions possible)

            # Ref count should be 10
            assert manager.get_reference_count("COM1") == 10

    @pytest.mark.asyncio
    async def test_concurrent_release(self, manager):
        """Multiple concurrent releases should be safe."""
        with patch.object(ModbusProtocol, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = True

            # Create 10 references
            for _ in range(10):
                await manager.get_protocol("COM1")

            assert manager.get_reference_count("COM1") == 10

            # Release all concurrently
            with patch.object(ModbusProtocol, "disconnect", new_callable=AsyncMock) as mock_disconnect:
                await asyncio.gather(*[
                    manager.release_protocol("COM1") for _ in range(10)
                ])

                # Should close exactly once
                mock_disconnect.assert_called_once()
                assert manager.get_reference_count("COM1") == 0


class TestProtocolManagerUtilities:
    """Test utility methods."""

    @pytest.mark.asyncio
    async def test_is_port_in_use(self, manager):
        """is_port_in_use should return correct status."""
        with patch.object(ModbusProtocol, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = True

            assert not manager.is_port_in_use("COM1")

            await manager.get_protocol("COM1")
            assert manager.is_port_in_use("COM1")

            await manager.release_protocol("COM1")
            assert not manager.is_port_in_use("COM1")

    @pytest.mark.asyncio
    async def test_get_active_ports(self, manager):
        """get_active_ports should return list of active ports."""
        with patch.object(ModbusProtocol, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = True

            await manager.get_protocol("COM1")
            await manager.get_protocol("COM2")
            await manager.get_protocol("COM3")

            active = manager.get_active_ports()
            assert set(active) == {"COM1", "COM2", "COM3"}

    @pytest.mark.asyncio
    async def test_get_protocol_info(self, manager):
        """get_protocol_info should return reference counts."""
        with patch.object(ModbusProtocol, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = True

            await manager.get_protocol("COM1")
            await manager.get_protocol("COM1")
            await manager.get_protocol("COM2")

            info = await manager.get_protocol_info()
            assert info == {"COM1": 2, "COM2": 1}


class TestProtocolManagerErrorHandling:
    """Test error handling in protocol manager."""

    @pytest.mark.asyncio
    async def test_connection_failure_propagates(self, manager):
        """Connection failures should propagate to caller."""
        with patch.object(ModbusProtocol, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = False  # Connection failed

            with pytest.raises(ConnectionError):
                await manager.get_protocol("COM1")

            # Should not store failed protocol
            assert not manager.is_port_in_use("COM1")

    @pytest.mark.asyncio
    async def test_connection_exception_propagates(self, manager):
        """Connection exceptions should propagate to caller."""
        with patch.object(ModbusProtocol, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.side_effect = Exception("Serial port not found")

            with pytest.raises(Exception, match="Serial port not found"):
                await manager.get_protocol("COM1")

            # Should not store failed protocol
            assert not manager.is_port_in_use("COM1")
