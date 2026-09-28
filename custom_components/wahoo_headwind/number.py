"""Number entities for the Wahoo KICKR Headwind: manual speed and HR zones."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HeadwindConfigEntry
from .device import (
    HeadwindConfigUnknownError,
    HeadwindDevice,
    HeadwindInvalidConfigError,
)
from .entity import HeadwindEntity
from .protocol import HR_ZONE_COUNT

BPM = "bpm"

# A resting heart rate below 40 or a working one above 220 isn't a zone
# boundary anyone would set; the protocol itself allows 0-255.
HR_MIN_BPM = 40
HR_MAX_BPM = 220


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeadwindConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    device = entry.runtime_data
    async_add_entities(
        [
            HeadwindManualSpeed(device),
            *(HeadwindHrZoneCeiling(device, zone) for zone in range(1, HR_ZONE_COUNT + 1)),
        ]
    )


class HeadwindManualSpeed(HeadwindEntity, NumberEntity):
    """Fan speed as a plain slider.

    The fan entity already takes a percentage, but that control is tucked
    into its more-info dialog. This is the same action as a dashboard-friendly
    slider: it switches the fan to manual mode and sets the speed. It shows
    the fan's current speed in every mode, so in heart-rate mode it follows
    what the fan chose.
    """

    _attr_translation_key = "manual_speed"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, device: HeadwindDevice) -> None:
        super().__init__(device, "manual_speed")

    @property
    def native_value(self) -> float | None:
        return self._device.speed

    async def async_set_native_value(self, value: float) -> None:
        await self._device.set_speed(round(value))


class HeadwindHrZoneCeiling(HeadwindEntity, NumberEntity):
    """Upper heart rate of one zone used by the fan's heart-rate mode."""

    _attr_translation_key = "hr_zone_ceiling"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = HR_MIN_BPM
    _attr_native_max_value = HR_MAX_BPM
    _attr_native_step = 1
    _attr_native_unit_of_measurement = BPM
    _attr_mode = NumberMode.BOX

    def __init__(self, device: HeadwindDevice, zone: int) -> None:
        super().__init__(device, f"hr_zone_{zone}_ceiling")
        self._zone = zone
        self._attr_translation_placeholders = {"zone": str(zone)}

    @property
    def available(self) -> bool:
        # Connected but config not yet read: showing a value would be a guess.
        return super().available and self._device.config is not None

    @property
    def native_value(self) -> float | None:
        if self._device.config is None:
            return None
        return self._device.config.hr_zone_ceilings[self._zone - 1]

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self._device.set_hr_zone_ceiling(self._zone, round(value))
        except HeadwindInvalidConfigError as err:
            raise ServiceValidationError(str(err)) from err
        except HeadwindConfigUnknownError as err:
            raise HomeAssistantError(str(err)) from err
