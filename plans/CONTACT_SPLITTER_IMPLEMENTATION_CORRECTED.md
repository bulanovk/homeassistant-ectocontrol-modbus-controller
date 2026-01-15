# Implementation Plan: 10-Channel Contact Sensor Splitter (CORRECTED)

**Device Type:** 0x59 (Contact Sensor Splitter 10ch)
**Date:** 2025-01-15
**Status:** Planning Phase - CORRECTED with Russian Protocol Documentation

## Overview

The 10-Channel Contact Sensor Splitter is a Modbus RTU device that monitors 10 digital contact inputs (dry contacts) and exposes their states via Modbus input registers using a **bitfield structure at addresses 0x0010-0x0011** (NOT 0x0012!). This implementation will add support for this device type to the existing Ectocontrol Modbus Controller integration.

## Device Specifications

### Hardware Details
- **Device Type Code:** 0x59 (from REGISTER_TYPE_CHANNELS MSB)
- **Channel Count:** Read from REGISTER_TYPE_CHANNELS LSB (range: 1-10)
- **Communication:** Modbus RTU over RS-485
- **Baud Rate:** 19200
- **Register Map:** Uses generic device info registers + discrete sensor bitfield registers

### Register Map for Contact Splitter

#### Generic Device Information (0x0000-0x0003)
All Ectocontrol devices share these registers:

| Address | Name | Type | Access | Description |
|---------|------|------|--------|-------------|
| 0x0000 | Reserved | u16 | RO | Reserved for future use |
| 0x0001 | UID | u24 | RO | Unique device identifier (0x800000-0xFFFFFF) |
| 0x0002 | Address | u8/u8 | RO | Reserved (MSB), Device Modbus address (LSB, 1-32) |
| 0x0003 | Type + Channels | u8/u8 | RO | Device type=0x59 (MSB), Channel count (LSB, range: 1-10) |

#### Contact State Registers (Bitfield at 0x0010-0x0011)

**CRITICAL:** Contact states are stored in **bitfield registers at 0x0010-0x0011**, NOT individual registers!

**Source:** Russian Protocol Documentation, Section 3.2 "ДИСКРЕТНЫЕ ДАТЧИКИ" (Discrete Sensors)

| Address | Name | Type | Access | Description |
|---------|------|------|--------|-------------|
| 0x0010 | Channels 1-8 Bitfield | u16 (bitfield) | RO | Bits 0-7 represent channels 1-8 contact states |
| 0x0011 | Channels 9-10 Bitfield | u16 (bitfield) | RO | Bits 0-2 represent channels 9-10 contact states (only 3 bits used) |

**Bitfield Structure:**

**Register 0x0010 (Channels 1-8):**
```
+--------+--------+--------+--------+--------+--------+--------+--------+
|  15-8  |   7    |   6    |   5    |   4    |   3    |   2    |   1    |
+--------+--------+--------+--------+--------+--------+--------+--------+
|  Resvd | CH8    | CH7    | CH6    | CH5    | CH4    | CH3    | CH2    |
+--------+--------+--------+--------+--------+--------+--------+--------+
+--------+--------+
|   0    |
+--------+
| CH1    |
+--------+
```

**Register 0x0011 (Channels 9-10, only bits 0-2 used):**
```
+--------+--------+--------+--------+--------+--------+--------+--------+
|  15-3  |   2    |   1    |   0    |
+--------+--------+--------+--------+
|  Resvd | CH10   | CH9    | (unused) |
+--------+--------+--------+
```

**Bit Values:**
- Bit n = 0 → Contact OPEN (circuit open)
- Bit n = 1 → Contact CLOSED (circuit complete)

**Examples:**
- `0x0010=0x0000, 0x0011=0x0000` = All channels OPEN
- `0x0010=0x0001, 0x0011=0x0000` = Only channel 1 CLOSED (bit 0 of reg 0x0010)
- `0x0010=0x0005, 0x0011=0x0000` = Channels 1 and 3 CLOSED (binary: 0000000000000101)
- `0x0010=0x00FF, 0x0011=0x0000` = Channels 1-8 CLOSED, channels 9-10 OPEN
- `0x0010=0x00FF, 0x0011=0x0007` = All 10 channels CLOSED (0x00FF = bits 0-7 set, 0x0007 = bits 0-2 set)

