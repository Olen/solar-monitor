# BLE Migration (gatt → bleak) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace solar-monitor's abandoned `gatt` BLE transport with `bleak` so high-rate GATT notifications (Meritsun batteries ~10/sec) are delivered reliably (bleak uses AcquireNotify; gatt's dbus-signal StartNotify drops them).

**Architecture:** One asyncio event loop runs in a dedicated daemon thread and owns all BLE (new `ble.py`). The rest of the app stays threaded/synchronous and unchanged. Data crosses to the threaded side via the existing `pipeline` `queue.Queue`; MQTT commands cross into the loop via `run_coroutine_threadsafe`. `SolarDevice` slims to a decoding-only object that keeps the exact surface the plugins use.

**Tech Stack:** Python 3, `bleak` (asyncio BLE), `paho-mqtt`, existing `duallog`/`supervisor`/`datalogger`. Tests: `pytest` driving async coroutines via `asyncio.run` (no `pytest-asyncio` dependency).

## Global Constraints

- Do NOT change: `plugins/*/__init__.py`, the entity decoders in `solardevice.py` (`PowerDevice`/`BatteryDevice`/`RegulatorDevice`/`InverterDevice`/`RectifierDevice`), `datalogger.py`, `supervisor.py`, `duallog.py`.
- Preserve the exact `SolarDevice` surface the plugins use: `entities`, `characteristic_write_value(value, char_uuid)`, `device_write_characteristic_polling`, `device_write_characteristic_commands`, `device_id`, `config` (`getboolean`), `alias()`, `logger_name`, `need_polling`, `send_ack`, `util`, `module`.
- Reuse `connection.backoff_seconds(attempt, base, maximum, jitter, rand)` unchanged (keep its tests).
- Keep the `persistent`/`trusted`/availability behaviour already committed; default trust = `need_polling`.
- Serialize connection *establishment* (one `connect()` at a time) — now an `asyncio.Lock`.
- Notification callback must be lean (decode + non-blocking `try_put`); it runs on the loop and must not block it.
- Python 3, no `pytest-asyncio`; write async tests with `asyncio.run(coro())`.

---

## File Structure

- **Create `ble.py`** — asyncio BLE layer: `maintain_device`, `poll_loop` helper, `BleManager`, `command_bridge`. Owns the loop/thread, adapter, scan, per-device tasks, the establishment `asyncio.Lock`.
- **Create `tests/test_ble.py`** — async unit tests with a `FakeClient`.
- **Modify `solardevice.py`** — slim `SolarDevice` (drop `gatt.Device`, callbacks, poller threads; add `on_connected`, `notify_callback`, `on_notification`, async-scheduled `characteristic_write_value`, `get_poll_data`). Delete `SolarDeviceManager(gatt.DeviceManager)`.
- **Modify `monitor_app.py`** — build `BleManager`, discover, register devices, start; wire the MQTT command bridge; remove the GLib loop thread, per-device `threading.Thread`s, `connect_lock`, `_make_connect_fn`/`_make_rotating_connect_fn`.
- **Modify `connection.py`** — keep `backoff_seconds`; delete thread-based `maintain_device`/`rotate_devices`.
- **Modify `tests/test_connection.py`** — keep the `backoff_seconds` tests; delete the `maintain_device`/`rotate_devices` tests (moved to `test_ble.py`).
- **Modify `requirements.txt`** — add `bleak`; remove `gatt`, `dbus-python`, `pycairo`, `PyGObject`.
- **`solar-monitor.py`** entrypoint — unchanged (still calls `monitor_app.main()`).

---

## Task 1: Async connection core in `ble.py` (`maintain_device` + `poll_loop`)

**Files:**
- Create: `ble.py`
- Test: `tests/test_ble.py`

