"""Wahoo KICKR Headwind BLE protocol (pure Python, no Home Assistant imports).

Derived from the Wahoo Android app: the BLE codec lives in its native
``libCruxAndroid.so`` (``crux_codec_btle_headwind_*``) and the mode names in
the app's Headwind view model. Checked against a real fan (firmware 2.0.43).
See docs/PROTOCOL.md for details.

The fan exposes one proprietary service with a single control point
characteristic (write-without-response, notify, read). Commands are
``<opcode> [arg]``; the fan answers on the same characteristic with
``FE <opcode> <status> <value>`` responses and pushes ``FD <event> ...``
events when its state changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

SERVICE_UUID = "a026ee0c-0a7d-4ab3-97fa-f1500f9feb8b"
CONTROL_CHAR_UUID = "a026e038-0a7d-4ab3-97fa-f1500f9feb8b"

LOCAL_NAME_PREFIX = "HEADWIND"

OPCODE_GET_SPEED = 0x01
OPCODE_SET_SPEED = 0x02
OPCODE_GET_MODE = 0x03
OPCODE_SET_MODE = 0x04
OPCODE_GET_CONFIG = 0x05
OPCODE_SET_CONFIG = 0x06

PACKET_EVENT = 0xFD
PACKET_RESPONSE = 0xFE

EVENT_STATE = 0x01

STATUS_OK = 0x01


class HeadwindMode(IntEnum):
    """Fan modes, named as in the Wahoo app."""

    ERROR = 0
    POWER_OFF = 1
    HEART_RATE = 2
    SPEED = 3
    MANUAL = 4  # "DIRECT" in the app
    STANDBY = 5
    CORE_TEMP = 6
    RUN_SPEED = 7
    POWER = 8
    HYBRID = 9


# Modes in which the fan isn't blowing, as grouped by the Wahoo app.
OFF_MODES = frozenset({HeadwindMode.ERROR, HeadwindMode.POWER_OFF, HeadwindMode.STANDBY})


def get_speed_command() -> bytes:
    return bytes((OPCODE_GET_SPEED,))


def get_mode_command() -> bytes:
    return bytes((OPCODE_GET_MODE,))


def set_mode_command(mode: HeadwindMode) -> bytes:
    """Build the command that switches the fan to ``mode``."""
    return bytes((OPCODE_SET_MODE, int(mode)))


def set_speed_command(percentage: int) -> bytes:
    """Build the command that sets the fan speed (0-100 %).

    Only honoured in manual mode.
    """
    return bytes((OPCODE_SET_SPEED, max(0, min(100, int(percentage)))))


def get_config_command() -> bytes:
    return bytes((OPCODE_GET_CONFIG,))


def set_config_command(config: HeadwindConfig) -> bytes:
    """Build the command that stores ``config`` on the fan.

    The fan takes the whole configuration at once; there is no command for a
    single heart-rate ceiling. Callers should start from the config the fan
    last reported and change only what they mean to.
    """
    ceilings = (max(0, min(255, int(bpm))) for bpm in config.hr_zone_ceilings)
    return bytes((OPCODE_SET_CONFIG, *ceilings)) + config.tail


HR_ZONE_COUNT = 4


@dataclass(frozen=True, slots=True)
class HeadwindConfig:
    """The fan's stored configuration, as returned by get-configuration.

    Wire layout after the ``FE 05 <status>`` header (and after the ``06``
    opcode when writing it back), from the app's
    ``crux_codec_btle_headwind_{decode_packet,encode_set_configuration*}``:

    ``H1 H2 H3 H4``   heart-rate zone ceilings, bpm (u8 each)
    ``Smin Smax``     speed-sensor range, mm/s (u16 LE each)
    then, on firmware that supports it (``encode_set_configuration_v2``):
    ``K Cmin Cmax Rmin Rmax``  skin-temp flag (u8), CORE temperature range
                               (u16, 0.01 degC) and run-speed range (u16, mm/s)

    Only the heart-rate ceilings are interpreted. Everything after them is
    kept as raw bytes and written back unchanged, so changing a ceiling can
    never alter settings this integration doesn't manage, whichever of the
    two layouts the fan uses.
    """

    hr_zone_ceilings: tuple[int, int, int, int]
    tail: bytes

    @property
    def sensor_speed_range_mms(self) -> tuple[int, int] | None:
        """Speed-sensor min/max, for diagnostics."""
        if len(self.tail) < 4:
            return None
        return (
            int.from_bytes(self.tail[0:2], "little"),
            int.from_bytes(self.tail[2:4], "little"),
        )


@dataclass(frozen=True, slots=True)
class HeadwindUpdate:
    """State carried by a notification; fields the packet doesn't carry are None."""

    speed: int | None = None
    mode: HeadwindMode | None = None
    config: HeadwindConfig | None = None


def _mode(value: int) -> HeadwindMode | None:
    try:
        return HeadwindMode(value)
    except ValueError:
        return None


def parse_notification(data: bytes | bytearray) -> HeadwindUpdate | None:
    """Decode a notification into a state update, or None if it carries no state.

    ``FD 01 SS MM``      state event: speed %, mode
    ``FE OP ST VV``      response to opcode OP with status ST (01 = OK) and
                         value VV: speed for 01/02, mode for 03/04
    ``FE 05 ST <config>`` get-configuration response; the app decodes the
                         set-configuration acknowledgement (``FE 06``) the
                         same way. See HeadwindConfig for the layout.

    Speed and mode verified against a Headwind on firmware 2.0.43.
    """
    data = bytes(data)
    if len(data) >= 4 and data[0] == PACKET_EVENT and data[1] == EVENT_STATE:
        return HeadwindUpdate(speed=min(100, data[2]), mode=_mode(data[3]))
    if len(data) >= 4 and data[0] == PACKET_RESPONSE and data[2] == STATUS_OK:
        if data[1] in (OPCODE_GET_SPEED, OPCODE_SET_SPEED):
            return HeadwindUpdate(speed=min(100, data[3]))
        if data[1] in (OPCODE_GET_MODE, OPCODE_SET_MODE):
            return HeadwindUpdate(mode=_mode(data[3]))
        # 4 ceilings + 2 speed u16s is the shortest config the app accepts.
        if data[1] in (OPCODE_GET_CONFIG, OPCODE_SET_CONFIG) and len(data) >= 11:
            return HeadwindUpdate(
                config=HeadwindConfig(
                    hr_zone_ceilings=(data[3], data[4], data[5], data[6]),
                    tail=data[7:],
                )
            )
    return None
