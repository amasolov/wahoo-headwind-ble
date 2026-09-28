# Wahoo KICKR Headwind for Home Assistant

Control a [Wahoo KICKR Headwind](https://www.wahoofitness.com/devices/indoor-cycling/accessories/kickr-headwind-buy)
smart fan from Home Assistant over Bluetooth LE: on/off, speed 0–100 %, and
the fan's own modes (manual, heart rate, speed, power, CORE temperature,
running speed, hybrid).

> **Status: working on real hardware.** Tested against a KICKR Headwind on
> firmware 2.0.43 (speed, manual/sensor modes, power off, live state). The
> protocol was extracted from the Wahoo app; see [docs/PROTOCOL.md](docs/PROTOCOL.md).

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

### Shelly Bluetooth proxies won't work

Home Assistant uses Shelly devices as **passive** Bluetooth scanners: they
relay advertisements but can't open connections. The Headwind has to be
connected to and written to, so a Shelly proxy can see the fan but can't
control it. Home Assistant's Bluetooth diagnostics show this: with only Shelly
scanners, the "connectable" device list stays empty. Shelly scripts can't open
GATT connections either.

Use one of these instead:
- an ESP32 running ESPHome with `bluetooth_proxy: active: true` near the fan
  (any cheap ESP32 board works; an existing ESPHome ESP32 near the bike can
  usually just have this added), or
- a Bluetooth adapter on the Home Assistant host, if it's in range, or
- the standalone [`esphome/headwind.yaml`](esphome/headwind.yaml).

```yaml
# Minimal ESPHome Bluetooth proxy
esp32_ble_tracker:
  scan_parameters:
    active: true
bluetooth_proxy:
  active: true
```

The fan normally accepts a single BLE connection: close the Wahoo app (or
turn off Bluetooth on that phone) while Home Assistant is connected. ANT+
(e.g. Zwift via ANT+) is unaffected.

## Install

### HACS
1. HACS → ⋮ → **Custom repositories** → add
   `https://github.com/amasolov/wahoo-headwind-ble`, type **Integration**.
2. Search for **Wahoo KICKR Headwind**, download it, then restart Home Assistant.

### Manual
Copy `custom_components/wahoo_headwind` into your `config/custom_components/`
and restart.

Then the fan should be discovered automatically (Settings → Devices &
services). If it isn't, add the integration by hand and pick it from the list.

## Entities

| Entity | Description |
| --- | --- |
| `fan.headwind_xxxx` | On/off and speed. Setting a speed switches the fan to manual mode; off uses the fan's power-off mode, like the Wahoo app. Presets: `manual`, `heart_rate`, `speed`, `power`, `core_temp`, `run_speed`, `hybrid`. |
| `select.headwind_xxxx_mode` | Mode: `off` plus the presets above. |
| `number.headwind_xxxx_manual_speed` | Speed slider, 0–100 %. Shows the current speed in every mode; setting it switches to manual, like the fan's own speed control. |
| `number.headwind_xxxx_heart_rate_zone_N_ceiling` | Upper heart rate (bpm) of zones 1–4 in heart-rate mode. They must increase from zone 1 to 4. The Wahoo app only shows zones 1 and 4 (its min and max). |

The sensor-driven modes use whatever sensors are paired to the fan in the
Wahoo app; `hybrid` also needs its sensor mix configured there.

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
