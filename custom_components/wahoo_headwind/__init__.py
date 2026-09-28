"""The Wahoo KICKR Headwind integration."""

from __future__ import annotations

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady

from .device import HeadwindDevice

PLATFORMS: list[Platform] = [Platform.FAN, Platform.SELECT]

type HeadwindConfigEntry = ConfigEntry[HeadwindDevice]


async def async_setup_entry(hass: HomeAssistant, entry: HeadwindConfigEntry) -> bool:
    """Set up a Headwind from a config entry."""
    address: str = entry.data[CONF_ADDRESS]
    ble_device = bluetooth.async_ble_device_from_address(
        hass, address.upper(), connectable=True
    )
    if ble_device is None:
        raise ConfigEntryNotReady(f"Could not find Headwind with address {address}")

    device = HeadwindDevice(ble_device, entry.title)

    @callback
    def _async_update_ble(
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Keep the BLEDevice fresh so reconnects use the best adapter/proxy."""
        device.set_ble_device(service_info.device)

    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            _async_update_ble,
            bluetooth.BluetoothCallbackMatcher(address=address.upper(), connectable=True),
            bluetooth.BluetoothScanningMode.PASSIVE,
        )
    )

    try:
        await device.connect()
    except Exception as err:  # noqa: BLE001 - bleak raises many error types
        await device.disconnect()
        raise ConfigEntryNotReady(f"Could not connect to {address}: {err}") from err

    entry.runtime_data = device

    async def _async_stop(event: Event) -> None:
        await device.disconnect()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HeadwindConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.disconnect()
    return unload_ok
