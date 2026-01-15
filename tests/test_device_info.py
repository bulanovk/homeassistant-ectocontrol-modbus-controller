
import pytest
from unittest.mock import AsyncMock, MagicMock
from custom_components.ectocontrol_modbus_controller.boiler_gateway import BoilerGateway
from custom_components.ectocontrol_modbus_controller.const import REGISTER_UID

@pytest.mark.asyncio
async def test_gateway_read_device_info_success():
    """Test reading device info registers 0x0000-0x0003."""
    class MockProtocol:
        def __init__(self):
            self.read_registers = AsyncMock()

    protocol = MockProtocol()
    gateway = BoilerGateway(protocol, slave_id=1)

    # Mock registers:
    # 0x0000: Reserved (0x0000)
    # 0x0001: UID High (0x8A3F)
    # 0x0002: UID Low (0x21) + Address (0x01) -> 0x2101
    # 0x0003: Type (0x14) + Channels (0x02) -> 0x1402
    protocol.read_registers.return_value = [
        0x0000,
        0x8A3F,
        0x2101,
        0x1402
    ]

    success = await gateway.read_device_info()
    
    assert success is True
    # UID construction: 
    # High 16 bits: 0x8A3F
    # Low 8 bits: (0x2101 >> 8) & 0xFF = 0x21
    # Result: 0x8A3F21
    assert gateway.device_uid == 0x8A3F21
    assert gateway.get_device_uid_hex() == "8a3f21"
    
    # Device Type: (0x1402 >> 8) & 0xFF = 0x14
    assert gateway.device_type == 0x14
    assert gateway.get_device_type_name() == "OpenTherm Adapter v2"
    
    # Channels: 0x1402 & 0xFF = 0x02
    assert gateway.channel_count == 2

@pytest.mark.asyncio
async def test_gateway_read_device_info_failure():
    """Test behavior when read fails."""
    class MockProtocol:
        def __init__(self):
            self.read_registers = AsyncMock()

    protocol = MockProtocol()
    gateway = BoilerGateway(protocol, slave_id=1)
    
    protocol.read_registers.return_value = None
    
    success = await gateway.read_device_info()
    
    assert success is False
    assert gateway.device_uid is None
    assert gateway.get_device_uid_hex() is None

@pytest.mark.asyncio
async def test_gateway_device_type_mapping():
    """Test various device types."""
    gateway = BoilerGateway(MagicMock(), 1)
    
    # Test known type
    gateway.device_type = 0x22
    assert gateway.get_device_type_name() == "Temperature Sensor"
    
    # Test unknown type
    gateway.device_type = 0xFF
    assert gateway.get_device_type_name() == "Unknown (0xFF)"

def test_gateway_device_info_model_format():
    """Test that device_info model does not include redundant adapter_type."""
    class MockProtocol:
        port = "/dev/ttyUSB0"
    
    gateway = BoilerGateway(MockProtocol(), slave_id=1)
    gateway.device_uid = 0x8ABCDEF
    
    # Test OpenTherm Adapter v2 - should NOT include "(OpenTherm)" suffix
    gateway.device_type = 0x14  # OpenTherm Adapter v2
    gateway.cache = {0x0010: 0x0000}  # Adapter type: OpenTherm (0x00), bit 3: connected
    device_info = gateway.get_device_info()
    
    # Model should be "OpenTherm Adapter v2", NOT "OpenTherm Adapter v2 (OpenTherm)"
    assert device_info["model"] == "OpenTherm Adapter v2"
    assert device_info["manufacturer"] == "Ectostroy"
    assert device_info["identifiers"] == {("ectocontrol_modbus_controller", "uid_8abcdef")}
    assert device_info["name"] == "Ectocontrol OpenTherm Adapter v2"
    
    # Test eBus Adapter - should NOT include "(eBus)" suffix
    gateway.device_type = 0x15  # eBus Adapter
    gateway.cache = {0x0010: 0x0001}  # Adapter type: eBus (0x01)
    device_info = gateway.get_device_info()
    
    assert device_info["model"] == "eBus Adapter"
    assert device_info["name"] == "Ectocontrol eBus Adapter"
    
    # Test Navien Adapter - should NOT include "(Navien)" suffix
    gateway.device_type = 0x16  # Navien Adapter
    gateway.cache = {0x0010: 0x0002}  # Adapter type: Navien (0x02)
    device_info = gateway.get_device_info()
    
    assert device_info["model"] == "Navien Adapter"
    assert device_info["name"] == "Ectocontrol Navien Adapter"
