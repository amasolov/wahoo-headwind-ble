"""Mode select for the Wahoo KICKR Headwind."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HeadwindConfigEntry
from .entity import HeadwindEntity
from .protocol import HeadwindMode

OPTION_OFF = "off"

# Selectable modes. "off" writes POWER_OFF, like the Wahoo app's Off button.
OPTIONS: dict[str, HeadwindMode] = {
    OPTION_OFF: HeadwindMode.POWER_OFF,
    "manual": HeadwindMode.MANUAL,
    "heart_rate": HeadwindMode.HEART_RATE,
    "speed": HeadwindMode.SPEED,
    "power": HeadwindMode.POWER,
    "core_temp": HeadwindMode.CORE_TEMP,
    "run_speed": HeadwindMode.RUN_SPEED,
    "hybrid": HeadwindMode.HYBRID,
}
MODE_TO_OPTION = {mode: option for option, mode in OPTIONS.items()}
MODE_TO_OPTION[HeadwindMode.STANDBY] = OPTION_OFF


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
        return MODE_TO_OPTION.get(self._device.mode)

    async def async_select_option(self, option: str) -> None:
        await self._device.set_mode(OPTIONS[option])