**Interfaces:**
- Consumes: `connection.backoff_seconds(attempt, base=10.0, maximum=300.0, jitter=5.0, rand=None) -> float`.
- Consumes (from a `dev` duck-type, provided by Task 2): `dev.mac_address:str`, `dev.logger_name:str`, `dev.notify_uuid:str|None`, `dev.notify_callback(char, data)`, `dev.need_polling:bool`, `dev.device_write_characteristic_polling:str|None`, `dev.get_poll_data() -> bytes|None`, `dev.on_connected(client)`, `dev.on_disconnected()`.
- Produces: `async maintain_device(dev, connect_lock, client_factory, stop_event, poll_interval=1.0, base_backoff=10.0, max_backoff=300.0, jitter=5.0, rand=None, sleep=None) -> None`. `client_factory(mac:str) -> client` where `client` has async `connect()/disconnect()/start_notify(uuid,cb)/write_gatt_char(uuid,data)` and property `is_connected:bool`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ble.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_ble.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ble'` / `AttributeError: module 'ble' has no attribute 'maintain_device'`.

- [ ] **Step 3: Implement `ble.py` core**

Create `ble.py`:

```python
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
                if dev.notify_uuid:
                    await client.start_notify(dev.notify_uuid, dev.notify_callback)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_ble.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add ble.py tests/test_ble.py
git commit -m "feat: async BLE maintain_device (bleak) with fake-client tests"
```

---

## Task 2: Slim `SolarDevice` to decoding-only

**Files:**
- Modify: `solardevice.py` (class `SolarDevice` `__init__` and methods; delete `SolarDeviceManager`)
- Test: `tests/test_ble.py` (add decoding tests)

**Interfaces:**
- Consumes: the plugin `Util` interface (`util.notificationUpdate(data, uuid) -> truthy`, `util.pollRequest() -> bytes|None`, `util.cmdRequest(var, msg) -> list[bytes]`, `util.ackData(value) -> bytes`) and `entities` decoders — UNCHANGED.
- Produces (used by Task 1 and Task 3):
  - `SolarDevice(mac_address, logger_name, config, datalogger, queue)` — no `manager`, not a `gatt.Device`.
  - attrs: `mac_address`, `logger_name`, `need_polling:bool`, `send_ack:bool`, `notify_uuid:str|None` (first of `char_notify`), `device_write_characteristic_polling:str|None`, `device_write_characteristic_commands:str|None`, `device_id`, `config`, `entities`, `module`, `util`, `alias()`.
  - `on_connected(client)` — set `self._client = client`, resolve write-UUIDs, set alias+availability on the datalogger.
  - `notify_callback(char, data)` — bleak notification entry; calls `on_notification(str(char.uuid), bytes(data))`.
  - `on_notification(uuid, data)` — decode + enqueue (body of old `characteristic_value_updated`).
  - `characteristic_write_value(value, char_uuid)` — schedule `self._client.write_gatt_char(char_uuid, value)` on the running loop (used by VEDirect and ack path).
  - `get_poll_data() -> bytes|None` — `return self.util.pollRequest()`.
  - `run_command(var, message)` — `for data in self.util.cmdRequest(var, message): write`.
  - `alias()` — returns the advertised name captured at discovery (`self._alias`), no gatt call.

- [ ] **Step 1: Write the failing decoding test**

Add to `tests/test_ble.py`:

```python
import solardevice
import queue as _queue
import configparser


def _meritsun_config():
    c = configparser.ConfigParser()
    c.add_section("monitor"); c.set("monitor", "reconnect", "False")
    c.add_section("battery_1")
    c.set("battery_1", "type", "Meritsun")
    c.set("battery_1", "mac", "7C:01:0A:41:CA:F9")
    return c


def test_solardevice_on_notification_decodes_and_enqueues():
    q = _queue.Queue(maxsize=100)
    dev = solardevice.SolarDevice(
        mac_address="7C:01:0A:41:CA:F9", logger_name="battery_1",
        config=_meritsun_config(), datalogger=None, queue=q)
    # Feed a known Meritsun frame captured on hardware (voltage/soc present).
    # A real frame from leveld; see docs/superpowers/specs for capture procedure.
    frame = bytes.fromhex("92" + "00" * 60)   # START_VAL then padding (parser tolerates)
    dev.on_notification("0000ffe4-0000-1000-8000-00805f9b34fb", frame)
    # notificationUpdate ran without raising; queue may be empty for a padding
    # frame, which is fine — the assertion is that it does not throw and the
    # device is wired (util present, notify_uuid resolved).
    assert dev.util is not None
    assert dev.notify_uuid == "0000ffe4-0000-1000-8000-00805f9b34fb"
```

