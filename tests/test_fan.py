"""Tests for setup, the fan entity and the mode select."""

import asyncio
from datetime import timedelta
from unittest.mock import patch

import pytest

from homeassistant.components.bluetooth import async_get_advertisement_callback
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_ADDRESS,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.wahoo_headwind.const import DOMAIN

from .conftest import ADDRESS, NAME, make_service_info

FAN = "fan.headwind_1234"
MODE = "select.headwind_1234_mode"


@pytest.fixture
async def setup_entry(hass: HomeAssistant, mock_bluetooth: None, fake_client):
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=ADDRESS, title=NAME, data={CONF_ADDRESS: ADDRESS}
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.wahoo_headwind.bluetooth.async_ble_device_from_address",
        return_value=make_service_info().device,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry, fake_client.holder["client"]


async def test_setup_not_found(hass: HomeAssistant, mock_bluetooth: None) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDRESS, data={CONF_ADDRESS: ADDRESS})
    entry.add_to_hass(hass)
    with patch(
        "custom_components.wahoo_headwind.bluetooth.async_ble_device_from_address",
        return_value=None,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_queries_state_on_connect(hass: HomeAssistant, setup_entry) -> None:
    _, client = setup_entry
    assert client.writes == [b"\x01", b"\x03", b"\x05"]
    client.notify(bytes.fromhex("fe 01 01 3c"))
    client.notify(bytes.fromhex("fe 03 01 04"))
    await hass.async_block_till_done()
    state = hass.states.get(FAN)
    assert state.state == STATE_ON
    assert state.attributes["percentage"] == 60
    assert hass.states.get(MODE).state == "manual"


async def test_state_from_notifications(hass: HomeAssistant, setup_entry) -> None:
    _, client = setup_entry
    client.notify(bytes.fromhex("fd 01 3c 04"))
    await hass.async_block_till_done()
    state = hass.states.get(FAN)
    assert state.state == STATE_ON
    assert state.attributes["percentage"] == 60
    assert state.attributes["preset_mode"] == "manual"
    assert hass.states.get(MODE).state == "manual"

    client.notify(bytes.fromhex("fd 01 00 01"))
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == STATE_OFF
    assert hass.states.get(MODE).state == "off"

    # Standby is shown as off too.
    client.notify(bytes.fromhex("fd 01 00 05"))
    await hass.async_block_till_done()
    assert hass.states.get(MODE).state == "off"

    # Sensor modes count as on even while the fan is at 0 %.
    client.notify(bytes.fromhex("fd 01 00 02"))
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == STATE_ON
    assert hass.states.get(FAN).attributes["preset_mode"] == "heart_rate"


async def test_set_percentage_switches_to_manual(hass: HomeAssistant, setup_entry) -> None:
    _, client = setup_entry
    client.writes.clear()
    await hass.services.async_call(
        "fan", "set_percentage", {ATTR_ENTITY_ID: FAN, "percentage": 75}, blocking=True
    )
    assert client.writes == [b"\x04\x04", b"\x02\x4b"]
    assert hass.states.get(FAN).attributes["percentage"] == 75

    # Already manual: only the speed is written.
    client.writes.clear()
    await hass.services.async_call(
        "fan", "set_percentage", {ATTR_ENTITY_ID: FAN, "percentage": 30}, blocking=True
    )
    assert client.writes == [b"\x02\x1e"]

    # Off uses the app's POWER_OFF mode.
    client.writes.clear()
    await hass.services.async_call("fan", "turn_off", {ATTR_ENTITY_ID: FAN}, blocking=True)
    assert client.writes == [b"\x04\x01"]
    assert hass.states.get(FAN).state == STATE_OFF

    # Turning back on returns to manual at the previous speed.
    client.writes.clear()
    await hass.services.async_call("fan", "turn_on", {ATTR_ENTITY_ID: FAN}, blocking=True)
    assert client.writes == [b"\x04\x04", b"\x02\x1e"]


async def test_preset_and_select(hass: HomeAssistant, setup_entry) -> None:
    _, client = setup_entry
    client.writes.clear()
    await hass.services.async_call(
        "fan", "set_preset_mode", {ATTR_ENTITY_ID: FAN, "preset_mode": "heart_rate"}, blocking=True
    )
    assert client.writes == [b"\x04\x02"]
    assert hass.states.get(FAN).state == STATE_ON

    client.writes.clear()
    await hass.services.async_call(
        "select", "select_option", {ATTR_ENTITY_ID: MODE, "option": "power"}, blocking=True
    )
    assert client.writes == [b"\x04\x08"]
    assert hass.states.get(FAN).attributes["preset_mode"] == "power"

    client.writes.clear()
    await hass.services.async_call(
        "select", "select_option", {ATTR_ENTITY_ID: MODE, "option": "off"}, blocking=True
    )
    assert client.writes == [b"\x04\x01"]
    assert hass.states.get(FAN).state == STATE_OFF


async def test_disconnect_marks_unavailable_and_unload(hass: HomeAssistant, setup_entry) -> None:
    entry, client = setup_entry
    with patch("custom_components.wahoo_headwind.device.RECONNECT_DELAY", 3600):
        client.drop()
        await hass.async_block_till_done()
        assert hass.states.get(FAN).state == STATE_UNAVAILABLE
        assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED



async def test_reconnects_when_the_fan_advertises(
    hass: HomeAssistant, setup_entry, fake_client
) -> None:
    """A dropped fan is retried on its next advertisement, not on a timer.

    Between rides the fan's plug is off for days; blind retries would hold a
    Bluetooth proxy slot the whole time.
    """
    _, client = setup_entry
    attempts = fake_client.call_count
    with patch("custom_components.wahoo_headwind.device.RECONNECT_DELAY", 0):
        client.drop()
        await hass.async_block_till_done()
        assert hass.states.get(FAN).state == STATE_UNAVAILABLE

        # Silence (fan unpowered): nothing is attempted.
        for _ in range(10):
            await asyncio.sleep(0)
        assert fake_client.call_count == attempts

        # The fan powers up and advertises: reconnect straight away.
        async_get_advertisement_callback(hass)(make_service_info())
        await hass.async_block_till_done()
    assert fake_client.call_count == attempts + 1
    assert hass.states.get(FAN).state != STATE_UNAVAILABLE


# Advertisement timestamps are compared with the moment the fan disconnected.
# Pin that moment so the tests don't race the clock: on Linux HA's coarse
# clock ticks every few ms, so "just before" and "just after" a disconnect
# can land in the same tick.
DROPPED_AT = 1000.0


async def test_reconnects_after_a_short_power_cut(
    hass: HomeAssistant, setup_entry, fake_client
) -> None:
    """The fan comes back advertising exactly what HA already has on record.

    HA skips callbacks for such a duplicate, so only the history check can
    notice it. On a real fan this left it disconnected after the plug was
    switched off and on again.
    """
    _, client = setup_entry
    advertise = async_get_advertisement_callback(hass)
    advertise(make_service_info(seen_at=DROPPED_AT - 60))  # before the cut
    await hass.async_block_till_done()
    attempts = fake_client.call_count

    with (
        patch("custom_components.wahoo_headwind.device.RECONNECT_DELAY", 0),
        patch(
            "custom_components.wahoo_headwind.device.monotonic_time_coarse",
            return_value=DROPPED_AT,
        ),
    ):
        client.drop()
        await hass.async_block_till_done()
        advertise(make_service_info(seen_at=DROPPED_AT + 2))  # same data, after
        await hass.async_block_till_done()
        assert fake_client.call_count == attempts  # HA suppressed the callback

        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=6))
        await hass.async_block_till_done()
    assert fake_client.call_count == attempts + 1
    assert hass.states.get(FAN).state != STATE_UNAVAILABLE


async def test_history_check_ignores_advertisements_from_before_the_drop(
    hass: HomeAssistant, setup_entry, fake_client
) -> None:
    """An old advertisement says nothing about whether the fan still has power."""
    _, client = setup_entry
    async_get_advertisement_callback(hass)(make_service_info(seen_at=DROPPED_AT - 60))
    await hass.async_block_till_done()
    attempts = fake_client.call_count

    with patch(
        "custom_components.wahoo_headwind.device.monotonic_time_coarse",
        return_value=DROPPED_AT,
    ):
        client.drop()
        await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=6))
    await hass.async_block_till_done()
    assert fake_client.call_count == attempts
    assert hass.states.get(FAN).state == STATE_UNAVAILABLE
