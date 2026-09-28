"""Wahoo KICKR Headwind BLE protocol (pure Python, no Home Assistant imports).

The Headwind exposes a Wahoo proprietary GATT service with a single
write/notify characteristic. Commands are short byte strings; the first byte
is an opcode.

Everything here is kept in one module so that it can be verified (and fixed)
in one place - see docs/PROTOCOL.md for which parts are confirmed and how to
verify the rest against the Wahoo app or a real fan.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

SERVICE_UUID = "a026ee0c-0a7d-4ab3-97fa-f1500f9feb8b"
CONTROL_CHAR_UUID = "a026e038-0a7d-4ab3-97fa-f1500f9feb8b"

LOCAL_NAME_PREFIX = "HEADWIND"

OPCODE_SET_SPEED = 0x02
OPCODE_SET_MODE = 0x04

# Notifications with this header carry the fan state.
STATE_HEADER = bytes((0xFD, 0x01))


class HeadwindMode(IntEnum):
    """Operating modes selectable from the Wahoo app / fan buttons."""

    HEART_RATE = 0x01
    SPEED = 0x02
    SLEEP = 0x03
    MANUAL = 0x04


def set_mode_command(mode: HeadwindMode) -> bytes:
    """Build the command that switches the fan to ``mode``."""
    return bytes((OPCODE_SET_MODE, int(mode)))


def set_speed_command(percentage: int) -> bytes:
    """Build the command that sets the manual-mode fan speed (0-100 %).

    The fan must be in manual mode for this to take effect.
    """
    return bytes((OPCODE_SET_SPEED, max(0, min(100, int(percentage)))))


@dataclass(frozen=True, slots=True)
class HeadwindState:
    """State decoded from a status notification."""

    mode: HeadwindMode | None
    speed: int
    raw: bytes


def parse_notification(data: bytes | bytearray) -> HeadwindState | None:
    """Decode a status notification, or return None if it is not one.

    Layout (``FD 01 ?? MM SS ...``): byte 3 is the mode, byte 4 the current
    fan speed in percent.
    """
    data = bytes(data)
    if len(data) < 5 or not data.startswith(STATE_HEADER):
        return None
    try:
        mode: HeadwindMode | None = HeadwindMode(data[3])
    except ValueError:
        mode = None
    return HeadwindState(mode=mode, speed=min(100, data[4]), raw=data)
