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
    HeadwindMode,
    HeadwindState,
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
        if self.mode is None:
            return self.speed > 0
        if self.mode == HeadwindMode.SLEEP:
            return False
        if self.mode == HeadwindMode.MANUAL:
            return self.speed > 0
        # HR/speed modes are "on" even while the fan is momentarily at 0 %.
        return True

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
            try:
                await client.start_notify(CONTROL_CHAR_UUID, self._on_notify)
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
        state = parse_notification(data)
        _LOGGER.debug("%s: notification %s -> %s", self.name, data.hex(" "), state)
        if state is None:
            return
        self._apply_state(state)

    def _apply_state(self, state: HeadwindState) -> None:
        if state.mode is not None:
            self.mode = state.mode
        self.speed = state.speed
        self._fire_callbacks()

    async def _write(self, payload: bytes) -> None:
        await self.connect()
        assert self._client is not None
        _LOGGER.debug("%s: write %s", self.name, payload.hex(" "))
        await self._client.write_gatt_char(CONTROL_CHAR_UUID, payload, response=True)

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
        await self.set_speed(0)