> Note to implementer: replace `frame` with a real captured Meritsun notification (hex) from `leveld` (`grep "<-" /tmp/12V100Ah-*.log` produced when `debug=True`) and assert a concrete value lands in `q` (e.g. an `soc` tuple). The padding-frame version above must at minimum pass without raising.

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_ble.py::test_solardevice_on_notification_decodes_and_enqueues -q`
Expected: FAIL — `SolarDevice.__init__` still requires `manager` / is a `gatt.Device`.

- [ ] **Step 3: Rewrite `SolarDevice` (transport-free)**

In `solardevice.py`:
- Remove `import gatt` and the `class SolarDeviceManager(gatt.DeviceManager)` block entirely.
- Change the class declaration and `__init__` signature:

```python
class SolarDevice:
    def __init__(self, mac_address, logger_name='unknown', type=None,
                 datalogger=None, queue=None, config=None):
        self.mac_address = mac_address
        self.logger_name = logger_name
        self.datalogger = datalogger
        self.queue = queue
        self.config = config
        self._client = None
        self._alias = logger_name
        self._dropped = 0
        # plugin-derived, filled below
        self.module = None
        self.util = None
        self.type = None
        self.device_id = None
        self.need_polling = None
        self.send_ack = None
        self.notify_uuid = None
        self.device_write_characteristic_polling = None
        self.device_write_characteristic_commands = None
        self.entities = None

        if config:
            self.type = config.get(logger_name, 'type', fallback=None)
        if not self.type:
            return
        try:
            mod = __import__("plugins." + self.type)
            self.module = getattr(mod, self.type)
            logging.info("Successfully imported {}.".format(self.type))
        except ImportError:
            logging.error("Error importing {}".format(self.type))
            raise ImportError()

        self.service_notify = getattr(self.module.Config, "NOTIFY_SERVICE_UUID", None)
        self.service_write = getattr(self.module.Config, "WRITE_SERVICE_UUID", None)
        self.char_notify = getattr(self.module.Config, "NOTIFY_CHAR_UUID", None)
        self.char_write_polling = getattr(self.module.Config, "WRITE_CHAR_UUID_POLLING", None)
        self.char_write_commands = getattr(self.module.Config, "WRITE_CHAR_UUID_COMMANDS", None)
        self.device_id = getattr(self.module.Config, "DEVICE_ID", None)
        self.need_polling = bool(getattr(self.module.Config, "NEED_POLLING", None))
        self.send_ack = getattr(self.module.Config, "SEND_ACK", None)
        # char_notify may be a str or a container of UUIDs; pick the first.
        if isinstance(self.char_notify, (list, tuple, set)):
            self.notify_uuid = next(iter(self.char_notify), None)
        else:
            self.notify_uuid = self.char_notify
        # write chars are plain UUID strings for bleak.write_gatt_char
        self.device_write_characteristic_polling = self.char_write_polling
        self.device_write_characteristic_commands = self.char_write_commands

        if "battery" in logger_name:
            self.entities = BatteryDevice(parent=self)
        elif "regulator" in logger_name:
            self.entities = RegulatorDevice(parent=self)
        elif "inverter" in logger_name:
            self.entities = InverterDevice(parent=self)
        elif "rectifier" in logger_name:
            self.entities = RectifierDevice(parent=self)
        else:
            self.entities = PowerDevice(parent=self)
        self.util = self.module.Util(self)
```

- Replace `alias()`:

```python
    def alias(self):
        return self._alias
