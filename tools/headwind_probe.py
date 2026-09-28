#!/usr/bin/env python3
"""Standalone Headwind BLE probe (needs only `pip install bleak`).

Use it on a laptop/Raspberry Pi near the fan to confirm the protocol:

    python tools/headwind_probe.py scan
    python tools/headwind_probe.py dump    AA:BB:CC:DD:EE:FF
    python tools/headwind_probe.py monitor AA:BB:CC:DD:EE:FF
    python tools/headwind_probe.py send    AA:BB:CC:DD:EE:FF 04 04   # manual mode
    python tools/headwind_probe.py send    AA:BB:CC:DD:EE:FF 02 32   # 50 %

`monitor` subscribes to every notifiable characteristic and prints the raw
bytes, so you can press the buttons on the fan (or change modes in the Wahoo
app on another device) and watch what changes. Close the Wahoo app first:
the fan usually accepts only one BLE connection.
"""

from __future__ import annotations

import argparse
import asyncio

from bleak import BleakClient, BleakScanner

SERVICE_UUID = "a026ee0c-0a7d-4ab3-97fa-f1500f9feb8b"
CONTROL_CHAR_UUID = "a026e038-0a7d-4ab3-97fa-f1500f9feb8b"


async def scan(seconds: float) -> None:
    found = await BleakScanner.discover(timeout=seconds, return_adv=True)
    for device, adv in found.values():
        name = adv.local_name or device.name or ""
        mark = "  <-- Headwind?" if "HEADWIND" in name.upper() or SERVICE_UUID in adv.service_uuids else ""
        print(f"{device.address}  rssi={adv.rssi:4}  {name!r:24} {adv.service_uuids}{mark}")


async def dump(address: str) -> None:
    async with BleakClient(address) as client:
        for service in client.services:
            print(f"[service] {service.uuid}  {service.description}")
            for char in service.characteristics:
                value = ""
                if "read" in char.properties:
                    try:
                        value = (await client.read_gatt_char(char)).hex(" ")
                    except Exception as err:  # noqa: BLE001
                        value = f"<{err}>"
                print(f"   [char] {char.uuid}  {','.join(char.properties):32} {value}")


async def monitor(address: str, seconds: float) -> None:
    async with BleakClient(address) as client:
        for service in client.services:
            for char in service.characteristics:
                if "notify" in char.properties or "indicate" in char.properties:
                    uuid = char.uuid

                    def handler(_s, data, uuid=uuid):
                        print(f"{asyncio.get_running_loop().time():10.2f}  {uuid}  {data.hex(' ')}")

                    await client.start_notify(char, handler)
                    print(f"subscribed to {uuid}")
        print(f"listening for {seconds:.0f}s ... (Ctrl+C to stop)")
        await asyncio.sleep(seconds)


async def send(address: str, payload: bytes, char: str, listen: float) -> None:
    async with BleakClient(address) as client:
        await client.start_notify(char, lambda _s, d: print("notify:", d.hex(" ")))
        print("write:", payload.hex(" "))
        props = client.services.get_characteristic(char).properties
        # The Headwind control point only supports write-without-response.
        await client.write_gatt_char(char, payload, response="write" in props)
        await asyncio.sleep(listen)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan")
    p.add_argument("--seconds", type=float, default=10)
    p = sub.add_parser("dump")
    p.add_argument("address")
    p = sub.add_parser("monitor")
    p.add_argument("address")
    p.add_argument("--seconds", type=float, default=120)
    p = sub.add_parser("send")
    p.add_argument("address")
    p.add_argument("hex", nargs="+", help="bytes, e.g. 02 32")
    p.add_argument("--char", default=CONTROL_CHAR_UUID)
    p.add_argument("--listen", type=float, default=3)
    args = parser.parse_args()

    if args.cmd == "scan":
        asyncio.run(scan(args.seconds))
    elif args.cmd == "dump":
        asyncio.run(dump(args.address))
    elif args.cmd == "monitor":
        asyncio.run(monitor(args.address, args.seconds))
    else:
        asyncio.run(send(args.address, bytes.fromhex("".join(args.hex)), args.char, args.listen))


if __name__ == "__main__":
    main()
