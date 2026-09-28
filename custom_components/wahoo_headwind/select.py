"""Mode select for the Wahoo KICKR Headwind (includes sleep)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HeadwindConfigEntry
from .entity import HeadwindEntity
from .protocol import HeadwindMode

OPTIONS = {mode.name.lower(): mode for mode in HeadwindMode}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeadwindConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([HeadwindModeSelect(entry.runtime_data)])


class HeadwindModeSelect(HeadwindEntity, SelectEntity):
    """Select the fan operating mode."""

    _attr_translation_key = "mode"
    _attr_options = list(OPTIONS)

    def __init__(self, device) -> None:
        super().__init__(device, "mode")

    @property
    def current_option(self) -> str | None:
        mode = self._device.mode
        return mode.name.lower() if mode is not None else None

    async def async_select_option(self, option: str) -> None:
        await self._device.set_mode(OPTIONS[option])