**Important Notes:**
- Register 0x0010 holds channels 1-8 (bits 0-7)
- Register 0x0011 holds channels 9-10 (bits 0-2 only, bits 3-15 reserved)
- Channel count is dynamic (1-10), read from register 0x0003 LSB
- Only read registers up to channel_count (e.g., for 4-channel device, only read 0x0010)

## Architecture Design

### Current Architecture (Boiler Only)
```
ConfigEntry → BoilerGateway → Coordinator → Entities (sensor, switch, etc.)
                  ↓
            ModbusProtocol
```

### Proposed Architecture (Multi-Device Support)
```
ConfigEntry → DeviceRouter → (Device Type Detection)
                              ├→ BoilerGateway → BoilerCoordinator → Boiler Entities
                              └→ ContactGateway → ContactCoordinator → Contact Entities
                                          ↓
                                  ModbusProtocol (shared)
```

### Key Design Decisions

1. **Device Type Detection:** Use `REGISTER_TYPE_CHANNELS` (0x0003) to detect device type during setup
2. **Gateway Abstraction:** Create separate gateway classes for each device type
3. **Coordinator Separation:** Each device type has its own coordinator with appropriate polling logic
4. **Entity Platform Routing:** Route entities to appropriate platform based on device type
5. **Shared ModbusProtocol:** Use existing ModbusProtocolManager for shared serial connections

## Implementation Tasks

### Phase 1: Core Infrastructure

#### Task 1.1: Create ContactSensorGateway Class
**File:** `custom_components/ectocontrol_modbus_controller/contact_gateway.py`

**Responsibilities:**
- Read device info (UID, device type, channel count)
- Cache contact state bitfield registers (0x0010-0x0011)
- Provide getter methods for each channel state using bit extraction
- Handle invalid states and errors

**Key Methods:**
```python
class ContactSensorGateway:
    def __init__(self, protocol, slave_id: int):
        self.protocol = protocol
        self.slave_id = slave_id
        self.cache: Dict[int, int] = {}
        self.device_uid: Optional[int] = None
        self.device_type: Optional[int] = None
        self.channel_count: Optional[int] = None  # Read from device, not hardcoded!

    async def read_device_info(self) -> bool:
        """Read generic device info from registers 0x0000-0x0003.

        Populates:
        - device_uid: 24-bit unique identifier
        - device_type: Device type code (should be 0x59)
        - channel_count: Number of channels (1-10, read from LSB of 0x0003)
        """

    def get_channel_count(self) -> int:
        """Return the number of channels this device has.

        Dynamically read from device info, not hardcoded.
        Returns channel_count if available, otherwise 0.
        """

    def get_channel_bitfields(self) -> tuple[Optional[int], Optional[int]]:
        """Get the raw bitfield values from registers 0x0010 and 0x0011.

        Returns:
            Tuple of (reg_0x0010_value, reg_0x0011_value)
            None for any register not available or read failed
        """
        # Read from cache (populated by coordinator)
        reg_0x0010 = self.cache.get(0x0010)
        reg_0x0011 = self.cache.get(0x0011)
        return reg_0x0010, reg_0x0011

    def get_channel_state(self, channel: int) -> Optional[bool]:
        """Get contact state for channel (1 to channel_count) using bitfield.

        Args:
            channel: Channel number (1-indexed, must be <= channel_count)

        Returns:
            True if contact is CLOSED (bit = 1)
            False if contact is OPEN (bit = 0)
            None if channel invalid, bitfield not available, or read failed

        Raises:
            ValueError: If channel number is out of range (must be 1-10)

        Bit extraction logic:
            Channel 1-8: Extract from register 0x0010
                Channel n = bit (n-1) of register 0x0010
            Channel 9-10: Extract from register 0x0011
                Channel 9 = bit 0 of register 0x0011
                Channel 10 = bit 1 of register 0x0011
        """
        # Validate channel number
        if channel < 1 or channel > 10:
            raise ValueError(f"Channel must be 1-10, got {channel}")

        # Check against device channel count
        if self.channel_count is not None and channel > self.channel_count:
            return None

        # Get bitfields from cache
        reg_0x0010, reg_0x0011 = self.get_channel_bitfields()
        
        if channel <= 8:
            # Channels 1-8 are in register 0x0010
            if reg_0x0010 is None:
                return None
            bit_position = channel - 1
            is_closed = bool((reg_0x0010 >> bit_position) & 0x01)
            return is_closed
        else:
            # Channels 9-10 are in register 0x0011
            if reg_0x0011 is None:
                return None
            bit_position = channel - 9  # Channel 9 = bit 0, Channel 10 = bit 1
            is_closed = bool((reg_0x0011 >> bit_position) & 0x01)
            return is_closed

    def get_device_info(self) -> DeviceInfo:
        """Return Home Assistant DeviceInfo structure"""
```

