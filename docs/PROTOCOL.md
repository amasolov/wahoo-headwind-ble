# Wahoo KICKR Headwind BLE protocol

The Headwind is a BLE peripheral (it also speaks ANT+, which isn't covered
here). Besides the standard Device Information / Battery-style services it
exposes one Wahoo proprietary service:

| What | UUID |
| --- | --- |
| Headwind service | `a026ee0c-0a7d-4ab3-97fa-f1500f9feb8b` |
| Control / status characteristic (write + notify) | `a026e038-0a7d-4ab3-97fa-f1500f9feb8b` |

All Wahoo proprietary UUIDs share the `a026xxxx-0a7d-4ab3-97fa-f1500f9feb8b`
base (the KICKR trainer control point is `a026e005-…`).

The fan advertises with a local name starting with `HEADWIND`.

## Commands (write to `a026e038`)

| Bytes | Meaning |
| --- | --- |
| `04 01` | Heart-rate mode (speed follows a paired HR strap) |
| `04 02` | Speed mode (speed follows a paired speed sensor / trainer) |
| `04 03` | Sleep (fan off, stays connectable) |
| `04 04` | Manual mode |
| `02 NN` | Manual-mode fan speed, `NN` = 0–100 (percent) |

`02 NN` is only honoured in manual mode, so the integration always sends
`04 04` first when it isn't already in manual mode.

## Notifications (from `a026e038`)

State updates start with `FD 01`:

```
FD 01 ?? MM SS ...
         |  +-- current fan speed, percent
         +----- mode (01 HR, 02 speed, 03 sleep, 04 manual)
```

## Verification status

**This protocol has not yet been checked against the Wahoo app or a real fan
in this repo.** It is based on community reverse-engineering of the Headwind
(ESPHome / DIY controller projects). The APK could not be decompiled here
because the build environment had no access to APK mirrors. In order of
confidence:

1. Service/characteristic UUIDs and `02 NN` speed command: widely used by
   DIY controllers; high confidence.
2. `04 04` manual mode: commonly used together with `02 NN`; high confidence.
3. The other mode values (`01`, `02`, `03`): medium confidence.
4. Notification layout (`FD 01 ?? MM SS`): lowest confidence. If it's wrong
   the fan still works, the integration just keeps its own (optimistic)
   state. Raw notifications are logged at debug level.

All of it lives in
[`custom_components/wahoo_headwind/protocol.py`](../custom_components/wahoo_headwind/protocol.py),
so a correction is a one-file change.

### How to verify

**Against a real fan** (laptop / Raspberry Pi with Bluetooth, `pip install bleak`,
Wahoo app closed):

```bash
python tools/headwind_probe.py scan                 # find the address
python tools/headwind_probe.py dump    <address>    # list services/characteristics
python tools/headwind_probe.py monitor <address>    # print raw notifications
python tools/headwind_probe.py send    <address> 04 04
python tools/headwind_probe.py send    <address> 02 32
```

While `monitor` runs, press the buttons on the fan and note which bytes
change.

**Against the Wahoo app:**

```bash
adb shell pm path com.wahoofitness.fitness   # or download the APK from a mirror
adb pull <path>/base.apk wahoo.apk
tools/decompile_wahoo_apk.sh wahoo.apk
```

The script decompiles with jadx and greps for the UUIDs and Headwind classes;
the packet builder and parser classes it points to contain the authoritative
opcodes. Alternatively, enable *Bluetooth HCI snoop log* in Android developer
options, control the fan from the Wahoo app, and open the log in Wireshark
(filter `btatt`).
