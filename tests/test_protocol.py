"""Tests for the pure protocol helpers."""

from custom_components.wahoo_headwind.protocol import (
    HeadwindMode,
    HeadwindUpdate,
    get_mode_command,
    get_speed_command,
    parse_notification,
    set_mode_command,
    set_speed_command,
)


def test_commands() -> None:
    assert get_speed_command() == b"\x01"
    assert get_mode_command() == b"\x03"
    assert set_mode_command(HeadwindMode.MANUAL) == b"\x04\x04"
    assert set_mode_command(HeadwindMode.POWER_OFF) == b"\x04\x01"
    assert set_mode_command(HeadwindMode.HEART_RATE) == b"\x04\x02"


def test_set_speed_command_clamps() -> None:
    assert set_speed_command(42) == b"\x02\x2a"
    assert set_speed_command(-5) == b"\x02\x00"
    assert set_speed_command(150) == b"\x02\x64"


def test_parse_state_event() -> None:
    assert parse_notification(bytes.fromhex("fd 01 37 04")) == HeadwindUpdate(
        speed=0x37, mode=HeadwindMode.MANUAL
    )
    # Unknown mode values keep the speed but drop the mode.
    assert parse_notification(bytes.fromhex("fd 01 10 63")) == HeadwindUpdate(speed=0x10)


def test_parse_responses() -> None:
    # Captured from a real Headwind (firmware 2.0.43).
    assert parse_notification(bytes.fromhex("fe 01 01 00")) == HeadwindUpdate(speed=0)
    assert parse_notification(bytes.fromhex("fe 03 01 02")) == HeadwindUpdate(
        mode=HeadwindMode.HEART_RATE
    )
    assert parse_notification(bytes.fromhex("fe 02 01 1e")) == HeadwindUpdate(speed=30)
    assert parse_notification(bytes.fromhex("fe 04 01 04")) == HeadwindUpdate(
        mode=HeadwindMode.MANUAL
    )


def test_parse_ignored_packets() -> None:
    assert parse_notification(bytes.fromhex("fe 02 00 1e")) is None  # failed status
    # Paired-sensor event, as read from a real fan.
    assert parse_notification(bytes.fromhex("fd 02 01 01 00 02 ff 04 ff 08 00 10")) is None
    assert parse_notification(b"\x01\x02\x03\x04") is None
    assert parse_notification(b"\xfd\x01\x10") is None
    assert parse_notification(b"\xfe\x01\x01") is None