**Bit Extraction Example:**
```python
# Example 1: 4-channel device
# Register 0x0010 = 0x0005 (binary: 0000000000000101)
# Register 0x0011 = not read (channel_count=4)

reg_0x0010 = 0x0005

# Channel 1 (bit 0 of reg 0x0010):
ch1_state = (reg_0x0010 >> 0) & 0x01  # = 1 → CLOSED

# Channel 2 (bit 1 of reg 0x0010):
ch2_state = (reg_0x0010 >> 1) & 0x01  # = 0 → OPEN

# Channel 3 (bit 2 of reg 0x0010):
ch3_state = (reg_0x0010 >> 2) & 0x01  # = 1 → CLOSED

# Channel 4 (bit 3 of reg 0x0010):
ch4_state = (reg_0x0010 >> 3) & 0x01  # = 0 → OPEN

# Example 2: 10-channel device
# Register 0x0010 = 0x00FF (all channels 1-8 CLOSED)
# Register 0x0011 = 0x0007 (channels 9-10 CLOSED)

reg_0x0010 = 0x00FF
reg_0x0011 = 0x0007

# Channel 8 (bit 7 of reg 0x0010):
ch8_state = (reg_0x0010 >> 7) & 0x01  # = 1 → CLOSED

# Channel 9 (bit 0 of reg 0x0011):
ch9_state = (reg_0x0011 >> 0) & 0x01  # = 1 → CLOSED

# Channel 10 (bit 1 of reg 0x0011):
ch10_state = (reg_0x0011 >> 1) & 0x01  # = 1 → CLOSED
```

**Validation:**
- Channel count must be in range 1-10 (read from device, not hardcoded!)
- Device type must be 0x59
- UID must be in valid range (0x800000-0xFFFFFF)
- Channel number must be 1-10 and <= channel_count when calling get_channel_state()
- Bits 8-15 of register 0x0010 are reserved and should be ignored
- Bits 3-15 of register 0x0011 are reserved and should be ignored

#### Task 1.2: Create ContactSensorCoordinator Class
**File:** `custom_components/ectocontrol_modbus_controller/contact_coordinator.py`

**Responsibilities:**
- Poll contact state bitfield registers every N seconds (default: 5 seconds)
- Update gateway cache with latest bitfield values
- Handle connection errors and retries
- Track update success for entity availability

**Key Methods:**
```python
class ContactSensorDataUpdateCoordinator(DataUpdateCoordinator):
    async def _async_update_data(self) -> Dict[int, int]:
        """Read contact state bitfields from registers 0x0010-0x0011.

        For the Contact Sensor Splitter, we need to read 1 or 2 registers:
        - Register 0x0010: Always read (channels 1-8)
        - Register 0x0011: Read only if channel_count > 8 (channels 9-10)

        Returns:
            Dictionary with entries: {0x0010: value, 0x0011: value} (if applicable)
        """
        # Always read register 0x0010 (channels 1-8)
        channel_count = self.gateway.channel_count or 10
        
        # Determine how many registers to read
        if channel_count <= 8:
            # Only need register 0x0010
            regs = await self.gateway.protocol.read_registers(
                self.gateway.slave_id,
                0x0010,
                1
            )
            if regs is None or len(regs) == 0:
                raise UpdateFailed("Failed to read contact states")
            cache_data = {0x0010: regs[0]}
        else:
            # Need both registers 0x0010 and 0x0011
            regs = await self.gateway.protocol.read_registers(
                self.gateway.slave_id,
                0x0010,
                2
            )
            if regs is None or len(regs) < 2:
                raise UpdateFailed("Failed to read contact states")
            cache_data = {0x0010: regs[0], 0x0011: regs[1]}
        
        return cache_data

    def is_channel_available(self, channel: int) -> bool:
        """Check if channel has valid data (bitfield available and channel in range)"""
        if self.gateway.channel_count is None:
            return False
        if channel < 1 or channel > self.gateway.channel_count:
            return False
        
        # Check if appropriate register is in cache
        if channel <= 8:
            return 0x0010 in self.gateway.cache
        else:
            return 0x0011 in self.gateway.cache
```

