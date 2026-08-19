"""Writes to one connection are serialised.

Poll writes (`ble._hold`) and command writes
(`SolarDevice.characteristic_write_value`) are separate coroutines on the same
asyncio loop, so they interleave at every await: a command could start a write
while a poll write was still in flight on the same connection.
"""

import asyncio

import ble


class _Client:
    """Records overlap: how many writes were in flight at once."""

    def __init__(self):
        self.is_connected = True
        self.concurrent = 0
        self.max_concurrent = 0
        self.writes = []
        self._solar_write_lock = asyncio.Lock()

    async def write_gatt_char(self, char, data):
        self.concurrent += 1
        self.max_concurrent = max(self.max_concurrent, self.concurrent)
        await asyncio.sleep(0)          # a real write yields here
        self.writes.append((char, bytes(data)))
        self.concurrent -= 1


class _Device:
    logger_name = "test-device"
    need_polling = True
    device_write_characteristic_polling = "poll-char"

    def get_poll_data(self):
        return [1, 2, 3]


async def _competing_writer(client, n):
    """Stands in for command writes arriving while the poll loop runs."""
    for _ in range(n):
        async with client._solar_write_lock:
            await client.write_gatt_char("cmd-char", b"\x01")


def test_poll_and_command_writes_never_overlap():
    client, dev = _Client(), _Device()

    async def run():
        stop = asyncio.Event()

        async def stop_soon():
            await asyncio.sleep(0.05)
            stop.set()

        await asyncio.gather(
            ble._hold(dev, client, stop, 0.001, asyncio.sleep),
            _competing_writer(client, 20),
            stop_soon(),
        )

    asyncio.run(run())
    assert client.writes, "no writes were issued"
    assert client.max_concurrent == 1, (
        f"{client.max_concurrent} writes were in flight at once")


def test_a_client_without_a_lock_still_writes():
    """The lock is looked up defensively; absence must not break writing."""
    client, dev = _Client(), _Device()
    del client._solar_write_lock

    async def run():
        stop = asyncio.Event()

        async def stop_soon():
            await asyncio.sleep(0.02)
            stop.set()

        await asyncio.gather(ble._hold(dev, client, stop, 0.001, asyncio.sleep), stop_soon())

    asyncio.run(run())
    assert client.writes
