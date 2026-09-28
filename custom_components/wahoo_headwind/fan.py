"""Fan entity for the Wahoo KICKR Headwind."""

from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HeadwindConfigEntry
from .entity import HeadwindEntity
from .protocol import HeadwindMode

PRESET_MANUAL = "manual"
PRESET_HEART_RATE = "heart_rate"
PRESET_SPEED = "speed"

PRESET_TO_MODE = {
    PRESET_MANUAL: HeadwindMode.MANUAL,
    PRESET_HEART_RATE: HeadwindMode.HEART_RATE,
    PRESET_SPEED: HeadwindMode.SPEED,
}
MODE_TO_PRESET = {mode: preset for preset, mode in PRESET_TO_MODE.items()}

# Speed used when the fan is turned on without a percentage.
DEFAULT_ON_PERCENTAGE = 50


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeadwindConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([HeadwindFan(entry.runtime_data)])


class HeadwindFan(HeadwindEntity, FanEntity):
    """The Headwind fan: manual speed control plus HR/speed follow modes."""

    _attr_name = None
    _attr_translation_key = "headwind"
    _attr_preset_modes = list(PRESET_TO_MODE)
    _attr_speed_count = 100
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )

    def __init__(self, device) -> None:
        super().__init__(device, "fan")
        self._last_on_percentage = DEFAULT_ON_PERCENTAGE

    @property
    def is_on(self) -> bool:
        return self._device.is_on

    @property
    def percentage(self) -> int | None:
        return self._device.speed

    @property
    def preset_mode(self) -> str | None:
        return MODE_TO_PRESET.get(self._device.mode)

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage > 0:
            self._last_on_percentage = percentage
        await self._device.set_speed(percentage)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        await self._device.set_mode(PRESET_TO_MODE[preset_mode])

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        if preset_mode is not None:
            await self.async_set_preset_mode(preset_mode)
            return
        await self.async_set_percentage(percentage or self._last_on_percentage)

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self._device.speed > 0:
            self._last_on_percentage = self._device.speed
        await self._device.turn_off()
