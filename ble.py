"""Asyncio BLE transport (bleak) for solar-monitor.

Replaces the abandoned `gatt` library. One asyncio loop (owned by BleManager,
Task 3) runs in a daemon thread; each device gets one `maintain_device` task.
bleak uses AcquireNotify for notifications, which — unlike gatt's dbus-signal
StartNotify — keeps up with high-rate notifiers (the Meritsun batteries).
"""
import asyncio
import logging

from connection import backoff_seconds


async def _hold(dev, client, stop_event, poll_interval, sleep):
    """Hold a resolved connection, polling if the device needs it, until the
    link drops or shutdown is requested."""
    while not stop_event.is_set() and client.is_connected:
        if dev.need_polling and dev.device_write_characteristic_polling:
            data = dev.get_poll_data()
            if data:
                try:
                    await client.write_gatt_char(dev.device_write_characteristic_polling, data)
                except Exception as e:
                    logging.debug("[%s] poll write failed: %r", dev.logger_name, e)
                    break
        await sleep(poll_interval)


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
    them to the async layer. Replaces the per-device mqtt_poller thread."""
    if not (datalogger and datalogger.mqtt):
        return
    mqtt = datalogger.mqtt
    triggers = mqtt.trigger
    while not stop_event.is_set():
        fired = False
        for name, trig in list(triggers.items()):
            if trig.wait(0.5):
                trig.clear()
                fired = True
                dev = devices_by_name.get(name)
                sets = mqtt.sets.get(name, [])
                mqtt.sets[name] = []
                if dev is not None:
                    for var, message in sets:
                        manager.submit_command(dev, var, message)
        if not fired:
            stop_event.wait(0.2)
