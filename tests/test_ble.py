import asyncio
import ble

NO_JITTER = lambda a, b: 0.0


class FakeClient:
    """Stand-in for BleakClient for unit tests."""
    def __init__(self, mac, connect_error=None, drop_after_polls=None):
        self.mac = mac
        self.connect_error = connect_error
        self.is_connected = False
        self.notified_uuid = None
        self.writes = []
        self._drop_after = drop_after_polls
        self._polls = 0

    async def connect(self):
        if self.connect_error:
            raise self.connect_error
        self.is_connected = True

    async def disconnect(self):
        self.is_connected = False

    async def start_notify(self, uuid, cb):
        self.notified_uuid = uuid

    async def write_gatt_char(self, uuid, data):
        self.writes.append((uuid, data))
        self._polls += 1
        if self._drop_after and self._polls >= self._drop_after:
            self.is_connected = False


class FakeDev:
    def __init__(self, need_polling=False, poll_data=b"\x01"):
        self.mac_address = "AA:BB"
        self.logger_name = "reg"
        self.notify_uuid = "ffe4"
        self.need_polling = need_polling
        self.device_write_characteristic_polling = "ffd1"
        self._poll_data = poll_data
        self.events = []
        self.notify_callback = lambda char, data: None

    def get_poll_data(self):
        return self._poll_data

    def on_connected(self, client):
        self.events.append("connected")

    def on_disconnected(self):
        self.events.append("disconnected")


def test_maintain_connects_subscribes_and_polls():
    dev = FakeDev(need_polling=True)
    lock = asyncio.Lock()
    stop = asyncio.Event()
    made = []

    def factory(mac):
        c = FakeClient(mac, drop_after_polls=2)
        made.append(c)
        return c

    async def run():
        task = asyncio.create_task(
            ble.maintain_device(dev, lock, factory, stop, poll_interval=0,
                                rand=NO_JITTER, sleep=lambda d: asyncio.sleep(0)))
        # let it connect, subscribe, poll twice (then FakeClient drops), then stop
        await asyncio.sleep(0.05)
        stop.set()
        await asyncio.wait_for(task, timeout=1)

    asyncio.run(run())
    assert made[0].notified_uuid == "ffe4"          # start_notify called
    assert len(made[0].writes) >= 2                  # poll wrote data
    assert dev.events[:2] == ["connected", "disconnected"]


def test_maintain_backs_off_on_connect_error():
    dev = FakeDev()
    lock = asyncio.Lock()
    stop = asyncio.Event()
    delays = []

    def factory(mac):
        return FakeClient(mac, connect_error=RuntimeError("boom"))

    async def fake_sleep(d):
        delays.append(d)
        if len(delays) >= 3:
            stop.set()
        await asyncio.sleep(0)

    async def run():
        await asyncio.wait_for(
            ble.maintain_device(dev, lock, factory, stop, base_backoff=5,
                                max_backoff=300, rand=NO_JITTER, sleep=fake_sleep),
            timeout=1)

    asyncio.run(run())
    assert delays[:3] == [5, 10, 20]                 # exponential backoff on failure


def test_maintain_stops_without_connecting_when_already_stopped():
    dev = FakeDev()
    lock = asyncio.Lock()
    stop = asyncio.Event()
    stop.set()
    calls = {"n": 0}

    def factory(mac):
        calls["n"] += 1
        return FakeClient(mac)

    asyncio.run(asyncio.wait_for(
        ble.maintain_device(dev, lock, factory, stop, sleep=lambda d: asyncio.sleep(0)),
        timeout=1))
    assert calls["n"] == 0
