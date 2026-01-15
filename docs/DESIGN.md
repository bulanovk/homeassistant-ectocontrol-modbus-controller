# Design & Architecture Guide

## Project Overview

**Ectocontrol Modbus Controller** is a Home Assistant integration that acts as a Modbus controller/master on the RS-485 bus, communicating with Ectocontrol devices. It provides a bridge to embed Ectocontrol device control into Home Assistant.

**First Implementation:** Boiler Controller V2 — exposes gas boiler status and controls via Modbus RTU protocol.

- **Target**: Home Assistant 2025.12+
- **Python**: 3.13+
- **Protocol**: Modbus RTU (19200 baud, no parity)
- **Role**: Modbus controller/master (polls Ectocontrol devices as slaves)
- **Hardware**: Ectocontrol Boiler Controller V2 (or compatible device) connected via RS-485

---

## Multi-Slave Architecture ✨ NEW

### Protocol Manager Layer

**File**: `modbus_protocol_manager.py`

The `ModbusProtocolManager` implements a **singleton pattern** for shared ModbusProtocol instances:

```
Physical Port (COM1)
  └─> ModbusProtocolManager
      └─> Shared ModbusProtocol (1 serial connection)
          ├─> BoilerGateway(slave=1) → Coordinator → Entities
          ├─> BoilerGateway(slave=2) → Coordinator → Entities
          └─> BoilerGateway(slave=3) → Coordinator → Entities
```

**Key Features:**
- **Reference Counting**: Protocol stays open as long as at least one slave is using it
- **Thread-Safe**: Uses `asyncio.Lock` for concurrent access
- **Lifecycle Management**: Auto-closes when last slave is unloaded
- **Resource Efficient**: N slaves share 1 serial connection instead of N

**API:**
```python
# Get shared protocol (increments ref count)
protocol = await manager.get_protocol(port="COM1", baudrate=19200)

# Release protocol (decrements ref count, closes if last)
await manager.release_protocol(port="COM1")

# Close all protocols (HA shutdown)
await manager.close_all()
```

---

## Layered Architecture

The integration uses a **4-layer architecture** for clean separation of concerns:

### Layer 0: Protocol Management — `ModbusProtocolManager` ✨ NEW

**File**: `modbus_protocol_manager.py`

Singleton manager for shared ModbusProtocol instances:
- **Responsibility**: Protocol lifecycle, reference counting, connection sharing
- **API**: `get_protocol()`, `release_protocol()`, `close_all()`
- **Thread-safety**: `asyncio.Lock` for concurrent access
- **Reference counting**: Protocol closes when ref_count reaches 0
- **Benefits**: Multiple slaves share one serial port

### Layer 1: Hardware Communication — `ModbusProtocol`

**File**: `modbus_protocol.py`

Thin async wrapper around `modbus-tk` RTU client:
- **Responsibility**: Serial port I/O, frame construction, error translation
- **API**: `connect()`, `disconnect()`, `read_registers()`, `read_input_registers()`, `write_registers()`, `write_register()`
- **Error handling**: Returns `None` on timeout/Modbus error; never raises exceptions
- **Concurrency**: Single async lock to serialize operations on half-duplex RS-485
- **Execution model**: Wraps sync `modbus-tk` calls in `asyncio.run_in_executor()` to avoid blocking event loop
- **Debug mode**: Optional `DebugSerial` wrapper logs all raw bytes sent/received (TX/RX hex dumps)

### Layer 2: Device Abstraction — `BoilerGateway`

**File**: `boiler_gateway.py`

High-level boiler state adapter:
- **Responsibility**: Register mapping, scaling, unit conversion, device logic
- **API**:
  - **Read helpers** (return from cache, never block): `get_ch_temperature()`, `get_pressure()`, `get_burner_on()`, etc.
  - **Write helpers** (async): `set_ch_setpoint()`, `set_circuit_enable_bit()`, `reboot_adapter()`, etc.
- **Cache**: Populated by `DataUpdateCoordinator`, not by `BoilerGateway` directly
- **Data flow**: Entities → Gateway getters → Cache (populated by Coordinator)
- **Scaling rules**: Apply all ÷10, ÷256, bitfield extraction here; entities use raw values