**Polling Strategy:**
- Default interval: 5 seconds (contacts change faster than boiler temps)
- **Dynamic register count**: Read 1 or 2 registers based on channel_count
- **Efficient**: One or two registers contain ALL channel states in bitfields
- Retry logic: Use existing retry mechanism from coordinator

**Comparison with Boiler:**
- **Boiler**: Reads 23 registers (0x0010-0x0026) for various sensors
- **Contact Splitter (1-8 channels)**: Reads 1 register (0x0010) for ALL channel states
- **Contact Splitter (9-10 channels)**: Reads 2 registers (0x0010-0x0011) for ALL channel states
- **Efficiency**: Contact splitter polling is ~11-23x more efficient!

#### Task 1.3: Create Device Router
**File:** `custom_components/ectocontrol_modbus_controller/device_router.py`

**Responsibilities:**
- Detect device type during setup
- Create appropriate gateway instance
- Route to correct coordinator
- Provide unified interface for entity setup

**Key Methods:**
```python
async def create_device_gateway(protocol, slave_id: int) -> Union[BoilerGateway, ContactSensorGateway]:
    """Detect device type and create appropriate gateway"""
    # Read device type from register 0x0003
    regs = await protocol.read_registers(slave_id, 0x0000, 4)
    if regs is None:
        raise ValueError("Failed to read device info")
    
    # Extract device type (MSB of reg[3])
    device_type = (regs[3] >> 8) & 0xFF
    
    # Return appropriate gateway
    if device_type == 0x59:
        return ContactSensorGateway(protocol, slave_id)
    elif device_type in [0x14, 0x15, 0x16]:
        return BoilerGateway(protocol, slave_id)
    else:
        raise ValueError(f"Unsupported device type: 0x{device_type:02X}")
```

### Phase 2: Entity Implementation

#### Task 2.1: Create Binary Sensor Entities for Contacts
**File:** `custom_components/ectocontrol_modbus_controller/contact_binary_sensor.py`

**Entity Design:**
- **Platform:** `binary_sensor`
- **Device Class:** `BinarySensorDeviceClass.OPENING` or `BinarySensorDeviceClass.DOOR`
- **Entity Class:** `ContactChannelBinarySensor`
- **Count:** Dynamic! Create entities for channel_count channels (1-10, not fixed to 10)

**Entity Properties:**
```python
class ContactChannelBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.OPENING
    
    def __init__(self, coordinator, channel: int):
        super().__init__(coordinator)
        self._channel = channel
        self._attr_name = f"Channel {channel}"
    
    @property
    def unique_id(self) -> str:
        gateway = self.coordinator.gateway
        return f"{DOMAIN}_uid_{gateway.get_device_uid_hex()}_channel_{channel}"
    
    @property
    def device_info(self) -> DeviceInfo:
        return self.coordinator.gateway.get_device_info()
    
    @property
    def is_on(self) -> bool | None:
        return self.coordinator.gateway.get_channel_state(self._channel)
```

**Entity Creation Logic:**
```python
async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    gateway = data["gateway"]
    
    # DYNAMIC: Create entities based on actual channel count from device
    entities = []
    for channel in range(1, gateway.get_channel_count() + 1):
        entities.append(ContactChannelBinarySensor(coordinator, channel))
    
    async_add_entities(entities)
```

**Naming Convention:**
- Entity Name: "Channel 1", "Channel 2", etc. (dynamic based on channel_count)
- Unique ID: `ectocontrol_modbus_controller_uid_8abcdef_channel_{n}`
- Device Association: All channels belong to same device

### Phase 3: Integration Setup

#### Task 3.1: Update __init__.py for Multi-Device Support
**File:** `custom_components/ectocontrol_modbus_controller/__init__.py`