```

- Add the transport hooks (replacing `connect`, `services_resolved`, callbacks, pollers):

```python
    def set_alias(self, name):
        if name:
            self._alias = name.strip()

    def on_connected(self, client):
        self._client = client
        logging.info("[{}] Connected to {}".format(self.logger_name, self.alias()))
        if self.datalogger:
            try:
                self.datalogger.set_device_alias(self.logger_name, self.alias())
                self.datalogger.set_available(self.logger_name, True)
            except Exception as e:
                logging.debug("[{}] alias/availability: {}".format(self.logger_name, e))

    def on_disconnected(self):
        if self.datalogger:
            try:
                self.datalogger.set_available(self.logger_name, False)
            except Exception:
                pass
        self._client = None

    def notify_callback(self, characteristic, data):
        try:
            self.on_notification(str(getattr(characteristic, "uuid", characteristic)), bytes(data))
        except Exception as e:
            logging.error("[{}] notify handler error: {}".format(self.logger_name, e))

    def get_poll_data(self):
        return self.util.pollRequest() if self.util else None

    def run_command(self, var, message):
        for data in self.util.cmdRequest(var, message):
            self.characteristic_write_value(data, self.device_write_characteristic_commands)
```

- Rename the notification body from `characteristic_value_updated(self, characteristic, value)` to `on_notification(self, uuid, value)`; delete `super().characteristic_value_updated(...)`; use `uuid` instead of `characteristic.uuid`:

```python
    def on_notification(self, uuid, value):
        if self.send_ack:
            data = self.util.ackData(value)
            self.characteristic_write_value(data, self.device_write_characteristic_polling)
        if self.util.notificationUpdate(value, uuid):
            items = ['current', 'input_current', 'charge_current',
                     'voltage', 'input_voltage', 'charge_voltage',
                     'power', 'input_power', 'charge_power',
                     'soc', 'capacity', 'exp_capacity', 'max_capacity',
                     'charge_cycles', 'state', 'health', 'power_switch']
            for item in items:
                try:
                    self._enqueue((self.logger_name, item, getattr(self.entities, item)))
                except Exception:
                    pass
            try:
                self._enqueue((self.logger_name, 'temperature', self.entities.temperature_celsius))
                self._enqueue((self.logger_name, 'battery_temperature', self.entities.battery_temperature_celsius))
            except Exception:
                pass
            try:
                for cell in self.entities.cell_mvoltage:
                    if self.entities.cell_mvoltage[cell]['val'] > 0:
                        self._enqueue((self.logger_name, 'cell_{}'.format(cell), self.entities.cell_mvoltage[cell]['val']))
            except Exception:
                pass
            try:
                for cell in self.entities.cell_voltage:
                    if self.entities.cell_voltage[cell]['val'] > 0:
                        self._enqueue((self.logger_name, 'cell_{}_voltage'.format(cell), self.entities.cell_voltage[cell]['val']))
            except Exception:
                pass
```

- Replace `characteristic_write_value` to schedule a bleak write on the loop (drop the gatt object + `characteristic_write_value_succeeded/failed`):

```python
    def characteristic_write_value(self, value, char_uuid):
        client = self._client
        if client is None or char_uuid is None:
            return
        loop = getattr(client, "_solar_loop", None) or asyncio.get_event_loop()
        async def _w():
            try:
                await client.write_gatt_char(char_uuid, value)
            except Exception as e:
                logging.debug("[{}] write failed: {}".format(self.logger_name, e))
        try:
            asyncio.run_coroutine_threadsafe(_w(), loop)
        except Exception as e:
            logging.debug("[{}] write schedule failed: {}".format(self.logger_name, e))
```

- Delete: `def connect`, `def connect_succeeded`, `def connect_failed`, `def disconnect_succeeded`, `def services_resolved`, `def _signal_connect_result`, `def device_poller`, `def mqtt_poller`, `def characteristic_enable_notifications_*`, `def characteristic_write_value_succeeded/failed`, and the `_connect_event`/`_disconnect_event`/`run_device_poller`/`run_command_poller`/`command_trigger`/`on_disconnect` attributes.
- Keep `_enqueue`, `set_trusted` (it uses `self._client` / BlueZ via bleak's backend; see Task 3 note), and the entity classes (`PowerDevice` … `BatteryDevice`) exactly as-is.
- Add `import asyncio` at the top; remove `import gatt`, `import dbus`, `from dbus.exceptions import DBusException` (if no longer referenced — `set_trusted` moves to Task 3).

> Implementer note: `set_trusted()` used `self._properties` (a gatt/dbus proxy). With bleak there is no such proxy. Move trust-setting to `BleManager` (Task 3), which can set `org.bluez.Device1 Trusted` via bleak's bluez backend or `bluetoothctl`. Remove `set_trusted` from `SolarDevice`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_ble.py -q`
Expected: PASS (including the decoding test). Also run `python3 -m py_compile solardevice.py`.

