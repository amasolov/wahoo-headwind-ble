"""The Wahoo KICKR Headwind integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_time_interval

from .device import HeadwindDevice

# How often to look for the fan advertising again while it is disconnected.
# This only reads Home Assistant's advertisement history; no radio traffic.
ADVERTISEMENT_CHECK_INTERVAL = timedelta(seconds=5)

PLATFORMS: list[Platform] = [Platform.FAN, Platform.NUMBER, Platform.SELECT]

type HeadwindConfigEntry = ConfigEntry[HeadwindDevice]


async def async_setup_entry(hass: HomeAssistant, entry: HeadwindConfigEntry) -> bool:
    """Set up a Headwind from a config entry."""
    address: str = entry.data[CONF_ADDRESS]
    ble_device = bluetooth.async_ble_device_from_address(
        hass, address.upper(), connectable=True
    )
    if ble_device is None:
        raise ConfigEntryNotReady(
            f"No connectable Bluetooth adapter or proxy can see {address}. The "
            "Headwind needs an active connection: use a local adapter or an "
            "ESPHome Bluetooth proxy (Shelly proxies are passive only)"
        )

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

    @callback
    def _async_check_advertising(_now: object) -> None:
        """Wake a reconnect if the fan advertised since it disconnected.

        The callback above doesn't cover this: Home Assistant skips callbacks
        for an advertisement identical to the last one it has on record, and
        after a short power cut (the Headwind's smart plug switched off and on
        within the ~3 min HA keeps a silent device's history) the fan's
        advertisement is byte-for-byte the one from before. The history still
        records when each advertisement arrived, identical or not.

        Seen on a real fan: plug off for 45 s, back on, and no reconnect until
        the stale history expired minutes later.
        """
        if device.connected:
            return
        info = bluetooth.async_last_service_info(hass, address.upper(), connectable=True)
        if info is not None and info.time > device.disconnected_at:
            device.set_ble_device(info.device)

    entry.async_on_unload(
        async_track_time_interval(
            hass, _async_check_advertising, ADVERTISEMENT_CHECK_INTERVAL
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
