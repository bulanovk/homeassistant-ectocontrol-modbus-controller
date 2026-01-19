"""Simple test to verify PTY manager works without pytest fixtures."""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from pty_manager import PTYManager, check_socat_available


async def main():
    """Test PTY manager."""
    print("Checking socat...")
    if not await check_socat_available():
        print("ERROR: socat not installed")
        return

    print("Creating PTY pair...")
    manager = PTYManager()

    try:
        master, slave = await manager.create_pair()
        print(f"SUCCESS: Master={master}, Slave={slave}")

        # Test connection
        from custom_components.ectocontrol_modbus_controller.modbus_protocol import ModbusProtocol

        protocol = ModbusProtocol(port=master, baudrate=19200, timeout=2.0)
        result = await protocol.connect()
        print(f"Connect result: {result}")

        if result:
            regs = await protocol.read_registers(slave_id=1, start_addr=0x0000, count=4)
            print(f"Read registers: {regs}")

        await protocol.disconnect()

    finally:
        await manager.close()
        print("Cleaned up")


if __name__ == "__main__":
    asyncio.run(main())