- [ ] **Step 5: Commit**

```bash
git add solardevice.py tests/test_ble.py
git commit -m "refactor: slim SolarDevice to decoding-only (no gatt)"
```

---

## Task 3: `BleManager` (loop thread, discover, register, start/stop, command bridge)

**Files:**
- Modify: `ble.py` (add `BleManager`, `command_bridge`)
- Test: `tests/test_ble.py` (add manager registration/command tests with fakes)

**Interfaces:**
- Consumes: `bleak.BleakScanner`, `bleak.BleakClient`; `SolarDevice` (Task 2); `maintain_device` (Task 1).
- Produces:
  - `BleManager(adapter=None, connect_backoff=10.0)`:
    - `start()` — start the loop thread.
    - `stop()` — set stop, cancel tasks, stop loop, join thread.
    - `discover(timeout=10.0) -> dict[str,str]` — address(lower) → advertised name (runs a `BleakScanner` on the loop, thread-safe).
    - `register(dev)` — schedule a `maintain_device` task for `dev` (idempotent per `dev.mac_address`).
    - `set_trusted(mac, trusted)` — set BlueZ Trusted for the address.
    - `submit_command(dev, var, value)` — thread-safe; `run_coroutine_threadsafe(dev.run_command(var,value)-as-coro)`. Since `run_command` writes via `characteristic_write_value` (which itself schedules), `submit_command` just calls `dev.run_command(var, value)` on the loop.
  - `command_bridge(datalogger, devices_by_name, manager, stop_event)` — a threaded loop: wait on each device's MQTT trigger, drain `datalogger.mqtt.sets[name]`, call `manager.submit_command(dev, var, value)`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_ble.py`:

```python
def test_manager_registers_and_runs_a_device_task(monkeypatch):
    import ble
    mgr = ble.BleManager(adapter=None)
    made = {}

    def fake_factory(mac):
        c = FakeClient(mac, drop_after_polls=1)
        made[mac] = c
        return c

    monkeypatch.setattr(mgr, "_client_factory", fake_factory)
    dev = FakeDev(need_polling=True)
    mgr.start()
    try:
        mgr.register(dev)
        # give the loop time to connect+subscribe
        import time; time.sleep(0.2)
        assert made[dev.mac_address].notified_uuid == "ffe4"
    finally:
        mgr.stop()


def test_submit_command_invokes_run_command_on_loop():
    import ble, time
    mgr = ble.BleManager(adapter=None)
    called = []

    class Dev(FakeDev):
        def run_command(self, var, value):
            called.append((var, value))

    mgr.start()
    try:
        mgr.submit_command(Dev(), "power_switch", "1")
        time.sleep(0.1)
        assert called == [("power_switch", "1")]
    finally:
        mgr.stop()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_ble.py -q -k manager or submit`
Expected: FAIL — `BleManager` not defined.

- [ ] **Step 3: Implement `BleManager` + `command_bridge`**

Append to `ble.py`:

```python
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
                                self._stop, base_backoff=self.connect_backoff))
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
```

