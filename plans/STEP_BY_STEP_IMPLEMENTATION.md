# Step-by-Step Implementation Plan: Contact Sensor Splitter

**Device Type:** 0x59 (Contact Sensor Splitter)
**Status:** Ready to Start
**Total Phases:** 16
**Estimated Timeline:** 3 weeks

---

## Phase 0: Preparation & Analysis (Day 1)

### Objective
Understand requirements and study existing codebase patterns.

### Steps

#### Step 0.1: Review Corrected Implementation Plan
- [ ] Read `plans/CONTACT_SPLITTER_IMPLEMENTATION_CORRECTED.md`
- [ ] Understand bitfield structure at 0x0010-0x0011
- [ ] Review key differences from initial (incorrect) plan
- [ ] Confirm register addresses from Russian docs

#### Step 0.2: Study Russian Protocol Documentation
- [ ] Read `docs/MODBUS_PROTOCOL_RU.md` section 3.2 (lines 348-368)
- [ ] Understand discrete sensor bitfield structure
- [ ] Verify register 0x0010 holds channels 1-8
- [ ] Verify register 0x0011 holds channels 9-10
- [ ] Note bit extraction formulas

#### Step 0.3: Study Existing Boiler Gateway
- [ ] Read `custom_components/ectocontrol_modbus_controller/boiler_gateway.py`
- [ ] Understand cache pattern
- [ ] Study device info reading pattern
- [ ] Note validation and error handling patterns

#### Step 0.4: Understand Project Conventions
- [ ] Read `CLAUDE.md` coding guidelines
- [ ] Read `AGENTS.md` agent guidelines
- [ ] Review existing entity patterns
- [ ] Note UID-based device identifier requirement

### Deliverables
- ✅ Understanding of bitfield structure
- ✅ Knowledge of existing patterns
- ✅ Ready to implement

---

## Phase 1: Core Infrastructure - Gateway Layer (Days 2-3)

### Objective
Create `ContactSensorGateway` class with correct bitfield extraction.

### Steps

#### Step 1.1: Create contact_gateway.py File
- [ ] Create `custom_components/ectocontrol_modbus_controller/contact_gateway.py`
- [ ] Add file header with description
- [ ] Import required modules (typing, logging, etc.)
- [ ] Add module-level logger

#### Step 1.2: Implement ContactSensorGateway.__init__()
```python
def __init__(self, protocol, slave_id: int):
    self.protocol = protocol
    self.slave_id = slave_id
    self.cache: Dict[int, int] = {}
    self.device_uid: Optional[int] = None
    self.device_type: Optional[int] = None
    self.channel_count: Optional[int] = None
```
- [ ] Add type hints
- [ ] Initialize all attributes
- [ ] Add docstring

#### Step 1.3: Implement read_device_info() Method
```python
async def read_device_info(self) -> bool:
    # Read registers 0x0000-0x0003
    regs = await self.protocol.read_registers(self.slave_id, 0x0000, 4)
    if regs is None or len(regs) < 4:
        return False
    
    # Extract UID (24-bit from regs[0], regs[1], regs[2] MSB)
    uid_high = regs[1]
    uid_low = (regs[2] >> 8) & 0xFF
    self.device_uid = (uid_high << 8) | uid_low
    
    # Extract device type and channel count from regs[3]
    self.device_type = (regs[3] >> 8) & 0xFF
    self.channel_count = regs[3] & 0xFF
    
    return True
```
- [ ] Implement UID extraction (3 bytes)
- [ ] Implement device type extraction (MSB)
- [ ] Implement channel count extraction (LSB)
- [ ] Add validation for UID range (0x800000-0xFFFFFF)
- [ ] Add validation for channel count (1-10)
- [ ] Add debug logging

#### Step 1.4: Implement get_channel_bitfields() Method
```python
def get_channel_bitfields(self) -> tuple[Optional[int], Optional[int]]:
    reg_0x0010 = self.cache.get(0x0010)
    reg_0x0011 = self.cache.get(0x0011)
    return reg_0x0010, reg_0x0011
```
- [ ] Read from cache (populated by coordinator)
- [ ] Return both register values
- [ ] Handle missing registers gracefully

#### Step 1.5: Implement get_channel_state() Method
```python
def get_channel_state(self, channel: int) -> Optional[bool]:
    # Validate channel number
    if channel < 1 or channel > 10:
        raise ValueError(f"Channel must be 1-10, got {channel}")
    
    # Check against device channel count
    if self.channel_count is not None and channel > self.channel_count:
        return None
    
    reg_0x0010, reg_0x0011 = self.get_channel_bitfields()
    
    if channel <= 8:
        # Channels 1-8 in register 0x0010
        if reg_0x0010 is None:
            return None
        bit_position = channel - 1
        return bool((reg_0x0010 >> bit_position) & 0x01)
    else:
        # Channels 9-10 in register 0x0011
        if reg_0x0011 is None:
            return None
        bit_position = channel - 9
        return bool((reg_0x0011 >> bit_position) & 0x01)
```
- [ ] Add channel validation (1-10)
- [ ] Check against channel_count
- [ ] Extract bits from correct register
- [ ] Use correct bit position formula
- [ ] Return True (closed) or False (open)

