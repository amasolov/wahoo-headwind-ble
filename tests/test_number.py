"""Tests for the manual speed slider and heart rate zone numbers."""

from unittest.mock import patch

import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, CONF_ADDRESS, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wahoo_headwind.const import DOMAIN

from .conftest import ADDRESS, NAME, make_service_info

SPEED = "number.headwind_1234_manual_speed"
ZONE = "number.headwind_1234_heart_rate_zone_{}_ceiling"
CONFIG = bytes.fromhex("fe 05 01 64 78 8c a0 bb 08 a8 2b")


@pytest.fixture
async def client(hass: HomeAssistant, mock_bluetooth: None, fake_client):
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
    return fake_client.holder["client"]


async def _set(hass: HomeAssistant, entity_id: str, value: float) -> None:
    await hass.services.async_call(
        "number", "set_value", {ATTR_ENTITY_ID: entity_id, "value": value}, blocking=True
    )


async def test_manual_speed(hass: HomeAssistant, client) -> None:
    # Follows the fan's reported speed, whatever the mode.
    client.notify(bytes.fromhex("fd 01 2d 02"))
    await hass.async_block_till_done()
    assert hass.states.get(SPEED).state == "45"

    client.writes.clear()
    await _set(hass, SPEED, 70)
    assert client.writes == [b"\x04\x04", b"\x02\x46"]
    assert hass.states.get(SPEED).state == "70"
    assert hass.states.get("fan.headwind_1234").attributes["preset_mode"] == "manual"


async def test_hr_zones_unavailable_until_config_read(hass: HomeAssistant, client) -> None:
    assert hass.states.get(ZONE.format(1)).state == STATE_UNAVAILABLE
    client.notify(CONFIG)
    await hass.async_block_till_done()
    assert [hass.states.get(ZONE.format(z)).state for z in range(1, 5)] == [
        "100",
        "120",
        "140",
        "160",
    ]


async def test_set_hr_zone_writes_whole_config(hass: HomeAssistant, client) -> None:
    client.notify(CONFIG)
    await hass.async_block_till_done()
    client.writes.clear()

    await _set(hass, ZONE.format(4), 175)
    # Zone 4 changed; zones 1-3 and the speed-sensor range go back untouched.
    assert client.writes == [bytes.fromhex("06 64 78 8c af bb 08 a8 2b")]
    assert hass.states.get(ZONE.format(4)).state == "175"

    # The fan's acknowledgement is authoritative.
    client.notify(bytes.fromhex("fe 06 01 64 78 8c ae bb 08 a8 2b"))
    await hass.async_block_till_done()
    assert hass.states.get(ZONE.format(4)).state == "174"


async def test_hr_zones_must_increase(hass: HomeAssistant, client) -> None:
    client.notify(CONFIG)
    await hass.async_block_till_done()
    client.writes.clear()

    with pytest.raises(ServiceValidationError, match="must increase"):
        await _set(hass, ZONE.format(2), 150)  # above zone 3 (140)
    with pytest.raises(ServiceValidationError, match="must increase"):
        await _set(hass, ZONE.format(3), 120)  # equal to zone 2
    assert client.writes == []
    assert hass.states.get(ZONE.format(2)).state == "120"