**Example getter**:
```python
def get_ch_temperature(self) -> Optional[float]:
    raw = self._get_reg(REGISTER_CH_TEMP)
    if raw is None or raw == 0x7FFF:
        return None
    if raw >= 0x8000:
        raw = raw - 0x10000  # Signed interpretation
    return raw / 10.0
```

### Layer 3: Home Assistant Integration — Coordinator & Entities

**Files**: `coordinator.py`, `entities/*.py`, `__init__.py`

- **Coordinator** (`BoilerDataUpdateCoordinator`):
  - Periodically reads all registers (0x0010..0x0026) in a single batch
  - Updates `gateway.cache` with results
  - Tracks update success/failure; marks device unavailable after 3 consecutive failures
  - Polling interval: 15 seconds (configurable via config flow: 5-300 seconds)
  - Retry count: 3 attempts (configurable via config flow: 0-10 retries)
  - Exponential backoff between retries (0.5s, 1s, 1.5s, etc.)

- **Device Registry**:
  - Each adapter creates a single device in Home Assistant (identified by UID)
  - Device names use port-first naming for visual grouping: "{port_name} - Slave {id}"
    - Examples: "COM3 - Slave 1", "ttyUSB0 - Slave 2", "COM3 - Kitchen Boiler"
  - Device identifiers use `{DOMAIN, "uid_{uid_hex}"}` format for uniqueness
  - UID is 24-bit value read from adapter registers (0x800000-0xFFFFFF range)
  - Device info updated after first coordinator poll with manufacturer, model, version data
  - All entities associated with their device via `device_info` property
  - Setup fails if UID cannot be read (ensures proper device identification)
  - **UI Organization**: Devices sorted alphabetically by name, which groups slaves by port

- **Entities** (Sensor, Switch, Number, BinarySensor, Climate, Button):
  - Read-only access to gateway cache via gateway getters
  - Write operations call gateway async helpers then refresh coordinator
  - **Optimistic cache update**: After successful write, switch entities update cache immediately for responsive UI
  - All entities extend `CoordinatorEntity` for automatic availability tracking
  - All entities have unique ID in format `ectocontrol_uid_{uid_hex}_{feature}`
  - All entities use `_attr_has_entity_name = True` for automatic device-prefixed names
  - All entities provide `device_info` property for device association
  - UID must be available; entities raise ValueError if UID is missing

**Example entity flow**:
```python
class CHTemperatureSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    @property
    def unique_id(self) -> str:
        gateway = self.coordinator.gateway
        if not gateway.device_uid:
            raise ValueError("Device UID not available")
        return f"{DOMAIN}_uid_{gateway.get_device_uid_hex()}_ch_temperature"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for entity association."""
        return self.coordinator.gateway.get_device_info()

    @property
    def native_value(self):
        return self.coordinator.gateway.get_ch_temperature()  # Read from cache via gateway

    @property
    def available(self):
        return self.coordinator.last_update_success  # Coordinator tracks availability
```

---

## Data Flow Diagram

```
┌─────────────────────────────┐
│   Home Assistant Entities   │
│  (Sensor, Switch, Climate)  │
└────────────┬────────────────┘
             │ (read via gateway getters)
             │ (write via gateway helpers)
             │
┌────────────▼────────────────┐
│   DataUpdateCoordinator     │
│  (polls every 15s, caches)  │
└────────────┬────────────────┘
             │ (updates gateway.cache)
             │
┌────────────▼────────────────┐
│   BoilerGateway             │
│  (register → value scaling) │
└────────────┬────────────────┘
             │ (reads from cache)
             │ (writes via protocol)
             │
┌────────────▼────────────────┐
│   ModbusProtocol            │
│  (RTU frame I/O)            │
└────────────┬────────────────┘
             │
┌────────────▼────────────────┐
│   Serial Port (19200, RTU)  │
│   ↔ Boiler via RS-485       │
└─────────────────────────────┘
```

---

## Register Mapping

All Modbus registers are 16-bit unless otherwise noted.

### Status & Configuration (Read-Only)

