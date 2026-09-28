"""Tests for the pure protocol helpers."""

from custom_components.wahoo_headwind.protocol import (
    HeadwindConfig,
    HeadwindMode,
    HeadwindUpdate,
    get_config_command,
    get_mode_command,
    get_speed_command,
    parse_notification,
    set_config_command,
    set_mode_command,
    set_speed_command,
)

# Config responses built from the layout in the app's decoder: 4 HR ceilings,
# speed-sensor min/max (u16 LE, mm/s), then on newer firmware the skin-temp
# flag, CORE temp min/max (0.01 degC) and run-speed min/max (mm/s).
CONFIG_V1 = bytes.fromhex("fe 05 01 64 78 8c a0 bb 08 a8 2b")
CONFIG_V2 = CONFIG_V1 + bytes.fromhex("00 6a 0e fa 0e 30 04 0c 13")


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


def test_get_config_command() -> None:
    assert get_config_command() == b"\x05"


def test_parse_config_v1() -> None:
    update = parse_notification(CONFIG_V1)
    assert update == HeadwindUpdate(
        config=HeadwindConfig(
            hr_zone_ceilings=(100, 120, 140, 160), tail=bytes.fromhex("bb 08 a8 2b")
        )
    )
    # The app's clamp limits, 5 and 25 mph.
    assert update.config.sensor_speed_range_mms == (2235, 11176)


def test_parse_config_v2_keeps_the_extended_tail() -> None:
    update = parse_notification(CONFIG_V2)
    assert update.config.hr_zone_ceilings == (100, 120, 140, 160)
    assert update.config.tail == CONFIG_V2[7:]


def test_parse_config_ack_and_failures() -> None:
    # The set-configuration ack carries the stored config the same way.
    ack = bytes((0xFE, 0x06)) + CONFIG_V1[2:]
    assert parse_notification(ack).config.hr_zone_ceilings == (100, 120, 140, 160)
    assert parse_notification(bytes.fromhex("fe 05 02") + CONFIG_V1[3:]) is None
    assert parse_notification(CONFIG_V1[:10]) is None  # truncated


def test_set_config_round_trips_every_other_byte() -> None:
    """Only the ceilings change; whatever else the fan stored goes back as-is."""
    for packet in (CONFIG_V1, CONFIG_V2):
        config = parse_notification(packet).config
        assert set_config_command(config) == b"\x06" + packet[3:]
        changed = HeadwindConfig(hr_zone_ceilings=(90, 120, 140, 175), tail=config.tail)
        assert set_config_command(changed) == bytes((0x06, 90, 120, 140, 175)) + packet[7:]
