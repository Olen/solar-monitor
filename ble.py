"""Asyncio BLE transport (bleak) for solar-monitor.

One asyncio loop (owned by BleManager) runs in a daemon thread; each device gets
one `maintain_device` task.

bleak subscribes with BlueZ's StartNotify. Its AcquireNotify path delivers over
a file descriptor instead of D-Bus, which avoids a known BlueZ notification loss
(bleak#1343), but measured against the Meritsun packs it makes no difference:
what those packs lose is lost below D-Bus, at the connection interval. That is
what `connection_interval` addresses.
"""
import asyncio
import logging

import hci
from connection import backoff_seconds

# How much of the hold loop passes between link-quality checks, and what counts
# as a healthy link. A link at the interval we ask for accepts ~85% of framed
# packets; one the peripheral has renegotiated slow accepts under 5%.
VERIFY_SECONDS = 60.0
MIN_FRAMES_TO_JUDGE = 20
MIN_ACCEPT_RATIO = 0.3


def _assert_connection_interval(dev):
    """Ask for the configured interval on a link that has just come up.

    A peripheral may renegotiate the interval a few seconds after connecting,
    and BlueZ grants it. The packs do this once per connection, so asserting on
    connect is enough; `_verify_link` covers the rest.
    """
    interval = getattr(dev, "connection_interval", None)
    if interval:
        hci.set_connection_interval(dev.mac_address, *interval)


def _verify_link(dev):
    """Re-assert the interval when the data says the link has gone slow.

    No HCI command reads the current interval back, but a renegotiated link is
    unmistakable in the frames: nearly all of them fail the checksum.
    """
    interval = getattr(dev, "connection_interval", None)
    if not interval:
        return
    health = dev.frame_health()
    if not health:
        return
    accepted, rejected = health
    total = accepted + rejected
    if total < MIN_FRAMES_TO_JUDGE or accepted >= total * MIN_ACCEPT_RATIO:
        return
    logging.warning("[%s] %d of %d frames accepted; re-asserting %g-%g ms",
                    dev.logger_name, accepted, total, *interval)
    hci.set_connection_interval(dev.mac_address, *interval)


async def _hold(dev, client, stop_event, poll_interval, sleep):
    """Hold a resolved connection, polling if the device needs it, until the
    link drops or shutdown is requested."""
    since_verify = 0.0
    while not stop_event.is_set() and client.is_connected:
        if dev.need_polling and dev.device_write_characteristic_polling:
            data = dev.get_poll_data()
            if data:
                # Plugins may return a list of ints; bleak needs a bytes-like object.
                if not isinstance(data, (bytes, bytearray, memoryview)):
                    data = bytearray(data)
                try:
                    lock = getattr(client, "_solar_write_lock", None)
                    if lock is not None:
                        async with lock:
                            await client.write_gatt_char(dev.device_write_characteristic_polling, data)
                    else:
                        await client.write_gatt_char(dev.device_write_characteristic_polling, data)
                except Exception as e:
                    logging.warning("[%s] poll write failed: %r", dev.logger_name, e)
                    break
        await sleep(poll_interval)
        since_verify += poll_interval
        if since_verify >= VERIFY_SECONDS:
            since_verify = 0.0
            _verify_link(dev)


async def maintain_device(dev, connect_lock, client_factory, stop_event,
                          poll_interval=1.0, base_backoff=10.0, max_backoff=300.0,
                          jitter=5.0, rand=None, sleep=None):
    """Keep one device connected + notifying until stop_event is set.

    Establishment is serialized by `connect_lock` (the controller allows one LE
    Create Connection in flight at a time). After a good connection we retry
    promptly; after a failed attempt we back off exponentially (with jitter).
    """
    if sleep is None:
        sleep = asyncio.sleep
    attempt = 0
    while not stop_event.is_set():
        client = client_factory(dev.mac_address)
        connected = False
        try:
            async with connect_lock:
                logging.info("[%s] Connecting to %s", dev.logger_name, dev.mac_address)
                await client.connect()
                dev.on_connected(client)
                # Subscribe to EVERY notify characteristic the device exposes;
                # some devices (VEDirect) stream data across several and go silent
                # (and drop the link) if any is left unsubscribed.
                notify_uuids = getattr(dev, "notify_uuids", None)
                if not notify_uuids and dev.notify_uuid:
                    notify_uuids = [dev.notify_uuid]
                for uuid in (notify_uuids or []):
                    await client.start_notify(uuid, dev.notify_callback)
                connected = True
            _assert_connection_interval(dev)
            await _hold(dev, client, stop_event, poll_interval, sleep)
        except Exception as e:
            logging.error("[%s] connection error: %r", dev.logger_name, e)
        finally:
            dev.on_disconnected()
            try:
                if getattr(client, "is_connected", False):
                    await client.disconnect()
            except Exception:
                pass
        if stop_event.is_set():
            break
        if connected:
            attempt = 0                              # had a good connection — retry promptly
            continue
        attempt += 1
        await sleep(backoff_seconds(attempt, base_backoff, max_backoff, jitter, rand))


