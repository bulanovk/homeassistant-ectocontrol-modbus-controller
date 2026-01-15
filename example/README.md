# Ectocontrol Modbus Boiler - Example Dashboards

This folder contains example Home Assistant Lovelace dashboards for visualizing and controlling the Ectocontrol Modbus Adapter v2 boiler integration. The adapter supports both gas and electric boilers.

## Folder Structure

```
example/
├── README.md                 # This file
├── dashboards/
│   ├── boiler-dashboard.yaml         # Full-featured multi-view dashboard
│   └── boiler-compact.yaml           # Single-view dashboard (no HACS required)
└── cards/
    ├── temperature-card.yaml          # Temperature monitoring cards
    ├── pressure-status-card.yaml      # Pressure & system status cards
    ├── controls-card.yaml             # Switches, numbers, and buttons
    └── energy-monitoring-card.yaml    # Efficiency & power level analysis
```

## Quick Start

### Option 1: Import Complete Dashboard (Recommended)

1. Go to **Settings** > **Dashboards** in Home Assistant
2. Click **Add Dashboard** > **Add by ID** (or **Import YAML**)
3. Choose your dashboard:
   - `dashboards/boiler-dashboard.yaml` - Full featured with charts
   - `dashboards/boiler-compact.yaml` - Simple, no HACS required
4. Click **Import**
5. Replace `{slave_id}` with your Modbus slave ID (usually `1`)

### Option 2: Add Cards to Existing Dashboard

1. Open your existing dashboard in edit mode
2. Click **Add Card** > **Manual configuration**
3. Copy card definitions from `cards/` folder
4. Replace entity IDs with your actual slave ID
5. Click **Save**

### Option 3: Create Custom Dashboard

1. Copy individual card sections from the example dashboards
2. Mix and match to create your own layout
3. See `cards/` folder for pre-built card components

## Entity ID Format

All entities use this naming pattern:

```
ectocontrol_{slave_id}_{entity_name}
```

- `{slave_id}` - Your Modbus slave ID configured in the integration (default: `1`)
- `{entity_name}` - The specific sensor/switch/number

**Example:** If your slave ID is `1`:
- `sensor.ectocontrol_1_get_ch_temperature`
- `switch.ectocontrol_1_circuit_0`
- `number.ectocontrol_1_ch_setpoint`

If your slave ID is different, replace `_1_` with `_{your_id}_` throughout the dashboards.

## Available Entities

### Sensors
| Entity | Description | Unit |
|--------|-------------|------|
| `sensor.ectocontrol_*_get_ch_temperature` | Central heating temperature | °C |
| `sensor.ectocontrol_*_get_dhw_temperature` | Domestic hot water temperature | °C |
| `sensor.ectocontrol_*_get_pressure` | System water pressure | bar |
| `sensor.ectocontrol_*_get_flow_rate` | Water flow rate | L/min |
| `sensor.ectocontrol_*_get_modulation_level` | Power level (burner/heater) | % |
| `sensor.ectocontrol_*_get_outdoor_temperature` | Outdoor temperature | °C |
| `sensor.ectocontrol_*_get_ch_setpoint_active` | Active CH setpoint | °C |

### Binary Sensors
| Entity | Description |
|--------|-------------|
| `binary_sensor.ectocontrol_*_get_burner_on` | Heating element active state |
| `binary_sensor.ectocontrol_*_get_heating_enabled` | Heating circuit enabled |
| `binary_sensor.ectocontrol_*_get_dhw_enabled` | DHW circuit enabled |

### Switches
| Entity | Description |
|--------|-------------|
| `switch.ectocontrol_*_circuit_0` | Enable heating circuit |
| `switch.ectocontrol_*_circuit_1` | Enable DHW circuit |

### Numbers
| Entity | Description | Range |
|--------|-------------|-------|
| `number.ectocontrol_*_ch_setpoint` | CH setpoint | -10 to 100 °C |
| `number.ectocontrol_*_ch_min` | CH minimum limit | 0 to 100 °C |
| `number.ectocontrol_*_ch_max` | CH maximum limit | 0 to 100 °C |
| `number.ectocontrol_*_dhw_setpoint` | DHW setpoint | 0 to 100 °C |
| `number.ectocontrol_*_max_modulation` | Max power level | 0 to 100 % |

### Climate
| Entity | Description |
|--------|-------------|
| `climate.ectocontrol_*_climate` | Main thermostat control |

### Buttons
| Entity | Description |
|--------|-------------|
| `button.ectocontrol_*_reset_errors` | Reset boiler errors |
| `button.ectocontrol_*_reboot` | Reboot Modbus adapter |

## Dashboard Features

### boiler-dashboard.yaml

A comprehensive multi-view dashboard with:

- **Overview** - Quick status glance with heating element state, temperature, pressure
- **Heating** - CH controls, temperature history, setpoints
- **Hot Water** - DHW controls and temperature monitoring
- **Statistics** - 7-day temperature trends, pressure history, power level analysis
- **Settings** - All limits, device info, maintenance actions

**Required HACS Addons:**
- [Mushroom Cards](https://github.com/piitaya/lovelace-mushroom)
- [ApexCharts Card](https://github.com/RomRider/apexcharts-card)

### boiler-compact.yaml

A single-view dashboard using only built-in Home Assistant cards:

- No HACS addons required
- Quick status, gauges, history graphs
- Climate control, setpoints, circuit switches
- Maintenance actions

### Individual Card Examples

| Card File | Contents |
|-----------|----------|
| `temperature-card.yaml` | Temperature displays with graphs |
| `pressure-status-card.yaml` | System health monitoring |
| `controls-card.yaml` | All switches, numbers, buttons |
| `energy-monitoring-card.yaml` | Power level and efficiency analysis |

## Customization Tips

### Change Entity Names

Replace all occurrences of `_1_` with your actual slave ID:

```yaml
# Before
entity: sensor.ectocontrol_1_get_ch_temperature

# After (for slave ID 2)
entity: sensor.ectocontrol_2_get_ch_temperature
```

### Adjust Temperature Ranges

Modify gauge min/max values based on your system:

```yaml
- type: gauge
  entity: sensor.ectocontrol_1_get_ch_temperature
  min: 0    # Adjust as needed
  max: 100  # Adjust as needed
```

### Customize Severity Thresholds

Set warning levels based on your boiler specifications:

```yaml
severity:
  green: 1.2   # Normal pressure
  yellow: 1.8  # Warning zone
  red: 2.5     # Critical zone
```

### Change Graph Time Ranges

Adjust history display duration:

```yaml
hours_to_show: 24   # Show last 24 hours
# or
span:
  start: week       # Show last 7 days
```

## Troubleshooting

### Entities Show as Unavailable

1. Verify the integration is configured correctly
2. Check Modbus connection in **Settings** > **Devices & Services**
3. Verify slave ID matches your adapter configuration
4. Check Home Assistant logs for errors

### Cards Don't Display

1. Ensure entity IDs match your configured slave ID
2. Verify entities exist in **Developer Tools** > **States**
3. Check browser console for JavaScript errors

### Missing Custom Cards (boiler-dashboard.yaml)

Install required HACS addons:
```bash
# In HACS frontend:
1. Install "Mushroom Cards"
2. Install "ApexCharts Card"
3. Clear browser cache
4. Reload dashboard
```

## Further Resources

- [Home Assistant Lovelace Documentation](https://www.home-assistant.io/dashboards/)
- [Mushroom Cards Documentation](https://mui-x.github.io/mushroom/)
- [ApexCharts Card Documentation](https://github.com/RomRider/apexcharts-card)
