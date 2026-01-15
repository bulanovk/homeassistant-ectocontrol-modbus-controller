# Implementation Plan: 10-Channel Contact Sensor Splitter

**Device Type:** 0x59 (Contact Sensor Splitter 10ch)
**Date:** 2025-01-15
**Status:** Planning Phase

## Overview

The 10-Channel Contact Sensor Splitter is a Modbus RTU device that monitors 10 digital contact inputs (dry contacts) and exposes their states via Modbus holding registers. This implementation will add support for this device type to the existing Ectocontrol Modbus Controller integration.

## Device Specifications

### Hardware Details
- **Device Type Code:** 0x59 (from REGISTER_TYPE_CHANNELS MSB)
- **Channel Count:** Read from REGISTER_TYPE_CHANNELS LSB (1-10 channels supported)
- **Communication:** Modbus RTU over RS-485
- **Baud Rate:** 19200
- **Register Map:** Uses generic device info registers + contact state registers

**IMPORTANT:** Channel count is **dynamic** and read from the device at runtime. The implementation must support variable channel counts (1-10), not assume exactly 10 channels.

### Register Map for Contact Splitter

#### Generic Device Information (0x0000-0x0003)
All Ectocontrol devices share these registers:

| Address | Name | Type | Access | Description |
|---------|------|------|--------|-------------|
| 0x0000 | Reserved | u16 | RO | Reserved for future use |
| 0x0001 | UID | u24 | RO | Unique device identifier (0x800000-0xFFFFFF) |
| 0x0002 | Address | u8/u8 | RO | Reserved (MSB), Device Modbus address (LSB, 1-32) |
| 0x0003 | Type + Channels | u8/u8 | RO | Device type=0x59 (MSB), Channel count (LSB, range: 1-10) |

#### Contact State Registers (Bitfield at 0x0012)

**CRITICAL:** Contact states are stored in a **single bitfield register**, not as individual registers!

| Address | Name | Type | Access | Description |
|---------|------|------|--------|-------------|
| 0x0012 | Channel Bitfield | u16 (bitfield) | RO | Bits 0-9 represent channels 1-10 contact states |

**Bitfield Structure (Register 0x0012):**
```
+--------+--------+--------+--------+--------+--------+--------+--------+
|  15-10 |   9    |   8    |   7    |   6    |   5    |   4    |   3    |
+--------+--------+--------+--------+--------+--------+--------+--------+
|  Resvd | CH10   | CH9    | CH8    | CH7    | CH6    | CH5    | CH4    |
+--------+--------+--------+--------+--------+--------+--------+--------+
+--------+--------+--------+--------+--------+--------+--------+--------+
|   2    |   1    |   0    |
+--------+--------+--------+
| CH3    | CH2    | CH1    |
+--------+--------+--------+

Bit n = 0 → Contact OPEN (circuit open)
Bit n = 1 → Contact CLOSED (circuit complete)
```

**Example:**
- Value `0x0000` (binary: 0000000000000000) = All channels OPEN
- Value `0x0005` (binary: 0000000000000101) = Channels 1 and 3 CLOSED, others OPEN
- Value `0x03FF` (binary: 0000001111111111) = All 10 channels CLOSED
- Value `0x0001` (binary: 0000000000000001) = Only channel 1 CLOSED

**Important Notes:**
- Only bits 0-9 are used (channels 1-10)
- Bits 10-15 are reserved and should be ignored
- The bitfield is in the LSB (bits 0-15 of the 16-bit register)
- Channel count is dynamic (1-10), so only valid channels should be read