> Implementer note: `mqtt.trigger[name]` is a `threading.Event` created in `datalogger.create_listener`. `command_bridge` registers those triggers itself; a device that has a switch will have a trigger once its discovery config publishes. Handle `triggers` growing over time (re-read each loop, as above).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_ble.py -q`
Expected: PASS. Also `python3 -m py_compile ble.py`.

- [ ] **Step 5: Commit**

```bash
git add ble.py tests/test_ble.py
git commit -m "feat: BleManager (asyncio loop thread) + MQTT command bridge"
```

---

## Task 4: Wire `monitor_app.main()` onto `BleManager`

**Files:**
- Modify: `monitor_app.py`
- Modify: `connection.py` (delete thread `maintain_device`/`rotate_devices`)
- Modify: `tests/test_connection.py` (delete moved tests)

**Interfaces:**
- Consumes: `ble.BleManager`, `ble.command_bridge`, slim `SolarDevice`, `run_logger`, `supervise`, `LivenessTracker`, `DataLogger`.
- Produces: a `main(argv)` that discovers, registers devices with the manager, starts it, runs the command bridge thread, and supervises — returning the same exit codes as today.

- [ ] **Step 1: Delete the superseded thread functions and their tests**

- In `connection.py`: delete `maintain_device(...)` and `rotate_devices(...)`; keep `backoff_seconds` and `_MAX_BACKOFF_EXP`.
- In `tests/test_connection.py`: delete every test except `test_backoff_*` (the rest moved to `test_ble.py`).

Run: `python3 -m pytest tests/test_connection.py -q`
Expected: PASS (only backoff tests remain).

- [ ] **Step 2: Rewrite the device/connection section of `monitor_app.main()`**

Replace the block from `device_manager = SolarDeviceManager(...)` through the end of `main()` with:

```python
    manager = ble.BleManager(adapter=config['monitor'].get('adapter') or None)
    manager.start()

    def _handle_signal(signum, _frame):
        logging.info("Received signal %s; shutting down.", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    configured = {}
    for section in config.sections():
        mac = config.get(section, "mac", fallback=None)
        dtype = config.get(section, "type", fallback=None)
        if mac and dtype:
            configured[section] = mac.lower()

    devices = {}     # section -> SolarDevice

    def _register(section, discovered):
        if section in devices:
            return False
        mac = configured[section]
        name = discovered.get(mac)
        if name is None:
            return False
        try:
            dev = SolarDevice(mac_address=mac, logger_name=section, config=config,
                              datalogger=datalogger, queue=pipeline)
        except Exception as e:
            logging.error("Could not set up device [%s]: %s", section, e)
            return False
        dev.set_alias(name)
        trusted = config.getboolean(section, 'trusted', fallback=bool(dev.need_polling))
        manager.set_trusted(mac, trusted)
        devices[section] = dev
        liveness.expect(section)
        datalogger.set_available(section, False)
        manager.register(dev)
        logging.info("Registered device [%s] %s (trusted=%s)", section, mac, trusted)
        return True

    discovered = manager.discover(timeout=DISCOVERY_MAX_WAIT)
    logging.info("Discovered %d BLE devices", len(discovered))
    for section in configured:
        _register(section, discovered)

    if not devices:
        logging.error("No configured devices were discovered; exiting for restart.")
        stop_event.set(); manager.stop()
        return 1

    def _late_discovery_loop():
        while not stop_event.wait(REDISCOVER_INTERVAL):
            missing = [s for s in configured if s not in devices]
            if not missing:
                continue
            try:
                found = manager.discover(timeout=DISCOVERY_WINDOW)
            except Exception as e:
                logging.debug("Late discovery failed: %s", e); continue
            for section in missing:
                _register(section, found)

    threading.Thread(target=_late_discovery_loop, name="late-discovery", daemon=True).start()
    threading.Thread(target=ble.command_bridge, name="mqtt-cmd-bridge",
                     args=(datalogger, devices, manager, stop_event), daemon=True).start()

    logging.info("Supervising; terminate with Ctrl+C or SIGTERM")
    exit_code = supervise(_NullManager(), logger_future, liveness, stop_event,
                          check_interval=30.0, stale_timeout=600.0)
    stop_event.set()
    manager.stop()
    return exit_code
```

- Add at module top a tiny shim so `supervise` (which calls `device_manager.stop()`) works without gatt:

```python
class _NullManager:
    def stop(self):
        pass
```

- Update imports: `from ble import BleManager` no longer needed if using `ble.` prefix; add `import ble`; keep `from solardevice import SolarDevice` (drop `SolarDeviceManager`). Remove `run_discovery`/`discovery_complete` uses of gatt (the manager owns discovery now); you may keep `discovery_complete` (pure) and its tests, or delete if unused — check `tests/test_*` first.

> Implementer note: `supervise(device_manager, ...)` calls `device_manager.stop()` on exit; `_NullManager` satisfies that. Liveness/stale logic is unchanged; the persistent regulator keeps at least one device fresh.

- [ ] **Step 3: Run compile + unit suite**

Run: `python3 -m py_compile monitor_app.py connection.py && python3 -m pytest -q`
Expected: PASS (all remaining unit tests). `monitor_app.main()` is not unit-tested end-to-end (needs hardware); the compile + the `test_ble.py`/`test_connection.py`/config tests must pass.

- [ ] **Step 4: Commit**

```bash
git add monitor_app.py connection.py tests/test_connection.py
git commit -m "refactor: wire monitor_app onto BleManager; drop thread connection loops"
```

---

## Task 5: Dependencies + cleanup + CI parity

**Files:**
- Modify: `requirements.txt`
- Modify: `solardevice.py` (remove now-dead imports), `.github/workflows/ci.yml` (verify)

- [ ] **Step 1: Update `requirements.txt`**

```
bleak
configparser
requests
paho-mqtt
libscrc
python-dateutil
```
(Remove `gatt`, `dbus-python`, `pycairo`, `PyGObject`.)

- [ ] **Step 2: Remove dead imports**

In `solardevice.py` ensure `import gatt`, `import dbus`, `from dbus.exceptions import DBusException` are gone (grep). Add `import asyncio`.

Run: `grep -n "gatt\|dbus\|GLib\|PyGObject" solardevice.py monitor_app.py connection.py` → expect no matches (except comments referencing history).

- [ ] **Step 3: Run the exact CI commands locally**

Per `.github/workflows/ci.yml`:
```bash
python -m py_compile monitor_app.py solar-monitor.py supervisor.py solardevice.py datalogger.py duallog.py ble.py
python -m pytest -q
```
Expected: both succeed. (Update the CI `py_compile` line to include `ble.py`.)

- [ ] **Step 4: Commit**

```bash
git add requirements.txt solardevice.py .github/workflows/ci.yml
git commit -m "chore: swap gatt/dbus deps for bleak; add ble.py to CI compile"
```

---

## Task 6: Integration validation on leveld (hardware)

**Files:** none (operational). Deploy branch to `/home/pi/prog/solar-monitor`, run container, watch **file** logs (`/home/pi/solar-monitor/logs/solar-monitor.log`, not buffered docker logs).

- [ ] **Step 1:** Deploy branch + `pip install --user bleak` (uv/venv per repo). Restart container.
- [ ] **Step 2:** Confirm all configured devices connect and hold (`hcitool con` shows them; file logs show `Connected`/discovery).
- [ ] **Step 3 (acceptance):** `grep "\[battery_1\] Sending new data" logfile` shows **sustained** frames over minutes — not just an initial round. Same for battery_2. This is the fix.
- [ ] **Step 4:** Regulator power-switch command still reaches the device (`MQTT command received … → power_switch -> N` in file logs).
- [ ] **Step 5:** `sudo btmon` shows notifications still received; app now consumes them (no dbus-signal drop). Confirm HA entities update continuously.

---

## Self-Review Notes (author)

- **Spec coverage:** async bridge (Tasks 1,3), new ble.py (1,3), slim SolarDevice (2), preserved plugin surface (2 — `characteristic_write_value`, write-UUID attrs, `entities`, `device_id`, `config`, `alias`), reuse backoff_seconds (1), asyncio.Lock serialization (1,3), command bridge (3,4), unchanged datalogger/supervisor/plugins (all), deps swap (5), hardware acceptance = sustained battery frames (6). Covered.
- **Known risk to verify during impl:** `set_trusted` moved from SolarDevice(dbus) to BleManager(bluetoothctl) — verify bluetoothctl is available in the container/host context; if not, drop trust entirely (untrusted + persistent works, per this session's findings).
- **Type consistency:** write chars are UUID strings throughout (`device_write_characteristic_polling/_commands`); `notify_uuid` a single string; `client_factory(mac)->client` with `is_connected`, async `connect/disconnect/start_notify/write_gatt_char` used identically in Tasks 1 and 3.
