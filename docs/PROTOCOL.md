# Wahoo KICKR Headwind BLE protocol

Extracted from the Wahoo Android app (`com.wahoofitness.fitness`). The BLE
codec is in the app's native library `libCruxAndroid.so`
(`crux_codec_btle_headwind_*`, `crux_sensor_processor_headwind_v2_*`); mode
names and how the app uses them come from the decompiled Java/Kotlin
(`WFSensorViewModelDataHeadwind`). **Verified on a real Headwind** (hardware
rev 3, firmware 2.0.43); the byte captures below come from that fan.

## GATT

| What | UUID | App name |
| --- | --- | --- |
| Service | `a026ee0c-0a7d-4ab3-97fa-f1500f9feb8b` | `WAHOO_HEADWIND` (0xEE0C) |
| Control point | `a026e038-0a7d-4ab3-97fa-f1500f9feb8b` | `WAHOO_HEADWIND_CP` (0xE038) |

The control point supports **write-without-response**, notify and read. It
doesn't support write-with-response, so writes must be sent without response.

The fan advertises only its local name (`HEADWIND XXXX`), not the service
UUID. Discovery has to match on the name.

## Commands (write to the control point)

| Bytes | Meaning | App encoder |
| --- | --- | --- |
| `01` | Get speed | `encode_get_speed` |
| `02 NN` | Set speed, `NN` = 0–100 % (manual mode only) | `encode_set_speed` |
| `03` | Get mode | `encode_get_mode` |
| `04 MM` | Set mode (table below) | `encode_set_mode` |
| `05` | Get configuration | `encode_get_configuration` |
| `06 <config>` | Set configuration (layout below) | `encode_set_configuration`, `_v2` |
| `07 II` | Get one configuration item (`II` = 05: power zones) | `encode_get_specific_configuration` |
| `08 05 <8 × u16>` | Set power zone ceilings | `encode_set_pwr_zone_cfg` |

Opcodes 09–0B cover paired sensors, hybrid sensor types and an NVM reset.
This integration uses 01–06.

## Configuration

`05` is answered with `FE 05 <status> <config>`, and `06 <config>` with
`FE 06 <status> <config>`. The same layout is used both ways; multi-byte
values are little-endian:

| Bytes | Field | Units | App clamp on write |
| --- | --- | --- | --- |
| 1 each | HR zone 1–4 ceilings | bpm | none |
| 2 | Speed-sensor minimum | mm/s | ≥ 2235 (5 mph) |
| 2 | Speed-sensor maximum | mm/s | ≤ 11176 (25 mph) |
| 1 | Use skin temperature (CORE) | bool | — |
| 2 | CORE temperature minimum | 0.01 °C | ≥ 3690 |
| 2 | CORE temperature maximum | 0.01 °C | ≤ 3834 |
| 2 | Run speed minimum | mm/s | ≥ 1072 |
| 2 | Run speed maximum | mm/s | ≤ 4876 |

The last five fields exist only on firmware where the app reports
`supports_skin_temp_and_run_speed`; its decoder reads them only when 9 more
bytes follow the speed range, and writes them with
`encode_set_configuration_v2` (18 bytes) instead of the 9-byte v1 command.
There is no command to change one field, so the integration writes back the
configuration the fan last reported with only the HR ceilings changed. Every
byte after the ceilings goes back verbatim, whichever layout the fan uses.

The four HR ceilings are the zone boundaries the fan's heart-rate mode uses
(`CONFIG_HR_CEILING_1`…`4` in the app's native strings). The app's UI only
sets zone 1 (`sendSetHrCeiling1`) and zone 4 (`sendSetHrCeiling4`); zones 2
and 3 are stored on the fan and can be set with the same command.

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
| `FE 01 ST SS` | Get-speed response (`ST` = status, `01` = OK) |
| `FE 02 ST SS` | Set-speed acknowledgement |
| `FE 03 ST MM` | Get-mode response |
| `FE 04 ST MM` | Set-mode acknowledgement |
| `FE 05`–`FE 0B …` | Configuration / paired-sensor / hybrid responses |

The fan also repeats `FD 01` every second or so while connected, and sends
`FD 02` (paired sensors) after mode changes. Reading the characteristic
returns the last event.

The integration takes its state from `FD 01` events and from `FE` responses
with status `01`. After connecting it sends `01` and `03` so it knows the state
straight away.

## Captured session

```
-> 01          <- fe 01 01 00                 speed 0
-> 03          <- fe 03 01 02                 mode HEARTRATE
-> 04 04       <- fe 04 01 04, fd 01 19 04    manual, resumes last manual speed (25 %)
-> 02 1e       <- fe 02 01 1e, fd 01 1e 04    30 %
-> 04 01       <- fe 04 01 01, fd 01 00 01    POWER_OFF
-> 04 02       <- fe 04 01 02, fd 02 01 01 00 02 ff 04 ff 08 00 10, fd 01 00 02
```

## Checking against a real fan

```bash
python tools/headwind_probe.py scan                 # find the fan
python tools/headwind_probe.py monitor <address>    # watch notifications
python tools/headwind_probe.py send <address> 03    # expect FE 03 01 <mode>
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
