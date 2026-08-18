# BLE layer migration: gatt → bleak

**Status:** design approved, pending spec review
**Date:** 2026-07-20

## Goal

Replace solar-monitor's BLE transport — currently the abandoned `gatt` library —
with `bleak`, so that high-rate GATT notifications are delivered reliably. Keep
the plugin/decoder layer, the datalogger, and the supervisor unchanged.

## Motivation (diagnosed root cause)

The Meritsun batteries emit ~10 notifications/second. Captured on `leveld`:

- **HCI level** (`btmon`): battery_1 = 504, battery_2 = 503 ATT *Handle Value
  Notifications* in 50s — the controller receives them all.
- **D-Bus level** (`dbus-monitor`): BlueZ *does* emit `PropertiesChanged` for the
  battery characteristics (~23 signals/s, 344 in 15s).
- **App level**: solar-monitor logs **zero** battery data after the first round.

The break is inside the `gatt` library: it consumes notifications as D-Bus
signals on a single-threaded `dbus-python`/GLib loop (BlueZ `StartNotify`). At
this signal rate the path drops them; low-rate devices (regulator: 10/50s,
inverter: 124/50s) get through, the batteries (~500/50s) do not. This is why
polled devices work and pure-notify devices go silent after the initial round.

`bleak` uses **AcquireNotify** — a per-characteristic kernel socket (file
descriptor) instead of D-Bus signals — which handles high-rate notifications
without the dbus-signal bottleneck. This is the fix.

## Global constraints

- Do **not** change: the plugins (`plugins/*/__init__.py`), the entity decoders
  (`PowerDevice`/`BatteryDevice`/etc. in `solardevice.py`), `datalogger.py`,
  `supervisor.py`, `duallog.py`.
- Preserve the exact `SolarDevice` surface the plugins use:
  `entities`, `characteristic_write_value(value, char)`,
  `device_write_characteristic_polling`, `device_write_characteristic_commands`,
  `device_id`, `config` (with `getboolean`), `alias()`, `logger_name`.
- Keep the `persistent` / rotating config model (default: all-persistent).
- Preserve behaviour built earlier this session: per-device availability
  (online/offline), HA Device grouping, trust tied to `need_polling`, the
  connection-establishment serialization (one connect at a time).
- Python 3, `pip install --user` / venv per repo convention. Add `bleak` to
  `requirements.txt`; drop `gatt` and `dbus`/`PyGObject` where no longer needed.

## Architecture

One asyncio event loop runs in a dedicated daemon thread and owns **all** BLE.
The rest of the app stays threaded and synchronous.

```
threaded side (unchanged)                     asyncio side (new: ble.py)
--------------------------                    --------------------------
monitor_app.main()                            BleManager (owns loop + adapter)
  config, DataLogger, supervisor               discover() -> address:name
  pipeline queue  --consumed by--> run_logger   per device: maintain loop
  MQTT cmd --run_coroutine_threadsafe-->          connect (asyncio.Lock: 1 at a time)
                                                  get_services -> start_notify(cb)
  supervisor: liveness/stale -> exit code         poll loop (need_polling)
        ^ queue.put (thread-safe)                notify cb -> SolarDevice.on_notification
        |_______________________________________   -> util.notificationUpdate -> entities
```

- **Notifications and poll-writes run on the loop** and call the existing
  synchronous `SolarDevice`/plugin code.
- **Data → threaded side** via the existing thread-safe `pipeline` `queue.Queue`.
- **Commands → loop** via `run_coroutine_threadsafe`.
- `datalogger`, `supervisor`, `duallog`, plugins: untouched.

## Components

### `ble.py` (new)

- **`BleManager`**
  - Owns the asyncio loop (started in a daemon thread) and the adapter name.
  - `discover(timeout)` — `BleakScanner` sweep → `{address: advertised_name}`.
  - Spawns/supervises one maintain-task per registered device.
  - Holds the shared `asyncio.Lock` serializing connection establishment.
  - `start()`, `stop()` (cancel tasks, disconnect clients, stop loop).
  - `submit_command(section, var, value)` — thread-safe entry from MQTT; schedules
    the device's command coroutine via `run_coroutine_threadsafe`.
  - Exposes registration: `register(device)` where `device` is a `SolarDevice`.

- **`maintain_device(manager, dev, stop_event, base_backoff, max_backoff, jitter)`**
  (async) — the port of today's `connection.maintain_device`:
  1. `async with manager.connect_lock:` create `BleakClient(dev.mac,
     disconnected_callback=...)`, `await client.connect()`, resolve services,
     `await client.start_notify(dev.notify_uuid, cb)`.
  2. Release the lock (establishment done); mark device online (datalogger).
  3. Run the poll loop (if `need_polling`) until a disconnect event or stop.
  4. On failure/timeout/disconnect: mark offline, `backoff_seconds(...)`
     (reused unchanged from `connection.py`), retry.

- **`poll_loop(dev, client, interval)`** (async) — replaces the `device_poller`
  thread: each tick `data = dev.get_poll_data()` (→ `util.pollRequest()`); if
  data, `await client.write_gatt_char(dev.device_write_characteristic_polling,
  data)`. Per-device write serialization (an `asyncio.Lock` on the device) so
  acks and polls do not interleave.

- **notify callback** `cb(char, data: bytearray)` — on the loop:
  `dev.on_notification(str(char.uuid), bytes(data))`.

### Slim `SolarDevice` (in `solardevice.py`)