#### Step 1.6: Implement Helper Methods
```python
def get_channel_count(self) -> int:
    return self.channel_count if self.channel_count is not None else 0

def get_device_uid_hex(self) -> Optional[str]:
    if self.device_uid is None:
        return None
    return f"{self.device_uid:06x}"

def get_device_type_name(self) -> Optional[str]:
    if self.device_type is None:
        return None
    from .const import DEVICE_TYPE_NAMES
    return DEVICE_TYPE_NAMES.get(self.device_type, f"Unknown (0x{self.device_type:02X})")

def get_device_info(self) -> DeviceInfo:
    from homeassistant.helpers.device_registry import DeviceInfo
    from .const import DOMAIN
    
    if not self.device_uid:
        _LOGGER.error("Device UID not available")
        return DeviceInfo(identifiers={(DOMAIN, f"uid_{self.get_device_uid_hex()}")})
    
    return DeviceInfo(
        identifiers={(DOMAIN, f"uid_{self.get_device_uid_hex()}")},
        name=f"Ectocontrol Contact Splitter {self.get_channel_count()}ch",
        manufacturer="Ectocontrol",
        model=self.get_device_type_name(),
        serial_number=self.get_device_uid_hex(),
    )
```
- [ ] Implement all helper methods
- [ ] Use UID-based device identifier
- [ ] Add proper error handling

#### Step 1.7: Add Documentation
- [ ] Add module docstring
- [ ] Add class docstring
- [ ] Add method docstrings
- [ ] Document bit extraction formulas

### Deliverables
- ✅ `contact_gateway.py` file created
- ✅ All methods implemented
- ✅ Ready for testing

---

## Phase 2: Core Infrastructure - Coordinator Layer (Days 4-5)

### Objective
Create `ContactSensorDataUpdateCoordinator` with dynamic polling.

### Steps

#### Step 2.1: Create contact_coordinator.py File
- [ ] Create `custom_components/ectocontrol_modbus_controller/contact_coordinator.py`
- [ ] Add imports (DataUpdateCoordinator, UpdateFailed, etc.)
- [ ] Add module logger

#### Step 2.2: Implement ContactSensorDataUpdateCoordinator Class
```python
class ContactSensorDataUpdateCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, gateway, name, update_interval, retry_count, config_entry):
        self.gateway = gateway
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=update_interval,
        )
        self.retry_count = retry_count
        self.config_entry = config_entry
```
- [ ] Initialize coordinator
- [ ] Store gateway reference
- [ ] Set up retry logic

#### Step 2.3: Implement _async_update_data() Method
```python
async def _async_update_data(self) -> Dict[int, int]:
    channel_count = self.gateway.channel_count or 10
    
    if channel_count <= 8:
        # Only need register 0x0010
        regs = await self.gateway.protocol.read_registers(
            self.gateway.slave_id,
            0x0010,
            1
        )
        if regs is None or len(regs) == 0:
            raise UpdateFailed("Failed to read contact states")
        return {0x0010: regs[0]}
    else:
        # Need both registers
        regs = await self.gateway.protocol.read_registers(
            self.gateway.slave_id,
            0x0010,
            2
        )
        if regs is None or len(regs) < 2:
            raise UpdateFailed("Failed to read contact states")
        return {0x0010: regs[0], 0x0011: regs[1]}
```
- [ ] Implement dynamic register reading
- [ ] Read 1 register for ≤8 channels
- [ ] Read 2 registers for >8 channels
- [ ] Update gateway cache
- [ ] Handle errors appropriately

#### Step 2.4: Implement is_channel_available() Method
```python
def is_channel_available(self, channel: int) -> bool:
    if self.gateway.channel_count is None:
        return False
    if channel < 1 or channel > self.gateway.channel_count:
        return False
    
    if channel <= 8:
        return 0x0010 in self.gateway.cache
    else:
        return 0x0011 in self.gateway.cache
```
- [ ] Check channel count
- [ ] Check appropriate register in cache
- [ ] Return boolean

#### Step 2.5: Add Error Handling
- [ ] Add retry logic with exponential backoff
- [ ] Add timeout handling
- [ ] Add logging for diagnostics

### Deliverables
- ✅ `contact_coordinator.py` file created
- ✅ Dynamic polling implemented
- ✅ Ready for testing

---