import threading

try:
    from bleak import BleakClient, BleakScanner
except Exception:                      # allow import on hosts without bleak (tests use fakes)
    BleakClient = None
    BleakScanner = None


class BleManager:
    """Owns the asyncio loop (in a daemon thread) and all BLE tasks."""
    def __init__(self, adapter=None, connect_backoff=10.0):
        self.adapter = adapter
        self.connect_backoff = connect_backoff
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="ble-loop", daemon=True)
        self._stop = None              # asyncio.Event created on the loop
        self._tasks = {}               # mac -> Task
        self._connect_lock = None      # asyncio.Lock created on the loop

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _client_factory(self, mac):
        client = BleakClient(mac, adapter=self.adapter) if self.adapter else BleakClient(mac)
        client._solar_loop = self.loop
        # Poll writes (_hold) and command writes (SolarDevice.characteristic_write_value)
        # are separate coroutines on this one loop, so they interleave at every
        # await -- a command can start a write while a poll write is in flight on
        # the same connection. Serialise them per client.
        client._solar_write_lock = asyncio.Lock()
        return client

    def start(self):
        self._thread.start()
        fut = asyncio.run_coroutine_threadsafe(self._init_primitives(), self.loop)
        fut.result(timeout=5)

    async def _init_primitives(self):
        self._stop = asyncio.Event()
        self._connect_lock = asyncio.Lock()

    async def _stop_aware_sleep(self, delay):
        """Sleep up to `delay` seconds, returning early if shutdown is requested.
        Keeps maintain_device's backoff/poll waits from stalling stop()."""
        if delay <= 0:
            return
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass

    def stop(self):
        async def _shutdown():
            self._stop.set()
            for t in list(self._tasks.values()):
                t.cancel()
        try:
            asyncio.run_coroutine_threadsafe(_shutdown(), self.loop).result(timeout=5)
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=5)

    def discover(self, timeout=10.0):
        async def _scan():
            found = {}
            devices = await BleakScanner.discover(timeout=timeout, adapter=self.adapter) \
                if self.adapter else await BleakScanner.discover(timeout=timeout)
            for d in devices:
                found[d.address.lower()] = d.name or d.address
            return found
        return asyncio.run_coroutine_threadsafe(_scan(), self.loop).result(timeout=timeout + 5)

    def register(self, dev):
        async def _add():
            if dev.mac_address in self._tasks:
                return
            self._tasks[dev.mac_address] = asyncio.create_task(
                maintain_device(dev, self._connect_lock, self._client_factory,
                                self._stop, base_backoff=self.connect_backoff,
                                sleep=self._stop_aware_sleep))
        asyncio.run_coroutine_threadsafe(_add(), self.loop).result(timeout=5)

    def submit_command(self, dev, var, value):
        async def _cmd():
            try:
                dev.run_command(var, value)
            except Exception as e:
                logging.error("[%s] command %s failed: %r", dev.logger_name, var, e)
        asyncio.run_coroutine_threadsafe(_cmd(), self.loop)

    def set_trusted(self, mac, trusted):
        # bleak has no trust API; shell out to bluetoothctl (best-effort).
        import subprocess
        cmd = "trust" if trusted else "untrust"
        try:
            subprocess.run(["bluetoothctl", cmd, mac], timeout=5,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            logging.debug("bluetoothctl %s %s failed: %s", cmd, mac, e)


def command_bridge(datalogger, devices_by_name, manager, stop_event):
    """Threaded: consume MQTT commands (datalogger.mqtt.sets/trigger) and route
    them to the async layer.

    The datalogger's on_message drains into mqtt.sets[device] and fires
    mqtt.trigger[device]. Nothing else creates those trigger Events, so one
    shared wake Event is registered for every device here. Draining also happens
    on the 0.5s poll timeout, so a command that arrives before its trigger is
    registered -- or with no trigger at all -- is still delivered."""
    if not (datalogger and datalogger.mqtt):
        return
    mqtt = datalogger.mqtt
    wake = threading.Event()
    registered = set()
    while not stop_event.is_set():
        for name in list(devices_by_name.keys()):
            if name not in registered:
                mqtt.trigger[name] = wake        # all devices share one wake Event
                registered.add(name)
        wake.wait(0.5)                           # wake on a command, else poll
        wake.clear()
        for name in list(devices_by_name.keys()):
            sets = mqtt.sets.get(name)
            if not sets:
                continue
            mqtt.sets[name] = []
            dev = devices_by_name.get(name)
            if dev is not None:
                for var, message in sets:
                    logging.info("[%s] MQTT command -> device: %s = %s", name, var, message)
                    manager.submit_command(dev, var, message)