**Changes:**
```python
async def async_setup_entry(hass: HomeAssistant, entry) -> bool:
    # Existing code for protocol manager...
    
    # NEW: Device type detection and routing
    gateway = await create_device_gateway(protocol, slave)
    
    # Route to appropriate coordinator based on device type
    if isinstance(gateway, BoilerGateway):
        coordinator = BoilerDataUpdateCoordinator(...)
    elif isinstance(gateway, ContactSensorGateway):
        coordinator = ContactSensorDataUpdateCoordinator(...)
    
    # Forward to platforms based on device type
    if isinstance(gateway, BoilerGateway):
        platforms = ["sensor", "switch", "number", "binary_sensor", "climate", "button"]
    elif isinstance(gateway, ContactSensorGateway):
        platforms = ["binary_sensor"]  # Only binary sensors for contact splitter
```

#### Task 3.2: Update Config Flow for Device Type Display
**File:** `custom_components/ectocontrol_modbus_controller/config_flow.py`

**Changes:**
- Display detected device type in connection test step
- Show device type in config entry title
- Add device-specific validation (e.g., channel count for contact splitter)

**UI Enhancement:**
```
Connection Test Result:
✓ Device UID: 8ABCDEF
✓ Device Type: Contact Sensor Splitter (0x59)
✓ Channels: 4 (dynamically read from device)
✓ Communication: OK
```

**Important:** The config flow should display the actual channel count read from the device, not assume 10 channels.

### Phase 4: Testing

#### Task 4.1: Create Unit Tests
**File:** `tests/test_contact_gateway.py`

**Test Cases:**
- Test device info reading (UID, type, channels)
- Test channel state getter methods with bitfield extraction
- Test dynamic channel count handling (1, 4, 8, 10 channels)
- Test bit extraction from register 0x0010 (channels 1-8)
- Test bit extraction from register 0x0011 (channels 9-10)
- Test invalid channel numbers (out of range, > channel_count)
- Test invalid state values
- Test device info generation
- Test that channel_count is correctly read from register 0x0003 LSB

**File:** `tests/test_contact_coordinator.py`

**Test Cases:**
- Test polling logic for dynamic channel counts (1, 4, 8, 10 channels)
- Test dynamic register count (1 register for ≤8 channels, 2 registers for >8 channels)
- Test cache updates for both registers
- Test error handling and retries
- Test availability tracking

**File:** `tests/test_contact_entities.py`

**Test Cases:**
- Test entity state (on/off)
- Test entity unique IDs
- Test device info association
- Test unavailable states
- Test dynamic entity creation based on channel_count
- Test that entities are only created for valid channels (1 to channel_count)

#### Task 4.2: Create Integration Tests
**File:** `tests/test_contact_splitter_integration.py`

**Test Scenarios:**
- Full setup flow with mocked Modbus device
- Device type detection and routing
- Dynamic entity registration based on channel_count
- State updates after polling
- Error recovery
- Test with different channel counts (1, 4, 8, 10 channels)

### Phase 5: Documentation

#### Task 5.1: Update English MODBUS_PROTOCOL.md from Russian Version
**File:** `docs/MODBUS_PROTOCOL.md`

**Action:** Add comprehensive section for Contact Sensor Splitter based on Russian documentation

**Add Section:**
```markdown
### 3.X Contact Sensor Splitter (Device Type 0x59)

The Contact Sensor Splitter monitors up to 10 dry contact inputs and exposes their states via bitfield registers.

#### Device Type Code
- **0x59**: 10-channel Contact Sensor Splitter (channel count read from 0x0003 LSB, range 1-10)

#### Register Structure

**Generic Device Information (0x0000-0x0003):**
[Same as all devices]

**Contact State Bitfield Registers (0x0010-0x0011):**

| Address | Name | Type | Access | Description |
|---------|------|------|--------|-------------|
| 0x0010 | Channels 1-8 Bitfield | u16 (bitfield) | RO | Bits 0-7 represent channels 1-8 contact states |
| 0x0011 | Channels 9-10 Bitfield | u16 (bitfield) | RO | Bits 0-2 represent channels 9-10 contact states |

**Bitfield Structure:**

Register 0x0010 (Channels 1-8):
- Bit 0: Channel 1 state
- Bit 1: Channel 2 state
- ...
- Bit 7: Channel 8 state
- Bits 8-15: Reserved

Register 0x0011 (Channels 9-10):
- Bit 0: Channel 9 state
- Bit 1: Channel 10 state
- Bits 2-15: Reserved

**Bit Values:**
- 0 = Contact OPEN (circuit open)
- 1 = Contact CLOSED (circuit complete)

**Examples:**
- `0x0010=0x0001, 0x0011=0x0000` = Only channel 1 closed
- `0x0010=0x00FF, 0x0011=0x0000` = Channels 1-8 closed
- `0x0010=0x00FF, 0x0011=0x0007` = All 10 channels closed
```

