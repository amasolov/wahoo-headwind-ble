"""Tests for the config flow."""

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wahoo_headwind.const import DOMAIN

from .conftest import ADDRESS, NAME, make_service_info

PATCH_DISCOVERED = "custom_components.wahoo_headwind.config_flow.async_discovered_service_info"
PATCH_SETUP = "custom_components.wahoo_headwind.async_setup_entry"


async def test_bluetooth_discovery(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=make_service_info(),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "bluetooth_confirm"

    with patch(PATCH_SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert result["data"] == {CONF_ADDRESS: ADDRESS}


async def test_bluetooth_discovery_not_headwind(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=make_service_info(name="KICKR CORE", service_uuids=[]),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_bluetooth_discovery_already_configured(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id=ADDRESS, data={CONF_ADDRESS: ADDRESS}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=make_service_info(),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_step(hass: HomeAssistant) -> None:
    other = make_service_info(name="Some TV", service_uuids=[], address="11:22:33:44:55:66")
    by_name_only = make_service_info(name="HEADWIND 9", service_uuids=[], address="11:22:33:44:55:77")
    with patch(PATCH_DISCOVERED, return_value=[make_service_info(), other, by_name_only]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] is FlowResultType.FORM
    schema_keys = result["data_schema"].schema[CONF_ADDRESS].container
    assert set(schema_keys) == {ADDRESS, "11:22:33:44:55:77"}

    with patch(PATCH_SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: ADDRESS}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME


async def test_user_step_no_devices(hass: HomeAssistant) -> None:
    with patch(PATCH_DISCOVERED, return_value=[]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"
