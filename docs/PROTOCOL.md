# Wahoo KICKR Headwind BLE protocol

Extracted from the Wahoo Android app (`com.wahoofitness.fitness`). The BLE
codec is in the app's native library `libCruxAndroid.so`
(`crux_codec_btle_headwind_*`, `crux_sensor_processor_headwind_v2_*`); mode
names and how the app uses them come from the decompiled Java/Kotlin
(`WFSensorViewModelDataHeadwind`). Not yet checked against a real fan, but
the command encoders, the decoder and the mode enum were all read directly
from the app.

## GATT

| What | UUID | App name |
| --- | --- | --- |
| Service | `a026ee0c-0a7d-4ab3-97fa-f1500f9feb8b` | `WAHOO_HEADWIND` (0xEE0C) |
| Control point (write + notify) | `a026e038-0a7d-4ab3-97fa-f1500f9feb8b` | `WAHOO_HEADWIND_CP` (0xE038) |

The fan advertises with a local name starting with `HEADWIND`.

## Commands (write to the control point)

| Bytes | Meaning | App encoder |
| --- | --- | --- |
| `01` | Get speed | `encode_get_speed` |
| `02 NN` | Set speed, `NN` = 0–100 % (manual mode only) | `encode_set_speed` |
| `03` | Get mode | `encode_get_mode` |
| `04 MM` | Set mode (table below) | `encode_set_mode` |

The codec also has opcodes 05–0B for configuration (HR/power zone ceilings,
fan min/max, core-temp range), paired sensors, hybrid sensor types and an NVM
reset. This integration doesn't use them.

## Modes

From the app's mode-to-name function:

| Value | App name | Notes |
| --- | --- | --- |
| 0 | `ERROR` | |
| 1 | `POWER_OFF` | What the app's **Off** button writes |
| 2 | `HEARTRATE` | Speed follows a paired HR strap |
| 3 | `SPEED` | Follows a paired bike speed sensor / trainer |
| 4 | `DIRECT` | Manual; what the app's **Manual** button writes |
| 5 | `STANDBY` | The app shows this as Off |
| 6 | `CORE_TEMP` | CORE body temperature sensor |
| 7 | `RUN_SPEED` | Running speed sensor |
| 8 | `POWER` | Power zones |
| 9 | `HYBRID` | Several sensors combined (configured separately) |

When you pick **Sensor** in the app, it writes the mode that matches the
paired sensor type (HR → 2, bike speed → 3, core temp → 6, run speed → 7,
power → 8). It writes 9 when more than one sensor is paired, and falls back
to 2.

## Notifications (from the control point)

Byte 0 is the packet type:

**`FD` – event** (unsolicited):

| Bytes | Meaning |
| --- | --- |
| `FD 01 SS MM` | State: speed `SS` % and mode `MM` |
| `FD 02 …` | Paired-sensor slots (5 × type/state pairs); not used here |

**`FE` – response** to a command:

| Bytes | Meaning |
| --- | --- |
| `FE 01 SS` | Get-speed response |
| `FE 02 ST SS` | Set-speed acknowledgement (`ST` = status) |
| `FE 03 MM` | Get-mode response |
| `FE 04 ST MM` | Set-mode acknowledgement |
| `FE 05`–`FE 0B …` | Configuration / paired-sensor / hybrid responses |

The integration takes its state from `FD 01` events and the `FE 01` / `FE 03`
responses. After connecting it sends `01` and `03` so it knows the state
straight away.

## Checking against a real fan

```bash
python tools/headwind_probe.py scan                 # find the fan
python tools/headwind_probe.py monitor <address>    # watch notifications
python tools/headwind_probe.py send <address> 03    # expect FE 03 <mode>
python tools/headwind_probe.py send <address> 04 04 # manual
python tools/headwind_probe.py send <address> 02 32 # 50 % -> expect FD 01 32 04
```

Close the Wahoo app first; the fan usually allows only one BLE connection.
On macOS, bleak shows CoreBluetooth UUIDs instead of MAC addresses; use the
address that `scan` prints.

## Reproducing the extraction

```bash
apkeep -a com.wahoofitness.fitness -d apk-pure .     # or adb pull from a phone
unzip com.wahoofitness.fitness.xapk -d x
unzip x/config.armeabi_v7a.apk 'lib/*' -d so
objdump -T so/lib/armeabi-v7a/libCruxAndroid.so | grep crux_codec_btle_headwind
objdump -d --triple=thumbv7-linux-androideabi \
  --start-address=0x3952a4 --stop-address=0x39538c \
  so/lib/armeabi-v7a/libCruxAndroid.so               # encode_set_speed
```

Addresses are for the app version downloaded on 2026-09-28. For the mode
names, decompile `cw.j` with jadx (`jadx --single-class cw.j`); the class
names are obfuscated and will change between app versions.
`tools/decompile_wahoo_apk.sh` automates the Java side.