## Phase 3: Device Detection & Routing (Day 6)

### Objective
Create device router to detect device type and create appropriate gateway.

### Steps

#### Step 3.1: Create device_router.py File
- [ ] Create `custom_components/ectocontrol_modbus_controller/device_router.py`
- [ ] Add imports

#### Step 3.2: Implement create_device_gateway() Function
```python
async def create_device_gateway(protocol, slave_id: int) -> Union[BoilerGateway, ContactSensorGateway]:
    # Read device info registers
    regs = await protocol.read_registers(slave_id, 0x0000, 4)
    if regs is None or len(regs) < 4:
        raise ValueError("Failed to read device info")
    
    # Extract device type (MSB of register 3)
    device_type = (regs[3] >> 8) & 0xFF
    
    # Create appropriate gateway
    if device_type == 0x59:
        from .contact_gateway import ContactSensorGateway
        gateway = ContactSensorGateway(protocol, slave_id)
    elif device_type in [0x14, 0x15, 0x16]:
        from .boiler_gateway import BoilerGateway
        gateway = BoilerGateway(protocol, slave_id)
    else:
        raise ValueError(f"Unsupported device type: 0x{device_type:02X}")
    
    # Read device info
    await gateway.read_device_info()
    
    return gateway
```
- [ ] Implement device type detection
- [ ] Route to correct gateway class
- [ ] Call read_device_info() automatically
- [ ] Add error handling

### Deliverables
- ✅ `device_router.py` file created
- ✅ Device type detection working
- ✅ Ready for integration

---

## Phase 4: Entity Implementation (Days 7-8)

### Objective
Create binary sensor entities for contact channels.

### Steps

#### Step 4.1: Create contact_binary_sensor.py File
- [ ] Create `custom_components/ectocontrol_modbus_controller/contact_binary_sensor.py`
- [ ] Add imports

#### Step 4.2: Implement ContactChannelBinarySensor Class
```python
class ContactChannelBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.OPENING
    
    def __init__(self, coordinator, channel: int):
        super().__init__(coordinator)
        self._channel = channel
        self._attr_name = f"Channel {channel}"
```

#### Step 4.3: Implement Properties
```python
@property
def unique_id(self) -> str:
    gateway = self.coordinator.gateway
    return f"{DOMAIN}_uid_{gateway.get_device_uid_hex()}_channel_{self._channel}"

@property
def device_info(self) -> DeviceInfo:
    return self.coordinator.gateway.get_device_info()

@property
def is_on(self) -> bool | None:
    return self.coordinator.gateway.get_channel_state(self._channel)
```
- [ ] Implement unique_id with UID format
- [ ] Implement device_info for association
- [ ] Implement is_on using gateway

#### Step 4.4: Implement async_setup_entry()
```python
async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    gateway = data["gateway"]
    
    entities = []
    for channel in range(1, gateway.get_channel_count() + 1):
        entities.append(ContactChannelBinarySensor(coordinator, channel))
    
    async_add_entities(entities)
```
- [ ] Dynamically create entities based on channel_count
- [ ] Only create for valid channels (1 to channel_count)

### Deliverables
- ✅ `contact_binary_sensor.py` file created
- ✅ Dynamic entity creation working
- ✅ Ready for testing

---

## Phase 5: Integration Setup (Day 9)

### Objective
Update `__init__.py` to support multiple device types.

### Steps

#### Step 5.1: Update Imports in __init__.py
- [ ] Add import for device_router
- [ ] Add import for ContactSensorDataUpdateCoordinator
- [ ] Add import for ContactSensorGateway

#### Step 5.2: Modify async_setup_entry()
- [ ] Replace direct BoilerGateway creation with create_device_gateway()
- [ ] Add conditional coordinator creation
- [ ] Add conditional platform forwarding

```python
# Create gateway using router
gateway = await create_device_gateway(protocol, slave)

# Create appropriate coordinator
if isinstance(gateway, BoilerGateway):
    coordinator = BoilerDataUpdateCoordinator(...)
elif isinstance(gateway, ContactSensorGateway):
    coordinator = ContactSensorDataUpdateCoordinator(...)

# Forward to platforms
if isinstance(gateway, BoilerGateway):
    platforms = ["sensor", "switch", "number", "binary_sensor", "climate", "button"]
elif isinstance(gateway, ContactSensorGateway):
    platforms = ["binary_sensor"]
```

### Deliverables
- ✅ `__init__.py` updated
- ✅ Multi-device support working
- ✅ Ready for testing

---

## Phase 6: Configuration Flow Updates (Day 10)

### Objective
Update config flow to display device type and channel count.

### Steps

#### Step 6.1: Update Connection Test Step
- [ ] Read device type during connection test
- [ ] Display device type name
- [ ] Display channel count

