"""Fixtures for Wahoo KICKR Headwind tests."""

from __future__ import annotations

from collections.abc import Generator
import time
from unittest.mock import AsyncMock, MagicMock, patch

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
import pytest

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

from custom_components.wahoo_headwind.protocol import SERVICE_UUID

ADDRESS = "AA:BB:CC:DD:EE:FF"
NAME = "HEADWIND 1234"


def make_service_info(
    name: str = NAME, service_uuids: list[str] | None = None, address: str = ADDRESS
) -> BluetoothServiceInfoBleak:
    uuids = [SERVICE_UUID] if service_uuids is None else service_uuids
    device = BLEDevice(address, name, None)
    return BluetoothServiceInfoBleak(
        name=name,
        address=address,
        rssi=-60,
        manufacturer_data={},
        service_data={},
        service_uuids=uuids,
        source="local",
        device=device,
        advertisement=AdvertisementData(
            local_name=name,
            manufacturer_data={},
            service_data={},
            service_uuids=uuids,
            tx_power=None,
            rssi=-60,
            platform_data=(),
        ),
        connectable=True,
        time=time.monotonic(),
        tx_power=None,
    )


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations in all tests."""


class FakeClient:
    """Minimal stand-in for BleakClientWithServiceCache."""

    def __init__(self, disconnected_callback) -> None:
        self.is_connected = True
        self.writes: list[bytes] = []
        self.notify_callback = None
        self._disconnected_callback = disconnected_callback
        self.write_gatt_char = AsyncMock(side_effect=self._write)
        self.disconnect = AsyncMock(side_effect=self._disconnect)

    async def start_notify(self, uuid, callback) -> None:
        self.notify_callback = callback

    async def _write(self, uuid, data, response=None) -> None:
        self.writes.append(bytes(data))

    async def _disconnect(self) -> None:
        self.is_connected = False

    def notify(self, data: bytes) -> None:
        self.notify_callback(None, bytearray(data))

    def drop(self) -> None:
        """Simulate the fan dropping the connection."""
        self.is_connected = False
        self._disconnected_callback(self)


@pytest.fixture
def fake_client() -> Generator[MagicMock]:
    """Patch establish_connection to return a FakeClient."""
    holder: dict[str, FakeClient] = {}

    async def _establish(client_class, device, name, disconnected_callback=None, **kw):
        holder["client"] = FakeClient(disconnected_callback)
        return holder["client"]

    with patch(
        "custom_components.wahoo_headwind.device.establish_connection",
        side_effect=_establish,
    ) as mock:
        mock.holder = holder
        yield mock
