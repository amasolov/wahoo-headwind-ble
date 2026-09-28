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


@dataclass(frozen=True, slots=True)
class HeadwindUpdate:
    """State carried by a notification; fields the packet doesn't carry are None."""

    speed: int | None = None
    mode: HeadwindMode | None = None


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

    Verified against a Headwind on firmware 2.0.43.
    """
    data = bytes(data)
    if len(data) >= 4 and data[0] == PACKET_EVENT and data[1] == EVENT_STATE:
        return HeadwindUpdate(speed=min(100, data[2]), mode=_mode(data[3]))
    if len(data) >= 4 and data[0] == PACKET_RESPONSE and data[2] == STATUS_OK:
        if data[1] in (OPCODE_GET_SPEED, OPCODE_SET_SPEED):
            return HeadwindUpdate(speed=min(100, data[3]))
        if data[1] in (OPCODE_GET_MODE, OPCODE_SET_MODE):
            return HeadwindUpdate(mode=_mode(data[3]))
    return None