Stops being a `gatt.Device`. Keeps only the decoding role:

- `entities` (unchanged `PowerDevice`/`BatteryDevice`/…), plugin `module`/`util`.
- `on_notification(uuid, data)` — the body of today's
  `characteristic_value_updated`: `util.notificationUpdate`, `send_ack` →
  `ackData` write, enqueue the item list, cells, temperatures.
- `characteristic_write_value(value, char_uuid)` — schedules
  `client.write_gatt_char(char_uuid, value)` on the loop (`loop.create_task`
  when already on the loop thread). Retains the "In Progress" retry semantics.
- `_enqueue(item)` — unchanged (non-blocking `try_put`).
- Preserved attributes: `device_write_characteristic_polling`,
  `device_write_characteristic_commands` (now **UUID strings**), `device_id`,
  `config`, `alias()`, `logger_name`, `need_polling`, `send_ack`, plus
  `set_trusted()`/`set_available` hooks (via the datalogger) as today.
- `alias()` — from the BleakScanner advertised name / cached BlueZ name (bleak
  exposes this without a gatt object).

Removed: `gatt.Device` inheritance, `connect_succeeded`/`connect_failed`/
`services_resolved`/`disconnect_succeeded`, the `threading.Event` connect
signalling (`_connect_event`, `_disconnect_event`, `_signal_connect_result`),
the `device_poller`/`mqtt_poller` threads (the poll loop and command coro replace
them; the MQTT trigger still fans in via `submit_command`).

### `connection.py`

Keep `backoff_seconds` (pure) and its unit tests. The thread-based
`maintain_device`/`rotate_devices` are removed (superseded by the async versions
in `ble.py`); their tests are re-pointed at the async versions with a fake client.

### `monitor_app.main()`

- Remove: the GLib `loop_thread`, per-device `threading.Thread`s, `connect_lock`,
  `_make_connect_fn`/`_make_rotating_connect_fn`/`_rotating_*`.
- Add: build `BleManager(adapter)`; `run_discovery` via `manager.discover()`;
  for each configured+discovered device create a slim `SolarDevice`, set trust
  (need_polling default), mark offline, `manager.register(dev)`; `manager.start()`.
- Late discovery: `manager` periodically re-scans and registers missing devices.
- The `pipeline` queue, `DataLogger`, `run_logger`, and `supervise(...)` calls are
  unchanged. MQTT command trigger routes to `manager.submit_command`.

## Data flow details

- **Notification:** `start_notify` (AcquireNotify) → `cb` on loop →
  `on_notification` → `util.notificationUpdate` → `entities.*` setters →
  `_enqueue` → `pipeline` → `run_logger` → datalogger (MQTT/HTTP). Callback kept
  lean (decode + non-blocking put); it cannot stall the loop.
- **Poll write:** `poll_loop` → `pollRequest()` → `write_gatt_char`.
- **Command:** MQTT `on_message` (threaded, in datalogger) appends to
  `datalogger.mqtt.sets[section]` and fires the per-section trigger `Event` — as
  today. The per-device `mqtt_poller` thread is replaced by a single lightweight
  bridge thread started in `monitor_app` (or an async task waking on the trigger)
  that drains `sets[section]` and calls `manager.submit_command(section, var,
  value)` → `run_coroutine_threadsafe` → command coro → `cmdRequest()` →
  `write_gatt_char`. The datalogger's `sets`/`trigger` interface is unchanged.
- **Ack:** inside `on_notification`, `characteristic_write_value` schedules the
  ack write on the loop (VEDirect path).

## Error handling

- Connect failure / timeout / `BleakError`: log, mark offline, `backoff_seconds`
  + jitter, retry. Establishment stays serialized by the `asyncio.Lock`.
- Unexpected disconnect: bleak `disconnected_callback` sets the device's event →
  maintain loop reconnects.
- Loop/adapter fatal error: surfaced so the process exits non-zero → docker/
  systemd restart (supervisor's role preserved).
- Dead device (never advertises): discovery never finds it → stays offline →
  datalogger publishes availability `offline` (HA shows Unavailable).
- Liveness/stale detection: unchanged (`supervisor.supervise`).

## Testing

- **Unit (no hardware):**
  - `backoff_seconds` — existing tests unchanged.
  - Async `maintain_device` against a **fake BleakClient** (connect raises /
    resolves / drops on cue): asserts backoff schedule, connect-lock
    serialization, `start_notify` registered, poll-writes issued, offline/online
    transitions. Mirrors today's `test_connection.py`.
  - Decoders/plugins remain independently testable (unchanged).
- **Integration (leveld hardware):**
  - Meritsun batteries stream **continuously** (file logs show sustained frames
    well past the initial round) — the acceptance criterion.
  - All configured devices connect and hold; regulator/inverter still stream.
  - Regulator power-switch command still reaches the device.
  - Re-check with `btmon` (notifications received) and confirm the app now
    consumes them (no dbus-signal drop).

## Out of scope (tracked separately)

- Plugin/decoder logic, datalogger, supervisor, duallog — untouched.
- `PYTHONUNBUFFERED` stdout fix (so `docker logs` is live).
- SolarLink switch-state field (state currently reads the app-switch register).

## Rollout

leveld is remote and reboot-prone; validate by deploying the branch to
`/home/pi/prog/solar-monitor` and running the container, watching the **file**
logs (not buffered docker stdout). Keep the branch `feat/connection-reliability`
work; this migration is a further stage on it (or a dedicated `feat/bleak`
branch if preferred).
