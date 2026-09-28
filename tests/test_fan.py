"""Tests for setup, the fan entity and the mode select."""

from unittest.mock import patch

import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_ADDRESS,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

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


async def test_state_from_notifications(hass: HomeAssistant, setup_entry) -> None:
    _, client = setup_entry
    client.notify(bytes.fromhex("fd 01 00 04 3c 00"))
    await hass.async_block_till_done()
    state = hass.states.get(FAN)
    assert state.state == STATE_ON
    assert state.attributes["percentage"] == 60
    assert state.attributes["preset_mode"] == "manual"
    assert hass.states.get(MODE).state == "manual"

    client.notify(bytes.fromhex("fd 01 00 03 00 00"))
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == STATE_OFF
    assert hass.states.get(MODE).state == "sleep"


async def test_set_percentage_switches_to_manual(hass: HomeAssistant, setup_entry) -> None:
    _, client = setup_entry
    await hass.services.async_call(
        "fan", "set_percentage", {ATTR_ENTITY_ID: FAN, "percentage": 75}, blocking=True
    )
    assert client.writes == [b"\x04\x04", b"\x02\x4b"]
    assert hass.states.get(FAN).attributes["percentage"] == 75

    # Already manual: only the speed is written.
    client.writes.clear()
    await hass.services.async_call("fan", "turn_off", {ATTR_ENTITY_ID: FAN}, blocking=True)
    assert client.writes == [b"\x02\x00"]
    assert hass.states.get(FAN).state == STATE_OFF

    # Turning back on restores the previous speed.
    client.writes.clear()
    await hass.services.async_call("fan", "turn_on", {ATTR_ENTITY_ID: FAN}, blocking=True)
    assert client.writes == [b"\x02\x4b"]


async def test_preset_and_select(hass: HomeAssistant, setup_entry) -> None:
    _, client = setup_entry
    await hass.services.async_call(
        "fan", "set_preset_mode", {ATTR_ENTITY_ID: FAN, "preset_mode": "heart_rate"}, blocking=True
    )
    assert client.writes == [b"\x04\x01"]
    assert hass.states.get(FAN).state == STATE_ON

    client.writes.clear()
    await hass.services.async_call(
        "select", "select_option", {ATTR_ENTITY_ID: MODE, "option": "sleep"}, blocking=True
    )
    assert client.writes == [b"\x04\x03"]
    assert hass.states.get(FAN).state == STATE_OFF


async def test_disconnect_marks_unavailable_and_unload(hass: HomeAssistant, setup_entry) -> None:
    entry, client = setup_entry
    with patch("custom_components.wahoo_headwind.device.RECONNECT_DELAY", 3600):
        client.drop()
        await hass.async_block_till_done()
        assert hass.states.get(FAN).state == STATE_UNAVAILABLE
        assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
