"""BLE connection handling for a Wahoo KICKR Headwind (no Home Assistant imports)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging

from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
)

from .protocol import (
    CONTROL_CHAR_UUID,
    OFF_MODES,
    HeadwindMode,
    HeadwindUpdate,
    get_mode_command,
    get_speed_command,
    parse_notification,
    set_mode_command,
    set_speed_command,
)

_LOGGER = logging.getLogger(__name__)

# The fan only reports state while connected, so we keep the connection open
# and reconnect after this delay if it drops.
RECONNECT_DELAY = 10.0


class HeadwindDevice:
    """A single Headwind fan, kept connected and exposed as simple state."""

    def __init__(self, ble_device: BLEDevice, name: str | None = None) -> None:
        self._ble_device = ble_device
        self.name = name or ble_device.name or ble_device.address
        self._client: BleakClientWithServiceCache | None = None
        self._connect_lock = asyncio.Lock()
        self._callbacks: list[Callable[[], None]] = []
        self._reconnect_task: asyncio.Task[None] | None = None
        self._closing = False
        self.mode: HeadwindMode | None = None
        self.speed: int = 0
        self.last_raw: bytes | None = None

    @property
    def address(self) -> str:
        return self._ble_device.address

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    @property
    def is_on(self) -> bool:
        if self.mode is None or self.mode == HeadwindMode.MANUAL:
            return self.speed > 0
        # Sensor-driven modes are "on" even while the fan is momentarily at 0 %.
        return self.mode not in OFF_MODES

    def set_ble_device(self, ble_device: BLEDevice) -> None:
        """Update the BLEDevice (e.g. when a different proxy sees the fan)."""
        self._ble_device = ble_device

    def register_callback(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Register a state-change callback; returns an unsubscribe function."""
        self._callbacks.append(callback)
        return lambda: self._callbacks.remove(callback)

    def _fire_callbacks(self) -> None:
        for callback in list(self._callbacks):
            callback()

    async def connect(self) -> None:
        """Connect and subscribe to notifications if not already connected."""
        async with self._connect_lock:
            if self.connected:
                return
            self._closing = False
            _LOGGER.debug("%s: connecting", self.name)
            client = await establish_connection(
                BleakClientWithServiceCache,
                self._ble_device,
                self.name,
                disconnected_callback=self._on_disconnect,
                ble_device_callback=lambda: self._ble_device,
            )
            # The control point only supports write-without-response.
            try:
                await client.start_notify(CONTROL_CHAR_UUID, self._on_notify)
                # Ask for the current state; answers arrive as notifications.
                for command in (get_speed_command(), get_mode_command()):
                    await client.write_gatt_char(
                        CONTROL_CHAR_UUID, command, response=False
                    )
            except BleakError:
                await client.disconnect()
                raise
            self._client = client
            _LOGGER.debug("%s: connected", self.name)
        self._fire_callbacks()

    async def disconnect(self) -> None:
        """Disconnect and stop reconnecting."""
        self._closing = True
        if self._reconnect_task:
            self._reconnect_task.cancel()
            self._reconnect_task = None
        async with self._connect_lock:
            client, self._client = self._client, None
            if client is not None and client.is_connected:
                await client.disconnect()

    def _on_disconnect(self, _client: BleakClientWithServiceCache) -> None:
        _LOGGER.debug("%s: disconnected", self.name)
        self._client = None
        self._fire_callbacks()
        if not self._closing and self._reconnect_task is None:
            self._reconnect_task = asyncio.get_running_loop().create_task(
                self._reconnect()
            )

    async def _reconnect(self) -> None:
        try:
            while not self._closing and not self.connected:
                await asyncio.sleep(RECONNECT_DELAY)
                try:
                    await self.connect()
                except (BleakError, TimeoutError) as err:
                    _LOGGER.debug("%s: reconnect failed: %s", self.name, err)
        finally:
            self._reconnect_task = None

    def _on_notify(self, _sender: object, data: bytearray) -> None:
        self.last_raw = bytes(data)
        update = parse_notification(data)
        _LOGGER.debug("%s: notification %s -> %s", self.name, data.hex(" "), update)
        if update is not None:
            self._apply_update(update)

    def _apply_update(self, update: HeadwindUpdate) -> None:
        if update.mode is not None:
            self.mode = update.mode
        if update.speed is not None:
            self.speed = update.speed
        self._fire_callbacks()

    async def _write(self, payload: bytes) -> None:
        await self.connect()
        assert self._client is not None
        _LOGGER.debug("%s: write %s", self.name, payload.hex(" "))
        await self._client.write_gatt_char(CONTROL_CHAR_UUID, payload, response=False)

    async def set_mode(self, mode: HeadwindMode) -> None:
        await self._write(set_mode_command(mode))
        self.mode = mode
        self._fire_callbacks()

    async def set_speed(self, percentage: int) -> None:
        """Switch to manual mode (if needed) and set the fan speed."""
        if self.mode != HeadwindMode.MANUAL:
            await self._write(set_mode_command(HeadwindMode.MANUAL))
            self.mode = HeadwindMode.MANUAL
        await self._write(set_speed_command(percentage))
        self.speed = max(0, min(100, int(percentage)))
        self._fire_callbacks()

    async def turn_off(self) -> None:
        """Power the fan off the way the Wahoo app does (mode POWER_OFF)."""
        await self.set_mode(HeadwindMode.POWER_OFF)
