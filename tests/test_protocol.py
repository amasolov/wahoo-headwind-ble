"""Tests for the pure protocol helpers."""

from custom_components.wahoo_headwind.protocol import (
    HeadwindMode,
    parse_notification,
    set_mode_command,
    set_speed_command,
)


def test_set_speed_command_clamps() -> None:
    assert set_speed_command(42) == b"\x02\x2a"
    assert set_speed_command(-5) == b"\x02\x00"
    assert set_speed_command(150) == b"\x02\x64"


def test_set_mode_command() -> None:
    assert set_mode_command(HeadwindMode.MANUAL) == b"\x04\x04"
    assert set_mode_command(HeadwindMode.HEART_RATE) == b"\x04\x01"


def test_parse_notification() -> None:
    state = parse_notification(bytes.fromhex("fd 01 00 04 37 00"))
    assert state is not None
    assert state.mode is HeadwindMode.MANUAL
    assert state.speed == 0x37


def test_parse_notification_unknown_mode_and_junk() -> None:
    state = parse_notification(bytes.fromhex("fd 01 00 09 10"))
    assert state is not None and state.mode is None and state.speed == 0x10
    assert parse_notification(b"\x01\x02\x03\x04\x05") is None
    assert parse_notification(b"\xfd\x01") is None