| Address | Name | Type | Scale | Invalid | Purpose |
|---------|------|------|-------|---------|---------|
| 0x0010 | Status | u16 | 1 | — | Adapter type (bits 0-2), comm OK (bit 3), reboot code (MSB) |
| 0x0011 | Version | u16 | 1 | 0xFFFF | HW (MSB), SW (LSB) |
| 0x0018 | CH Temp | i16 | ÷10 | 0x7FFF | Heating circuit water temperature (°C) |
| 0x0019 | DHW Temp | u16 | ÷10 | 0x7FFF | Domestic hot water temperature (°C) |
| 0x001A | Pressure | u8 (LSB) | ÷10 | 0xFF | System pressure (bar) |
| 0x001B | Flow | u8 (LSB) | ÷10 | 0xFF | DHW flow rate (L/min) |
| 0x001C | Modulation | u8 (LSB) | 1 | 0xFF | Burner modulation level (%) |
| 0x001D | States | u8 (LSB) | 1 | — | Bit0=burner, Bit1=heating, Bit2=DHW |
| 0x001E | Main Error | u16 | 1 | 0xFFFF | Error code from boiler |
| 0x001F | Add Error | u16 | 1 | 0xFFFF | Additional error details |
| 0x0020 | Outdoor Temp | i8 (MSB) | 1 | 0x7F | Outside temperature (°C) |
| 0x0026 | CH Setpoint Active | i16 | ÷256 | 0x7FFF | Active CH setpoint (1/256 °C precision) |

### Control Registers (Read/Write)

| Address | Name | Type | Range | Purpose |
|---------|------|------|-------|---------|
| 0x0031 | CH Setpoint | i16 | 0..1000 | CH target temperature (×10, so raw=450 → 45°C) |
| 0x0032 | Emergency CH | i16 | 0..1000 | Emergency CH setpoint |
| 0x0033 | CH Min Limit | u8 | 0..100 | CH minimum allowed temperature |
| 0x0034 | CH Max Limit | u8 | 0..100 | CH maximum allowed temperature |
| 0x0035 | DHW Min Limit | u8 | 0..100 | DHW minimum allowed temperature |
| 0x0036 | DHW Max Limit | u8 | 0..100 | DHW maximum allowed temperature |
| 0x0037 | DHW Setpoint | u8 | 0..100 | DHW target temperature (°C) |
| 0x0038 | Max Modulation | u8 | 0..100 | Maximum burner modulation level (%) |
| 0x0039 | Circuit Enable | u16 | — | Bit0=heating enable, Bit1=DHW enable |
| 0x0080 | Command | u16 | — | 2=reboot adapter, 3=reset errors |

---

## Configuration Flow

User interaction when setting up the integration:

```
1. User adds integration (Settings → Devices & Services → +)
2. ConfigFlow Step 1: Select serial port (e.g., /dev/ttyUSB0, COM3)
3. ConfigFlow Step 2: Enter Modbus slave ID (1–32)
4. ConfigFlow Step 3: Provide friendly name (e.g., "Kitchen Boiler")
5. ConfigFlow Step 4 (Optional): Configure advanced settings:
   - Polling Interval: 5-300 seconds (default: 15)
   - Retry Count: 0-10 retries (default: 3)
   - Debug Modbus: Enable raw hex logging
6. ConfigFlow validates:
   - Port exists
   - Slave ID unique for this port (same port+slave_id combo not allowed)
   - Connection test: read register 0x0010 successfully
7. Entry created with title: "{port_name} - Slave {id}" or "{port_name} - {friendly_name}"
   - Examples: "COM3 - Slave 1", "ttyUSB0 - Kitchen Boiler"
   - This naming groups entries by port when sorted alphabetically in UI
8. async_setup_entry called
9. Device created with name: "{port_name} - Slave {id}" or "{port_name} - {friendly_name}"
   - Device identifier: UID-based for uniqueness
   - No parent/child device relationships (avoided complexity)
10. Entities created and polling begins
11. Device info updated after first successful poll with manufacturer/model/version
```

### Config Entry Naming Convention

Config entries use a **port-first naming convention** for visual grouping in the UI:

- **Without friendly name**: `"{port_name} - Slave {slave_id}"`
  - Example: "COM3 - Slave 1", "COM3 - Slave 2"
  - When sorted alphabetically, all entries for the same port appear together

- **With friendly name**: `"{port_name} - {friendly_name}"`
  - Example: "COM3 - Kitchen Boiler", "COM3 - Living Room"
  - Still groups by port while preserving user-provided names