#### Task 5.2: Update User Documentation
**File:** `docs/USAGE.md`

**Add Section:**
```markdown
## Contact Sensor Splitter Support

The integration supports the Ectocontrol Contact Sensor Splitter (device type 0x59).

### Features
- Monitor dry contact inputs (channel count read from device, typically 10)
- Binary sensor entities for each channel
- 5-second polling interval (fast response)
- Device type auto-detection
- Dynamic entity creation based on actual channel count

### Channel Count
The number of channels is **automatically detected** from the device during setup.
The integration reads the channel count from register 0x0003 LSB and creates
the appropriate number of binary sensor entities. This means:
- A 4-channel device creates 4 entities
- A 10-channel device creates 10 entities
- Any channel count from 1-10 is supported

### Entity Examples
For a device with 10 channels:
- binary_sensor.ectocontrol_uid_8abcdef_channel_1
- binary_sensor.ectocontrol_uid_8abcdef_channel_2
- ...
- binary_sensor.ectocontrol_uid_8abcdef_channel_10

### States
- **On**: Contact closed (circuit complete)
- **Off**: Contact open (circuit broken)
- **Unavailable**: Communication error or device offline
```

## Success Criteria

- [ ] Device type 0x59 is correctly detected during setup
- [ ] Channel count is correctly read from register 0x0003 LSB (not hardcoded!)
- [ ] Dynamic entity creation based on channel_count (1-10 channels)
- [ ] Contact states are accurately read from bitfield registers 0x0010-0x0011
- [ ] Entities show unavailable when communication fails
- [ ] Polling interval is configurable (default 5 seconds)
- [ ] All entities use UID-based unique IDs
- [ ] All entities are associated with a single device
- [ ] Unit tests pass (pytest) including tests for different channel counts (1, 4, 8, 10)
- [ ] Integration tests pass
- [ ] Documentation is updated with correct bitfield structure (0x0010-0x0011)
- [ ] English MODBUS_PROTOCOL.md updated from Russian version
- [ ] Code follows project conventions

## Implementation Timeline

### Week 1: Core Infrastructure
- Day 1-2: ContactSensorGateway implementation with bitfield extraction
- Day 3-4: ContactSensorCoordinator implementation with dynamic register reading
- Day 5: Device router and integration setup updates

### Week 2: Entity Implementation
- Day 1-2: Binary sensor entities for contacts
- Day 3: Config flow updates
- Day 4-5: Testing and bug fixes

### Week 3: Testing & Documentation
- Day 1-2: Unit tests for different channel counts
- Day 3: Integration tests
- Day 4-5: Documentation updates (EN from RU)

## Key Differences from Initial (Incorrect) Plan

| Aspect | Initial Plan (WRONG) | Corrected Plan (RIGHT) |
|--------|---------------------|------------------------|
| **Bitfield Start Address** | 0x0012 | **0x0010-0x0011** |
| **Number of Registers** | 1 register | **1 or 2 registers** (based on channel_count) |
| **Register 0x0010** | Individual channel states | **Channels 1-8 bitfield** |
| **Register 0x0011** | Not used | **Channels 9-10 bitfield** (if channel_count > 8) |
| **Bit Extraction** | Single register | **Two registers with different bit positions** |
| **Channel 9-10** | Bits 8-9 of single register | **Bits 0-1 of register 0x0011** |
| **Source** | English docs (incomplete) | **Russian docs (complete)** |

## References

- **Russian Protocol Documentation:** `docs/MODBUS_PROTOCOL_RU.md` (PRIMARY SOURCE)
- **English Protocol Documentation:** `docs/MODBUS_PROTOCOL.md` (needs update)
- Section 3.2 "ДИСКРЕТНЫЕ ДАТЧИКИ" (Discrete Sensors) - lines 348-368
- Section 9.1 "БЛОК ИЗМЕРИТЕЛЬНЫЙ 8 КАНАЛОВ" - line 1224 (for bitfield at 0x0012 for 8-channel block)

## Notes

This implementation plan is based on the **Russian protocol documentation** which contains complete and accurate information about the Contact Sensor Splitter's bitfield structure. The English documentation should be updated to include this information.
