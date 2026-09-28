"""Base entity for the Wahoo KICKR Headwind integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import Entity

from .device import HeadwindDevice


class HeadwindEntity(Entity):
    """Common state and device info for Headwind entities."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, device: HeadwindDevice, key: str) -> None:
        self._device = device
        self._attr_unique_id = f"{device.address}_{key}"
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, device.address)},
            manufacturer="Wahoo Fitness",
            model="KICKR Headwind",
            name=device.name,
        )

    @property
    def available(self) -> bool:
        return self._device.connected

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._device.register_callback(self.async_write_ha_state)
        )