This approach provides visual grouping in the Settings → Devices & Services list without requiring true config entry nesting (which is not supported by Home Assistant).

### Configuration Data Stored

Each config entry stores:
- `port`: Serial port device path
- `slave_id`: Modbus slave ID (1-32)
- `name`: Friendly device name (optional)
- `polling_interval`: Seconds between polls (5-300, default: 15)
- `retry_count`: Number of retry attempts (0-10, default: 3)
- `debug_modbus`: Enable raw Modbus logging (bool, default: False)

---

## Error Handling

### Protocol Errors

When `ModbusProtocol` encounters an error (timeout, CRC, Modbus exception):
- Returns `None` (for reads) or `False` (for writes)
- Logs error at `ERROR` level
- Does NOT raise exception

### Gateway Errors

When `BoilerGateway` encounters invalid/unsupported data:
- Returns `None` for sensors (entity shows unavailable)
- Checks for invalid markers: `0x7FFF` (16-bit), `0xFF` (8-bit), `0x7F` (8-bit signed)
- Does NOT raise exception

### Coordinator Errors

When polling fails:
- Raises `UpdateFailed` exception (caught by Home Assistant)
- Coordinator tracks failure count; device unavailable after 3 consecutive failures
- **Automatic retry with exponential backoff**:
  - Configurable retry count (default: 3, range: 0-10)
  - Backoff delay: 0.5s × retry attempt (0.5s, 1s, 1.5s, etc.)
  - Logs each retry attempt with attempt number
  - Logs recovery message when connection is restored
  - `UpdateFailed` raised only after all retries exhausted

### Entity Availability

Entities show `unavailable` state when:
- `coordinator.last_update_success` is `False`
- Sensor getter returns `None` (invalid marker)

### Switch Write Pattern (Optimistic Cache Update)

Switch entities use an optimistic cache update pattern for responsive UI:

1. User toggles switch (e.g., Heating Enable)
2. Switch entity calls `gateway.set_circuit_enable_bit()` which:
   - Reads current register value
   - Modifies the specific bit
   - Writes new value to device
   - **On success**: Updates `gateway.cache` immediately (optimistic update)
   - **On failure**: Returns `False`, logs error
3. Switch entity then calls `coordinator.async_request_refresh()` to confirm actual device state
4. UI updates immediately from cache (optimistic), then corrects if device reports different value

**Example**:
```python
async def set_circuit_enable_bit(self, bit: int, enabled: bool) -> bool:
    # Read current value to preserve other bits
    regs = await self.protocol.read_registers(self.slave_id, REGISTER_CIRCUIT_ENABLE, 1)
    current = regs[0] if regs else 0

    if enabled:
        newv = current | (1 << bit)
    else:
        newv = current & ~(1 << bit)

    result = await self.protocol.write_register(self.slave_id, REGISTER_CIRCUIT_ENABLE, newv)
    if result:
        self.cache[REGISTER_CIRCUIT_ENABLE] = newv  # Optimistic update
    return result
```

This pattern provides:
- **Responsive UI**: Switch appears to toggle immediately
- **Error handling**: Write failures are logged and don't update cache
- **Verification**: Refresh cycle confirms actual device state

### Climate Entity

The climate entity provides primary thermostat control for the heating system:

**Features**:
- **HVAC Modes**: HEAT, OFF
- **Temperature Control**: Target temperature with 0.5°C step
- **Dynamic Temperature Limits**: Min/max temperatures read from boiler registers
- **Current Temperature**: Displays actual CH water temperature
- **HVAC Action**: Shows HEATING when burner is on, IDLE otherwise

**Temperature Limits**:
- Min/max limits are read dynamically from registers 0x0033 (CH Min) and 0x0034 (CH Max)
- Falls back to safe defaults if limits unavailable (5.0°C min, 85.0°C max)
- Limits update automatically as polling refreshes cache

**Write Behavior**:
- Setting target temperature writes to register 0x0031 (scaled by 10)
- Setting HVAC mode to HEAT enables bit 0 of register 0x0039 (Circuit Enable)
- Setting HVAC mode to OFF disables bit 0 of register 0x0039
- After write, coordinator refreshes to confirm device state