#### Step 6.2: Update strings.json
- [ ] Add translation keys for device type display
- [ ] Add translation for channel count display

### Deliverables
- ✅ Config flow updated
- ✅ User sees device info during setup

---

## Phase 7: Constants & Type Definitions (Day 11)

### Objective
Add Contact Sensor Splitter constants to const.py.

### Steps

#### Step 7.1: Add Register Constants
```python
# Contact Sensor Splitter registers
REGISTER_CONTACT_CHANNELS_1_8 = 0x0010
REGISTER_CONTACT_CHANNELS_9_10 = 0x0011
```

#### Step 7.2: Add Device Type Constants
```python
DEVICE_TYPE_CONTACT_SPLITTER = 0x59
```

#### Step 7.3: Update DEVICE_TYPE_NAMES
```python
DEVICE_TYPE_NAMES = {
    ...
    0x59: "Contact Sensor Splitter",
}
```

### Deliverables
- ✅ `const.py` updated
- ✅ All constants defined

---

## Phase 8-11: Unit & Integration Testing (Days 12-15)

### Objective
Comprehensive testing of all components.

### Test Files to Create
1. `tests/test_contact_gateway.py`
2. `tests/test_contact_coordinator.py`
3. `tests/test_contact_entities.py`
4. `tests/test_contact_splitter_integration.py`

### Test Coverage Requirements
- [ ] Bitfield extraction for all channel counts (1, 4, 8, 10)
- [ ] Dynamic register reading (1 vs 2 registers)
- [ ] Entity state and properties
- [ ] Full integration flow
- [ ] Error handling and edge cases

### Deliverables
- ✅ All test files created
- ✅ pytest -q passes
- ✅ pytest --cov shows >80% coverage

---

## Phase 12-13: Documentation Updates (Day 16-17)

### Objective
Update English documentation from Russian version.

### Steps

#### Step 12.1: Update MODBUS_PROTOCOL.md
- [ ] Add Contact Sensor Splitter section
- [ ] Document registers 0x0010-0x0011
- [ ] Add bitfield structure diagrams
- [ ] Add bit extraction examples

#### Step 12.2: Update USAGE.md
- [ ] Add Contact Sensor Splitter usage section
- [ ] Document entity examples
- [ ] Document states and behaviors

#### Step 12.3: Update DESIGN.md
- [ ] Add multi-device architecture section
- [ ] Document device router pattern

### Deliverables
- ✅ English docs updated from Russian
- ✅ User documentation complete

---

## Phase 14-15: Code Quality & Final Testing (Days 18-19)

### Objective
Ensure code quality and all tests pass.

### Steps

#### Step 14.1: Run Linters
```bash
pylint custom_components/ectocontrol_modbus_controller/contact_*.py
mypy custom_components/ectocontrol_modbus_controller/contact_*.py
```

#### Step 14.2: Run Full Test Suite
```bash
pytest -q
pytest --cov=custom_components --cov-report=html
```

#### Step 14.3: Fix Issues
- [ ] Fix any pylint warnings
- [ ] Fix any type errors
- [ ] Fix any test failures
- [ ] Improve coverage if needed

### Deliverables
- ✅ All linting passes
- ✅ All tests pass
- ✅ Coverage >80%

---

## Phase 16: Git Commit & Documentation (Day 20)

### Objective
Commit changes and finalize documentation.

### Steps

#### Step 16.1: Review Changes
```bash
git diff
git status
```

#### Step 16.2: Create Commit
```bash
git add .
git commit -m "Add support for Contact Sensor Splitter (device type 0x59)

- Implement ContactSensorGateway with bitfield extraction from registers 0x0010-0x0011
- Implement ContactSensorDataUpdateCoordinator with dynamic polling
- Add device router for multi-device support
- Add binary sensor entities for contact channels
- Update documentation from Russian protocol docs

Co-authored-by: factory-droid[bot] <138933559+factory-droid[bot]@users.noreply.github.com>"
```

#### Step 16.3: Update IMPLEMENTATION.md
- [ ] Mark implementation as complete
- [ ] Add lessons learned
- [ ] Document any deviations from plan

### Deliverables
- ✅ Changes committed
- ✅ Documentation complete
- ✅ Ready for review

---

## Progress Tracking

### Completed Phases
- None yet

### Current Phase
- Phase 0: Preparation & Analysis

### Next Steps
1. Review corrected implementation plan
2. Study Russian protocol documentation
3. Begin Phase 1 implementation

### Notes
- Always use Russian documentation (MODBUS_PROTOCOL_RU.md) as primary source
- Double-check register addresses (0x0010-0x0011, NOT 0x0012)
- Test with multiple channel counts (1, 4, 8, 10)
- Follow all project conventions from CLAUDE.md and AGENTS.md
