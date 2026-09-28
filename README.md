# Wahoo KICKR Headwind for Home Assistant

Control a [Wahoo KICKR Headwind](https://www.wahoofitness.com/devices/indoor-cycling/accessories/kickr-headwind-buy)
smart fan from Home Assistant over Bluetooth LE: on/off, speed 0–100 %, and
the fan's own heart-rate / speed / sleep / manual modes.

> **Status: untested on hardware.** The BLE protocol is based on community
> reverse engineering and hasn't been verified against the Wahoo app or a real
> fan yet. See [docs/PROTOCOL.md](docs/PROTOCOL.md) for what's known and the
> two tools in `tools/` for checking it.

## How it connects

```
Headwind ))) BLE ((( Home Assistant Bluetooth adapter
                 or  ESPHome Bluetooth proxy (ESP32) ─── Wi-Fi ─── Home Assistant
```

The integration uses Home Assistant's Bluetooth stack, so it works with a
local adapter **or** any
[ESPHome Bluetooth proxy](https://esphome.io/components/bluetooth_proxy.html)
with `active: true` – that's the "BLE gateway". An ESP32 next to the fan is
usually the most reliable option.

**Shelly:** Shelly scripts can only *scan* BLE advertisements; they can't open
GATT connections or write characteristics, and Shelly's Home Assistant
Bluetooth proxy mode is passive-only. The Headwind has to be connected to and
written to, so Shelly devices can't control it.

The fan normally accepts a single BLE connection: close the Wahoo app (or
turn off Bluetooth on that phone) while Home Assistant is connected. ANT+
(e.g. Zwift via ANT+) is unaffected.

## Install

### HACS
Add this repository as a custom repository (type *Integration*), install
**Wahoo KICKR Headwind**, restart Home Assistant.

### Manual
Copy `custom_components/wahoo_headwind` into your `config/custom_components/`
and restart.

Then the fan should be discovered automatically (Settings → Devices &
services). If it isn't, add the integration by hand and pick it from the list.

## Entities

| Entity | Description |
| --- | --- |
| `fan.headwind_xxxx` | On/off and speed. Setting a speed switches the fan to manual mode. Presets: `manual`, `heart_rate`, `speed`. |
| `select.headwind_xxxx_mode` | Mode: `heart_rate`, `speed`, `sleep`, `manual`. |

Example: start the fan at 40 % when the trainer power sensor goes above 0.

```yaml
automation:
  - alias: Headwind on when riding
    triggers:
      - trigger: numeric_state
        entity_id: sensor.kickr_power
        above: 0
    actions:
      - action: fan.set_percentage
        target: { entity_id: fan.headwind_1234 }
        data: { percentage: 40 }
```

## Alternative: standalone ESPHome

[`esphome/headwind.yaml`](esphome/headwind.yaml) turns an ESP32 into a
dedicated Headwind controller that shows up in Home Assistant as a native
ESPHome fan, with no custom integration needed.

## Debugging

```yaml
logger:
  logs:
    custom_components.wahoo_headwind: debug
```

Every write and raw notification is logged. If the fan's reported state looks
wrong, please open an issue with those log lines.

## Development

```bash
uv venv -p 3.13 .venv
uv pip install -p .venv -r requirements_test.txt
.venv/bin/python -m pytest
```