**Example**:
```python
# User sets temperature to 22.5°C
async def async_set_temperature(self, **kwargs):
    temp = kwargs[ATTR_TEMPERATURE]  # 22.5
    raw = int(round(temp * 10))      # 225
    await self.coordinator.gateway.set_ch_setpoint(raw)
    await self.coordinator.async_request_refresh()

# User enables heating
async def async_set_hvac_mode(self, hvac_mode):
    if hvac_mode == HVACMode.HEAT:
        await self.coordinator.gateway.set_circuit_enable_bit(0, True)
    else:
        await self.coordinator.gateway.set_circuit_enable_bit(0, False)
    await self.coordinator.async_request_refresh()
```

---

## Concurrency & Threading

- **Executor**: All `modbus-tk` calls run in executor to avoid blocking HA event loop
- **Locking**: `ModbusProtocol._lock` ensures serial operations don't interleave (RS-485 is half-duplex)
- **Async/Await**: All public APIs use async/await; no synchronous blocking calls
- **Timeout**: 2–3 seconds for individual Modbus operations

---

## Testing Strategy

### Unit Tests

- **`test_modbus_protocol.py`**: Connection, read/write, error handling
- **`test_boiler_gateway.py`**: Scaling, bitfield extraction, cache logic
- **`test_coordinator.py`**: Polling, cache updates, failure tracking
- **`test_config_flow.py`**: Port/slave validation, duplicate detection
- **`test_entities*.py`**: Entity state, properties, write actions

### Integration Tests

- **`test_integration_modbus.py`**: Full setup with mocked RtuMaster
- Verify coordinator polling cycle
- Verify entities receive updates

### Test Patterns

Use `FakeGateway` and `DummyCoordinator` (not MagicMock) for critical logic isolation:

```python
class FakeGateway:
    def get_ch_temperature(self):
        return 21.5
    
    async def set_ch_setpoint(self, raw):
        self.last_set_raw = raw
        return True

# In test:
gateway = FakeGateway()
coordinator = DummyCoordinator(gateway)
entity = BoilerSensor(coordinator)
assert entity.native_value == 21.5
```

---

## Performance Considerations

- **Polling interval**: 15 seconds default, configurable 5-300 seconds via config flow
- **Retry behavior**: Configurable retry count with exponential backoff for transient failures
- **Batch reads**: All sensors read in single multi-register command (0x0010..0x0026 = 23 registers)
- **Lock overhead**: Minimal; typical Modbus round-trip is 100–500 ms
- **Memory**: Cache holds 23 × 2 bytes = 46 bytes per boiler instance
- **Entity updates**: Debounced by coordinator (only on value change or poll cycle)

---

## Debug Logging

The integration provides comprehensive debug logging for troubleshooting and monitoring:

### Diagnostics Logging (`diagnostics.py`)

When diagnostics are fetched via Home Assistant Developer Tools, the following debug logs are emitted:
- Config entry ID and title
- Gateway slave_id
- Protocol port and baudrate
- Coordinator name
- Cache size (number of registers)
- Complete diagnostics data payload

### Button Command Logging (`button.py`)

Button press actions log:
- "Reboot Adapter button pressed for slave_id=X"
- "Reset Boiler Errors button pressed for slave_id=X"

### Gateway Command Logging (`boiler_gateway.py`)

Command execution logs:
- `Sending reboot command (2) to slave_id=X register=0x0080`
- `Reboot command sent successfully` / `Failed to send reboot command`
- `Sending reset errors command (3) to slave_id=X register=0x0080`
- `Reset errors command sent successfully` / `Failed to send reset errors command`

### Enable Debug Logging

In Home Assistant `configuration.yaml`:
```yaml
logger:
  logs:
    custom_components.ectocontrol_modbus_controller: debug
    custom_components.ectocontrol_modbus_controller.modbus_protocol: debug
    custom_components.ectocontrol_modbus_controller.diagnostics: debug
    custom_components.ectocontrol_modbus_controller.button: debug
```

---

## Future Extensions

- **Auto-discovery**: Scan slave IDs 1–32 to find boilers automatically
- **Multi-register optimization**: Batch multiple setpoint writes into single command
- **Thermostat modes**: HEAT_ONLY, DHW_ONLY, HEAT+DHW
- **Diagnostics enhancements**: Historical error log, burner statistics
- **MQTT bridge**: Publish boiler state to MQTT topics
- **Advanced scheduling**: Time-based setpoint profiles