**Contact State Values:**
- `0` = Contact OPEN (circuit open)
- `1` = Contact CLOSED (circuit closed)
- Other values = Reserved or error states

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
- Cache contact state bitfield register (0x0012)
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

    def get_channel_bitfield(self) -> Optional[int]:
        """Get the raw bitfield value from register 0x0012.

        Returns:
            16-bit bitfield value where bit n represents channel n+1 state
            None if register not available or read failed
        """
        # Read from cache (populated by coordinator)
        raw = self.cache.get(0x0012)
        return raw

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
            Channel 1 = bit 0 of register 0x0012
            Channel 2 = bit 1 of register 0x0012
            Channel n = bit (n-1) of register 0x0012
        """
        # Validate channel number
        if channel < 1 or channel > 10:
            raise ValueError(f"Channel must be 1-10, got {channel}")

        # Check against device channel count
        if self.channel_count is not None and channel > self.channel_count:
            return None

        # Get bitfield from cache
        bitfield = self.get_channel_bitfield()
        if bitfield is None:
            return None

        # Extract bit for this channel (channel 1 = bit 0, channel 2 = bit 1, etc.)
        bit_position = channel - 1
        is_closed = bool((bitfield >> bit_position) & 0x01)

        return is_closed

    def get_device_info(self) -> DeviceInfo:
        """Return Home Assistant DeviceInfo structure"""
```

**Bit Extraction Example:**
```python
# If register 0x0012 contains 0x0005 (binary: 0000000000000101)
bitfield = 0x0005

# Channel 1 (bit 0):
ch1_state = (bitfield >> 0) & 0x01  # = 1 → CLOSED

# Channel 2 (bit 1):
ch2_state = (bitfield >> 1) & 0x01  # = 0 → OPEN

# Channel 3 (bit 2):
ch3_state = (bitfield >> 2) & 0x01  # = 1 → CLOSED

# Channel 4 (bit 3):
ch4_state = (bitfield >> 3) & 0x01  # = 0 → OPEN
```

**Validation:**
- Channel count must be in range 1-10 (read from device, not hardcoded!)
- Device type must be 0x59
- UID must be in valid range (0x800000-0xFFFFFF)
- Channel number must be 1-10 and <= channel_count when calling get_channel_state()
- Bits 10-15 of register 0x0012 are reserved and should be ignored

#### Task 1.2: Create ContactSensorCoordinator Class
**File:** `custom_components/ectocontrol_modbus_controller/contact_coordinator.py`

**Responsibilities:**
- Poll contact state bitfield register every N seconds (default: 5 seconds)
- Update gateway cache with latest bitfield value
- Handle connection errors and retries
- Track update success for entity availability

**Key Methods:**
```python
class ContactSensorDataUpdateCoordinator(DataUpdateCoordinator):
    async def _async_update_data(self) -> Dict[int, int]:
        """Read contact state bitfield from register 0x0012.

        For the Contact Sensor Splitter, we only need to read ONE register (0x0012)
        which contains a bitfield of all channel states. This is much more efficient
        than reading individual registers for each channel.

        Returns:
            Dictionary with single entry: {0x0012: bitfield_value}
        """
        # Read register 0x0012 (channel states bitfield)
        regs = await self.gateway.protocol.read_registers(
            self.gateway.slave_id,
            0x0012,  # Channel bitfield register
            1        # Only 1 register needed!
        )

        if regs is None or len(regs) == 0:
            raise UpdateFailed("Failed to read contact states")

        # Update gateway cache
        cache_data = {0x0012: regs[0]}
        return cache_data

    def is_channel_available(self, channel: int) -> bool:
        """Check if channel has valid data (bitfield available and channel in range)"""
        if self.gateway.channel_count is None:
            return False
        if channel < 1 or channel > self.gateway.channel_count:
            return False
        return 0x0012 in self.gateway.cache
```

**Polling Strategy:**
- Default interval: 5 seconds (contacts change faster than boiler temps)
- **Single register read**: Only read register 0x0012 (bitfield), not multiple registers!
- **Efficient**: One register contains ALL channel states in a bitfield
- Retry logic: Use existing retry mechanism from coordinator
- **Much simpler than boiler**: No need to calculate dynamic register ranges

**Comparison with Boiler:**
- **Boiler**: Reads 23 registers (0x0010-0x0026) for various sensors
- **Contact Splitter**: Reads 1 register (0x0012) for ALL channel states (bitfield)
- **Efficiency**: Contact splitter polling is ~23x more efficient!

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
    # Return BoilerGateway for type 0x14
    # Return ContactSensorGateway for type 0x59
    # Raise error for unsupported types
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
✓ Channels: 10 (dynamically read from device)
✓ Communication: OK
```

**Important:** The config flow should display the actual channel count read from the device, not assume 10 channels.

### Phase 4: Testing

#### Task 4.1: Create Unit Tests
**File:** `tests/test_contact_gateway.py`

**Test Cases:**
- Test device info reading (UID, type, channels)
- Test channel state getter methods
- Test dynamic channel count handling (1, 4, 10 channels)
- Test invalid channel numbers (out of range, > channel_count)
- Test invalid state values
- Test device info generation
- Test that channel_count is correctly read from register 0x0003 LSB

**File:** `tests/test_contact_coordinator.py`

**Test Cases:**
- Test polling logic for dynamic channel counts (1, 4, 10 channels)
- Test dynamic register range calculation based on channel_count
- Test cache updates
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
- Test with different channel counts (1, 4, 10 channels)

### Phase 5: Documentation

#### Task 5.1: Update User Documentation
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

For a device with 4 channels:
- binary_sensor.ectocontrol_uid_8abcdef_channel_1
- binary_sensor.ectocontrol_uid_8abcdef_channel_2
- binary_sensor.ectocontrol_uid_8abcdef_channel_3
- binary_sensor.ectocontrol_uid_8abcdef_channel_4

### States
- **On**: Contact closed (circuit complete)
- **Off**: Contact open (circuit broken)
- **Unavailable**: Communication error or device offline
```

#### Task 5.2: Update Developer Documentation
**File:** `docs/DESIGN.md`

**Add Section:**
```markdown
## Multi-Device Architecture

The integration supports multiple Ectocontrol device types through a gateway-based architecture.

### Device Type Detection
Device type is read from REGISTER_TYPE_CHANNELS (0x0003 MSB) during setup.

### Gateway Classes
- `BoilerGateway`: For OpenTherm/eBus/Navien adapters (type 0x14, 0x15, 0x16)
- `ContactSensorGateway`: For Contact Sensor Splitter (type 0x59)

### Coordinator Classes
Each device type has a specialized coordinator with appropriate polling logic.

### Adding New Device Types
1. Create gateway class in `<device>_gateway.py`
2. Create coordinator class in `<device>_coordinator.py`
3. Add device type code to `const.py`
4. Update `device_router.py` to route to new gateway
5. Implement entity classes in appropriate platform files
6. Add tests and documentation
```

## Implementation Timeline

### Week 1: Core Infrastructure
- Day 1-2: ContactSensorGateway implementation
- Day 3-4: ContactSensorCoordinator implementation
- Day 5: Device router and integration setup updates

### Week 2: Entity Implementation
- Day 1-2: Binary sensor entities for contacts
- Day 3: Config flow updates
- Day 4-5: Testing and bug fixes

### Week 3: Testing & Documentation
- Day 1-2: Unit tests
- Day 3: Integration tests
- Day 4-5: Documentation updates

## Success Criteria

- [ ] Device type 0x59 is correctly detected during setup
- [ ] Channel count is correctly read from register 0x0003 LSB (not hardcoded!)
- [ ] Dynamic entity creation based on channel_count (1-10 channels)
- [ ] Contact states are accurately reported (open/closed)
- [ ] Entities show unavailable when communication fails
- [ ] Polling interval is configurable (default 5 seconds)
- [ ] All entities use UID-based unique IDs
- [ ] All entities are associated with a single device
- [ ] Unit tests pass (pytest) including tests for different channel counts
- [ ] Integration tests pass
- [ ] Documentation is updated with dynamic channel count information
- [ ] Code follows project conventions

## Potential Challenges & Mitigation

### Challenge 1: Device Type Detection Timing
**Issue:** Device type must be read before creating gateway
**Solution:** Read device info in async_setup_entry before gateway creation

### Challenge 2: Mixed Device Types on Same Port
**Issue:** Multiple devices with different types on one RS-485 bus
**Solution:** Each config entry represents one slave ID, device type is per-entry

### Challenge 3: Polling Interval Differences
**Issue:** Contacts need faster polling than boiler temps
**Solution:** Different coordinators have different default intervals (5s vs 15s)

### Challenge 4: Entity Platform Routing
**Issue:** Contact splitter only needs binary_sensor platform
**Solution:** Route platforms dynamically based on device type in async_setup_entry

### Challenge 5: Dynamic Channel Count Handling
**Issue:** Different devices may have different channel counts (1-10)
**Solution:**
- Always read channel_count from register 0x0003 LSB during setup
- Store channel_count in gateway instance
- Create entities dynamically based on actual channel count
- Validate channel numbers are <= channel_count in all methods
- Test with multiple channel counts (1, 4, 10)

## Future Enhancements

1. **Sensor Debouncing:** Add configurable debounce time for contact inputs
2. **Counter Entities:** Add counter sensors for pulse counting (if supported)
3. **Alert Entities:** Create alert entities for state change notifications
4. **Group Support:** Allow grouping channels for multi-sensor detection
5. **Custom Entity Names:** Allow users to name channels (e.g., "Front Door", "Window")

## References

- Modbus Protocol Document: `docs/MODBUS_PROTOCOL.md`
- Russian Protocol Documentation: Contains detailed register descriptions
- Existing Boiler Implementation: Reference for patterns and conventions
- Home Assistant Binary Sensor Docs: https://developers.home-assistant.io/docs/core/entity/binary-sensor
