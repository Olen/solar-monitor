# Phase 0 + Phase 1 Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the two config hotfixes that break fresh installs (Phase 0, issue #43), then make the daemon fail loudly or self-heal instead of dying silently while alive (Phase 1, issue #44).

**Architecture:** New Phase-1 logic lands in a small, `gatt`-free module `supervisor.py` so it is unit-testable today without Bluetooth hardware. `solar-monitor.py` and `solardevice.py` are edited only to *call into* that module and to replace blocking/fatal patterns with non-blocking, exit-on-failure ones. A `tests/conftest.py` stubs `gatt`/`gi` so the BLE modules import under pytest.

**Tech Stack:** Python 3, pytest 9.x (dev-only, in a venv), `configparser` (stdlib), `queue`/`threading`/`signal` (stdlib), `gi.repository.GLib` (via PyGObject, already a runtime dep through `gatt`), `requests`.

## Global Constraints

- **No live hardware.** No test may require a real BLE device, adapter, or broker. `gatt` is not importable in dev/CI — it is stubbed for tests.
- **Dev deps via `uv` or `venv`, never `pip install --user`** (user instruction, overrides the global CLAUDE.md convention for this repo).
- **Keep the `gatt` library this phase.** No migration to `bleak` (deferred — needs hardware).
- **No `gatt`/dbus callback may ever block.** No `time.sleep()` and no blocking `queue.put()` inside any `gatt` callback (`connect_failed`, `disconnect_succeeded`, `characteristic_value_updated`, `services_resolved`, `connect`).
- **The process must exit non-zero on any unrecoverable state** so systemd's `Restart=always` can act. Never enter a state that is alive-but-idle.
- **Runtime deps stay in `requirements.txt`.** Do not add pytest to `requirements.txt`; it is dev-only.
- Every commit message ends with the repo's standard trailer:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

## Branching

- **Phase 0** (Tasks 1–3) is a self-contained hotfix. Do it on branch `fix/shipped-config-hotfix` off `master` and open its own PR referencing #43. It has no dependency on Phase 1.
- **Phase 1** (Tasks 4–11) goes on branch `feat/supervision-liveness` off `master` (rebase after Phase 0 merges), PR referencing #44.

## File Structure

- **Create `supervisor.py`** — `gatt`-free. Owns: `try_put()`, `run_logger()`, `LivenessTracker`. One responsibility: the queue/consumer/liveness logic that today is tangled into module scope and dbus callbacks. Unit-tested directly.
- **Create `tests/conftest.py`** — installs fake `gatt`, `gatt.errors`, and (where needed) `gi` modules into `sys.modules` so `solardevice.py` imports under pytest.
- **Create `tests/test_supervisor.py`, `tests/test_shipped_config.py`, `tests/test_solardevice_enqueue.py`, `tests/test_datalogger_http.py`, `tests/test_reconnect.py`, `tests/test_main_supervision.py`** — one test module per behavior area.
- **Modify `solar-monitor.ini.dist`** — the two Phase 0 config fixes.
- **Modify `solardevice.py`** — queue.put → non-blocking enqueue; reconnect via GLib scheduling instead of sleep+recurse.
- **Modify `datalogger.py`** — `requests.post` timeout + correct exception class.
- **Modify `solar-monitor.py`** — import `run_logger`/`LivenessTracker` from `supervisor`; signal handling; zero-devices exit; supervisory main loop with watchdog.
- **Create `pytest.ini`** — minimal pytest config (test path + the stub is via conftest).

---

## Task 1: Test harness bootstrap

**Files:**
- Create: `pytest.ini`
- Create: `tests/__init__.py` (empty)
- Create: `tests/conftest.py`
- Create: `tests/test_harness_smoke.py`
- Modify: `.gitignore` (add `.venv/` and `.pytest_cache/` if absent)

**Interfaces:**
- Produces: a working `pytest` invocation, and a `conftest.py` that makes `import gatt` and `import solardevice` succeed with no hardware.

- [ ] **Step 1: Create the venv and install pytest (dev-only)**

```bash
cd /home/olen/prog/solar-monitor
python3 -m venv .venv
. .venv/bin/activate
pip install pytest
```

(If `uv` is preferred: `uv venv .venv && . .venv/bin/activate && uv pip install pytest`.)

- [ ] **Step 2: Add pytest config**

Create `pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
```

- [ ] **Step 3: Add the gatt/gi stub conftest**

Create `tests/__init__.py` (empty), and `tests/conftest.py`:

```python
"""Test-only stubs so the BLE modules import without hardware.

`gatt` is a Linux/dbus/BlueZ library that cannot be imported in CI. We install
minimal fakes into sys.modules BEFORE any test imports solardevice.py.
"""
import sys
import types


def _install_gatt_stub():
    if "gatt" in sys.modules:
        return

    errors = types.ModuleType("gatt.errors")

    class _GattError(Exception):
        pass

    class InProgress(_GattError):
        pass

    class Failed(_GattError):
        pass

    errors.InProgress = InProgress
    errors.Failed = Failed

    gatt = types.ModuleType("gatt")

    class DeviceManager:
        def __init__(self, *args, **kwargs):
            pass

    class Device:
        def __init__(self, *args, **kwargs):
            pass

        def connect(self):
            pass

        def connect_succeeded(self):
            pass

        def connect_failed(self, error):
            pass

        def disconnect_succeeded(self):
            pass

        def services_resolved(self):
            pass

        def characteristic_value_updated(self, characteristic, value):
            pass

    gatt.DeviceManager = DeviceManager
    gatt.Device = Device
    gatt.errors = errors

    sys.modules["gatt"] = gatt
    sys.modules["gatt.errors"] = errors


_install_gatt_stub()
```

- [ ] **Step 4: Write the smoke test**

Create `tests/test_harness_smoke.py`:

```python
def test_gatt_stub_lets_solardevice_import():
    import solardevice
    assert hasattr(solardevice, "SolarDevice")
    assert hasattr(solardevice, "SolarDeviceManager")
```

- [ ] **Step 5: Run it and verify it passes**

Run: `. .venv/bin/activate && python -m pytest tests/test_harness_smoke.py -v`
Expected: PASS (1 passed)

- [ ] **Step 6: Commit**

```bash
git add pytest.ini tests/__init__.py tests/conftest.py tests/test_harness_smoke.py .gitignore
git commit -m "test: bootstrap pytest harness with gatt stub

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Phase 0 — fix the non-existent Victron plugin name

**Files:**
- Modify: `solar-monitor.ini.dist:32,37` (the two `type = VictronConnect` lines)
- Create: `tests/test_shipped_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: a shipped `.dist` whose every `type =` names a real directory under `plugins/`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_shipped_config.py`:

```python
import configparser
import os

DIST = os.path.join(os.path.dirname(os.path.dirname(__file__)), "solar-monitor.ini.dist")


def _read_dist():
    cp = configparser.ConfigParser()
    read = cp.read(DIST)
    assert read, "solar-monitor.ini.dist should be readable"
    return cp


def test_every_device_type_maps_to_a_real_plugin():
    cp = _read_dist()
    plugins_dir = os.path.join(os.path.dirname(DIST), "plugins")
    for section in cp.sections():
        dtype = cp.get(section, "type", fallback=None)
        if not dtype:
            continue
        assert os.path.isdir(os.path.join(plugins_dir, dtype)), (
            f"[{section}] type = {dtype} has no plugins/{dtype} directory"
        )
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_shipped_config.py::test_every_device_type_maps_to_a_real_plugin -v`
Expected: FAIL — `type = VictronConnect has no plugins/VictronConnect directory`

- [ ] **Step 3: Fix the config**

In `solar-monitor.ini.dist`, change both occurrences of:

```ini
type = VictronConnect
```

to:

```ini
type = VEDirect
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python -m pytest tests/test_shipped_config.py::test_every_device_type_maps_to_a_real_plugin -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add solar-monitor.ini.dist tests/test_shipped_config.py
git commit -m "fix: correct VictronConnect -> VEDirect in shipped ini (#43)

VictronConnect is a plugin name that never existed; the shipped config
made Victron devices fail to import silently.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Phase 0 — disarm the placeholder datalogger and dummy token

**Files:**
- Modify: `solar-monitor.ini.dist:42-44` (the `[datalogger]` block)
- Modify: `tests/test_shipped_config.py` (add two tests)

**Interfaces:**
- Consumes: `_read_dist()` from Task 2.
- Produces: a `.dist` with no active `[datalogger] url` and no credential-looking token.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_shipped_config.py`:

```python
def test_no_active_datalogger_url_by_default():
    cp = _read_dist()
    # A fresh install must not POST to a placeholder host on first run.
    url = cp.get("datalogger", "url", fallback=None) if cp.has_section("datalogger") else None
    assert not url, f"datalogger url should be commented out by default, got {url!r}"


def test_no_credential_looking_token():
    cp = _read_dist()
    token = cp.get("datalogger", "token", fallback="") if cp.has_section("datalogger") else ""
    assert token in ("", "your-token-here"), (
        f"shipped token should be a placeholder, got {token!r}"
    )
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_shipped_config.py -v`
Expected: both new tests FAIL (url is `http://server/solar/api/`, token is the MD5-looking value).

- [ ] **Step 3: Edit the config**

In `solar-monitor.ini.dist`, change the `[datalogger]` block from:

```ini
[datalogger]
url = http://server/solar/api/
token = 39129e20be0503937cb72a5f719337cc
```

to (comment out `url`, use a placeholder token, and switch the example to https):

```ini
[datalogger]
# Uncomment and point this at your own HTTP ingest endpoint to enable the
# JSON/HTTP datalogger. Leave commented out to use MQTT only.
# url = https://server.example.com/solar/api/
# token = your-token-here
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/test_shipped_config.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add solar-monitor.ini.dist tests/test_shipped_config.py
git commit -m "fix: comment out placeholder datalogger + dummy token in ini (#43)

A default install following the README hit an unreachable placeholder host,
which triggered the silent consumer-death hang.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> **Phase 0 is now complete.** Open the PR for `fix/shipped-config-hotfix` referencing #43. Tasks 4+ (Phase 1) can proceed in parallel on a separate branch.

---

## Task 4: `supervisor.try_put` — non-blocking enqueue

**Files:**
- Create: `supervisor.py`
- Create: `tests/test_supervisor.py`

**Interfaces:**
- Produces: `try_put(q, item) -> bool` — returns `True` if enqueued, `False` if the queue was full (never blocks, never raises `queue.Full`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_supervisor.py`:

```python
import queue
import supervisor


def test_try_put_returns_true_when_space():
    q = queue.Queue(maxsize=2)
    assert supervisor.try_put(q, ("a", "b", 1)) is True
    assert q.qsize() == 1


def test_try_put_returns_false_when_full_and_does_not_block():
    q = queue.Queue(maxsize=1)
    assert supervisor.try_put(q, ("a", "b", 1)) is True
    # Second put would block a blocking put() forever; try_put must return False.
    assert supervisor.try_put(q, ("c", "d", 2)) is False
    assert q.qsize() == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_supervisor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'supervisor'`

- [ ] **Step 3: Create the module with the minimal implementation**

Create `supervisor.py`:

```python
"""Hardware-free supervision helpers: queueing, the logger loop, liveness.

This module deliberately does NOT import gatt so it can be unit-tested without
Bluetooth. solar-monitor.py and solardevice.py import from here.
"""
import logging
import queue
import time


def try_put(q, item):
    """Enqueue without ever blocking. Returns True on success, False if full."""
    try:
        q.put_nowait(item)
        return True
    except queue.Full:
        return False
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_supervisor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add supervisor.py tests/test_supervisor.py
git commit -m "feat: add supervisor.try_put non-blocking enqueue helper (#44)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Replace blocking `queue.put()` in solardevice.py with drop-on-full

**Files:**
- Modify: `solardevice.py:60-73` (init — add drop counter), `:238`, `:245-246`, `:255`, `:263`, `:716` (the six `self.queue.put(...)` sites)
- Create: `tests/test_solardevice_enqueue.py`

**Interfaces:**
- Consumes: `supervisor.try_put`.
- Produces: `SolarDevice._enqueue(self, item)` — non-blocking; increments `self._dropped` and warns periodically when the queue is full.

- [ ] **Step 1: Write the failing test**

Create `tests/test_solardevice_enqueue.py`:

```python
import queue
import solardevice  # conftest stubs gatt


def _make_device():
    # SolarDevice.__init__ returns early (no plugin import) when type is None,
    # which is exactly the lightweight object we want for enqueue tests.
    dev = solardevice.SolarDevice(
        mac_address="11:22:33:44:55:66", manager=None, queue=queue.Queue(maxsize=1)
    )
    return dev


def test_enqueue_puts_item_when_space():
    dev = _make_device()
    dev._enqueue(("regulator", "voltage", 13.2))
    assert dev.queue.qsize() == 1
    assert dev._dropped == 0


def test_enqueue_drops_and_counts_when_full_without_blocking():
    dev = _make_device()
    dev._enqueue(("regulator", "voltage", 13.2))   # fills the maxsize=1 queue
    dev._enqueue(("regulator", "current", 5.0))    # would block a real put(); must drop
    assert dev.queue.qsize() == 1
    assert dev._dropped == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_solardevice_enqueue.py -v`
Expected: FAIL — `AttributeError: 'SolarDevice' object has no attribute '_enqueue'`

- [ ] **Step 3: Add the import and drop counter**

In `solardevice.py`, add near the top imports (after `import logging`, around line 17):

```python
from supervisor import try_put
```

In `SolarDevice.__init__`, immediately after `self.queue = queue` (line 60), add:

```python
        self._dropped = 0
```

- [ ] **Step 4: Add the `_enqueue` method**

In `solardevice.py`, add this method to `SolarDevice` (e.g. directly above `characteristic_value_updated`, around line 217):

```python
    def _enqueue(self, item):
        """Non-blocking enqueue. Dropping a sample is always better than
        blocking the dbus main-loop thread inside a gatt callback."""
        if not try_put(self.queue, item):
            self._dropped += 1
            if self._dropped % 100 == 1:
                logging.warning(
                    "[{}] Log queue full; dropped {} samples (consumer stalled?)".format(
                        self.logger_name, self._dropped
                    )
                )
```

- [ ] **Step 5: Replace the six put sites**

In `characteristic_value_updated` and the `power_switch` setter, replace every `self.queue.put(X)` with `self._enqueue(X)`. Exact replacements:

- Line 238: `self.queue.put((self.logger_name, item, getattr(self.entities, item)))` → `self._enqueue((self.logger_name, item, getattr(self.entities, item)))`
- Line 245: `self.queue.put((self.logger_name, 'temperature', self.entities.temperature_celsius))` → `self._enqueue((self.logger_name, 'temperature', self.entities.temperature_celsius))`
- Line 246: `self.queue.put((self.logger_name, 'battery_temperature', self.entities.battery_temperature_celsius))` → `self._enqueue((self.logger_name, 'battery_temperature', self.entities.battery_temperature_celsius))`
- Line 255: `self.queue.put((self.logger_name, 'cell_{}'.format(cell), self.entities.cell_mvoltage[cell]['val']))` → `self._enqueue((self.logger_name, 'cell_{}'.format(cell), self.entities.cell_mvoltage[cell]['val']))`
- Line 263: `self.queue.put((self.logger_name, 'cell_{}_voltage'.format(cell), self.entities.cell_voltage[cell]['val']))` → `self._enqueue((self.logger_name, 'cell_{}_voltage'.format(cell), self.entities.cell_voltage[cell]['val']))`
- Line 716 (in the `power_switch` setter): `self.queue.put((self.logger_name, 'power_switch', self.power_switch))` → `self._enqueue((self.name, 'power_switch', self.power_switch))`
  - NOTE: `PowerDevice` has `self.name`, not `self.logger_name`; this also fixes the confirmed `AttributeError` finding at that site.

- [ ] **Step 6: Run to verify it passes**

Run: `python -m pytest tests/test_solardevice_enqueue.py -v`
Expected: PASS

- [ ] **Step 7: Guard against a regression — assert no blocking put remains**

Add to `tests/test_solardevice_enqueue.py`:

```python
import re


def test_no_blocking_queue_put_calls_remain():
    with open("solardevice.py") as fh:
        src = fh.read()
    # self.queue.put( ... ) blocks; only self.queue.put_nowait / try_put allowed.
    assert not re.search(r"self\.queue\.put\(", src), (
        "found a blocking self.queue.put( in solardevice.py"
    )
```

Run: `python -m pytest tests/test_solardevice_enqueue.py -v` → PASS

- [ ] **Step 8: Commit**

```bash
git add solardevice.py tests/test_solardevice_enqueue.py
git commit -m "fix: non-blocking enqueue in solardevice, drop-on-full (#44)

Blocking queue.put() inside the dbus callback froze the whole main loop when
the consumer stalled. Also fixes the power_switch setter's self.logger_name
AttributeError (PowerDevice has self.name).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `supervisor.run_logger` — a consumer loop that never dies

**Files:**
- Modify: `supervisor.py`
- Modify: `tests/test_supervisor.py`

**Interfaces:**
- Produces: `run_logger(queue_obj, datalogger, stop_event, on_item=None, get_time=time.time)` — drains the queue, calls `datalogger.log(name, item, value)`, and NEVER raises/exits on a per-item exception (logs and continues). Returns when `stop_event` is set. Calls `on_item(logger_name)` after each successful log (for liveness).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_supervisor.py`:

```python
import threading


class _FlakyLogger:
    def __init__(self):
        self.logged = []
        self.calls = 0

    def log(self, name, item, value):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient sink failure")
        self.logged.append((name, item, value))


def test_run_logger_survives_a_sink_exception_and_keeps_going():
    q = queue.Queue()
    q.put(("reg", "voltage", 1))   # first call raises
    q.put(("reg", "voltage", 2))   # must still be processed
    stop = threading.Event()
    logger = _FlakyLogger()
    seen = []

    t = threading.Thread(
        target=supervisor.run_logger,
        args=(q, logger, stop),
        kwargs={"on_item": seen.append},
    )
    t.start()
    # wait until both items drained, then stop
    for _ in range(100):
        if logger.logged:
            break
        time.sleep(0.02)
    stop.set()
    t.join(timeout=3)

    assert not t.is_alive()               # loop did not die on the exception
    assert ("reg", "voltage", 2) in logger.logged
    assert "reg" in seen                  # on_item fired for the successful log


def test_run_logger_stops_when_event_set():
    q = queue.Queue()
    stop = threading.Event()
    stop.set()
    # Should return promptly because stop is already set.
    supervisor.run_logger(q, _FlakyLogger(), stop)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_supervisor.py -v`
Expected: FAIL — `AttributeError: module 'supervisor' has no attribute 'run_logger'`

- [ ] **Step 3: Implement `run_logger`**

Add to `supervisor.py`:

```python
def run_logger(queue_obj, datalogger, stop_event, on_item=None, get_time=time.time):
    """Drain the queue into datalogger.log(), forever, until stop_event is set.

    A per-item failure (sink down, decode bug) is logged and skipped — it must
    NEVER terminate this loop, because the producers block behind a full queue.
    """
    last_report = get_time()
    while not stop_event.is_set():
        try:
            logger_name, item, value = queue_obj.get(timeout=1.0)
        except queue.Empty:
            continue
        try:
            datalogger.log(logger_name, item, value)
            if on_item is not None:
                on_item(logger_name)
        except Exception as e:
            logging.error("datalogger.log failed for %s/%s: %s", logger_name, item, e)

        now = get_time()
        if now > last_report + 1 and not queue_obj.empty():
            logging.debug("Queue size = %s", queue_obj.qsize())
            last_report = now
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_supervisor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add supervisor.py tests/test_supervisor.py
git commit -m "feat: supervisor.run_logger consumer that survives sink failures (#44)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: `supervisor.LivenessTracker` — staleness detection

**Files:**
- Modify: `supervisor.py`
- Modify: `tests/test_supervisor.py`

**Interfaces:**
- Produces: `LivenessTracker(get_time=time.time)` with `.expect(name)`, `.record(name)`, `.stale(timeout_s) -> list[str]`, `.any_expected() -> bool`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_supervisor.py`:

```python
def test_liveness_reports_stale_after_timeout():
    clock = {"t": 1000.0}
    lt = supervisor.LivenessTracker(get_time=lambda: clock["t"])
    lt.expect("reg")
    lt.record("reg")            # fresh at t=1000
    clock["t"] = 1000.0 + 40
    assert lt.stale(30) == ["reg"]      # 40s > 30s timeout


def test_liveness_not_stale_when_recent():
    clock = {"t": 500.0}
    lt = supervisor.LivenessTracker(get_time=lambda: clock["t"])
    lt.expect("reg")
    clock["t"] = 500.0 + 10
    lt.record("reg")            # recorded at t=510
    clock["t"] = 500.0 + 20
    assert lt.stale(30) == []           # only 10s since last record


def test_expect_seeds_a_baseline_so_a_never_reporting_device_goes_stale():
    clock = {"t": 0.0}
    lt = supervisor.LivenessTracker(get_time=lambda: clock["t"])
    lt.expect("reg")            # baseline at t=0, never records
    clock["t"] = 100.0
    assert lt.stale(30) == ["reg"]
    assert lt.any_expected() is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_supervisor.py -v`
Expected: FAIL — `AttributeError: module 'supervisor' has no attribute 'LivenessTracker'`

- [ ] **Step 3: Implement `LivenessTracker`**

Add to `supervisor.py`:

```python
class LivenessTracker:
    """Tracks the last time each expected device produced a reading."""

    def __init__(self, get_time=time.time):
        self._get_time = get_time
        self._last = {}

    def expect(self, name):
        """Register a device we require data from; seeds a baseline timestamp."""
        self._last.setdefault(name, self._get_time())

    def record(self, name):
        """Note that `name` just produced a reading."""
        self._last[name] = self._get_time()

    def stale(self, timeout_s):
        """Return the names with no reading within the last `timeout_s` seconds."""
        now = self._get_time()
        return [n for n, t in self._last.items() if now - t > timeout_s]

    def any_expected(self):
        return bool(self._last)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_supervisor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add supervisor.py tests/test_supervisor.py
git commit -m "feat: supervisor.LivenessTracker staleness detection (#44)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Give `requests.post` a timeout and catch the right exception

**Files:**
- Modify: `datalogger.py` (the `send_to_server` HTTP branch — the `requests.post` + `except TimeoutError`)
- Create: `tests/test_datalogger_http.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `DataLogger.send_to_server` never raises on a network error and always passes a `timeout` to `requests.post`.

- [ ] **Step 1: Confirm the current code**

Read `datalogger.py` around the HTTP POST (the `send_to_server` method). Current shape:

```python
            try:
                response = requests.post(url=self.url, json=payload, headers=header)
            except TimeoutError:
                logging.error("Connection to {} timed out!".format(self.url))
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_datalogger_http.py`:

```python
import types
import sys
import requests
import datalogger


def _make_url_only_logger(monkeypatch_url="http://unreachable.invalid/api"):
    """Build a DataLogger with only the HTTP sink wired, bypassing __init__
    (which needs a full config). We set just the attributes send_to_server uses."""
    dl = datalogger.DataLogger.__new__(datalogger.DataLogger)
    dl.url = monkeypatch_url
    dl.token = "t"
    dl.mqtt = None
    dl.logdata = {}
    return dl


def test_post_is_called_with_a_timeout(monkeypatch):
    calls = {}

    def fake_post(*args, **kwargs):
        calls.update(kwargs)

        class _R:
            status_code = 200
        return _R()

    monkeypatch.setattr(requests, "post", fake_post)
    dl = _make_url_only_logger()
    dl.send_to_server("reg", "voltage", 13.2)
    assert "timeout" in calls and calls["timeout"] is not None


def test_connection_error_is_swallowed_not_raised(monkeypatch):
    def boom(*args, **kwargs):
        raise requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr(requests, "post", boom)
    dl = _make_url_only_logger()
    # Must NOT raise — a network blip must never propagate to the consumer loop.
    dl.send_to_server("reg", "voltage", 13.2)
```

- [ ] **Step 3: Run to verify it fails**

Run: `python -m pytest tests/test_datalogger_http.py -v`
Expected: `test_post_is_called_with_a_timeout` FAILS (no timeout kwarg); `test_connection_error_is_swallowed_not_raised` FAILS (ConnectionError is not a TimeoutError, so it propagates).

- [ ] **Step 4: Fix the POST**

In `datalogger.py`, replace the try/except around `requests.post` with:

```python
            try:
                response = requests.post(url=self.url, json=payload, headers=header, timeout=(5, 10))
            except requests.exceptions.RequestException as e:
                logging.error("Failed to POST to {}: {}".format(self.url, e))
```

- [ ] **Step 5: Run to verify it passes**

Run: `python -m pytest tests/test_datalogger_http.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add datalogger.py tests/test_datalogger_http.py
git commit -m "fix: timeout + correct exception on datalogger HTTP POST (#44)

requests raises ConnectionError (OSError), not builtin TimeoutError; the old
handler let network errors escape and kill the consumer thread. Also adds a
timeout so a hung endpoint can't stall the consumer forever.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Reconnect via GLib scheduling instead of sleep+recurse

**Files:**
- Modify: `solardevice.py:114-121` (`connect` — drop the blocking sleep), `:127-160` (`connect_failed`/`disconnect_succeeded` — schedule instead of sleep+connect)
- Create: `tests/test_reconnect.py`

**Interfaces:**
- Consumes: `gi.repository.GLib.timeout_add_seconds`.
- Produces: `SolarDevice._schedule_reconnect(self)` — schedules `self.connect()` on the main loop after a delay and returns immediately; never recurses, never sleeps.

- [ ] **Step 1: Extend the test stub with a GLib spy**

In `tests/conftest.py`, add a fixture that installs a fake `gi.repository.GLib` capturing scheduled callbacks. Append to the file:

```python
import pytest


class _FakeGLib:
    def __init__(self):
        self.scheduled = []  # list of (delay, callback)

    def timeout_add_seconds(self, delay, callback):
        self.scheduled.append((delay, callback))
        return 1  # a fake source id


@pytest.fixture
def fake_glib(monkeypatch):
    import solardevice
    fake = _FakeGLib()
    monkeypatch.setattr(solardevice, "GLib", fake, raising=False)
    return fake
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_reconnect.py`:

```python
import solardevice


def _reconnecting_device():
    dev = solardevice.SolarDevice(mac_address="aa:bb:cc:dd:ee:ff", manager=None)
    dev.auto_reconnect = True
    dev.logger_name = "reg"
    dev.poller_thread = None
    dev.command_thread = None
    return dev


def test_schedule_reconnect_uses_glib_and_does_not_recurse(fake_glib):
    dev = _reconnecting_device()
    connect_calls = {"n": 0}
    dev.connect = lambda: connect_calls.__setitem__("n", connect_calls["n"] + 1)

    dev._schedule_reconnect()

    # It scheduled a delayed retry rather than calling connect() synchronously.
    assert connect_calls["n"] == 0
    assert len(fake_glib.scheduled) == 1
    delay, cb = fake_glib.scheduled[0]
    assert delay == 10
    # The scheduled callback returns False (one-shot) and calls connect once.
    assert cb() is False
    assert connect_calls["n"] == 1


def test_schedule_reconnect_noop_when_disabled(fake_glib):
    dev = _reconnecting_device()
    dev.auto_reconnect = False
    dev._schedule_reconnect()
    assert fake_glib.scheduled == []
```

- [ ] **Step 3: Run to verify it fails**

Run: `python -m pytest tests/test_reconnect.py -v`
Expected: FAIL — `AttributeError: 'SolarDevice' object has no attribute '_schedule_reconnect'`

- [ ] **Step 4: Import GLib in solardevice.py**

Near the top of `solardevice.py` (after `import gatt`, around line 11), add:

```python
from gi.repository import GLib
```

- [ ] **Step 5: Add `_schedule_reconnect` and use it**

Add the method to `SolarDevice`:

```python
    def _schedule_reconnect(self):
        """Schedule a reconnect on the main loop. Never sleeps, never recurses —
        connect_failed -> connect() -> connect_failed() is a recursive cycle that
        blows the stack after ~an hour of a device being unreachable."""
        if not self.auto_reconnect:
            return
        logging.info("[{}] Reconnecting in 10 seconds...".format(self.logger_name))
        GLib.timeout_add_seconds(10, self._reconnect_cb)

    def _reconnect_cb(self):
        self.connect()
        return False  # one-shot: do not repeat
```

In `connect_failed` (lines 138-142), replace:

```python
        if self.auto_reconnect:
            logging.info("[{}] Reconnecting in 10 seconds...".format(self.logger_name))
            # self.sleeper.wait(10)
            time.sleep(10)
            self.connect()
```

with:

```python
        self._schedule_reconnect()
```

In `disconnect_succeeded` (lines 156-160), replace:

```python
        if self.auto_reconnect:
            logging.info("[{}] Reconnecting in 10 seconds".format(self.logger_name))
            # self.sleeper.wait(10)
            time.sleep(10)
            self.connect()
```

with:

```python
        self._schedule_reconnect()
```

In `connect` (lines 116-121), remove the blocking sleep in the DBusException handler:

```python
        try:
            super().connect()
        except DBusException as e:
            logging.error("[{}] DBUS-error: {}".format(self.logger_name, e))
            self._schedule_reconnect()
```

- [ ] **Step 6: Run to verify it passes**

Run: `python -m pytest tests/test_reconnect.py -v`
Expected: PASS

- [ ] **Step 7: Guard against a regression — no `time.sleep` in reconnect callbacks**

Add to `tests/test_reconnect.py`:

```python
import inspect


def test_no_time_sleep_in_gatt_callbacks():
    src = inspect.getsource(solardevice.SolarDevice.connect_failed)
    src += inspect.getsource(solardevice.SolarDevice.disconnect_succeeded)
    assert "time.sleep" not in src, "gatt callback must not block on time.sleep"
```

Run: `python -m pytest tests/test_reconnect.py -v` → PASS

- [ ] **Step 8: Commit**

```bash
git add solardevice.py tests/conftest.py tests/test_reconnect.py
git commit -m "fix: schedule reconnect on GLib loop, killing the recursive retry (#44)

connect_failed -> time.sleep(10) -> connect() -> connect_failed() recursed until
RecursionError (~55 min) and blocked the shared main loop 10s per cycle. Schedule
a one-shot GLib timeout instead.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Wire the supervisor, signals, and zero-device exit into solar-monitor.py

**Files:**
- Modify: `solar-monitor.py` — replace the inline `threaded_logger` (lines 74-95) with `supervisor.run_logger`; add signal handling and the supervisory watchdog loop (replacing lines 153-165); make zero-matched-devices exit non-zero.
- Create: `tests/test_main_supervision.py` (tests the extracted supervisory loop with fakes)

**Interfaces:**
- Consumes: `supervisor.run_logger`, `supervisor.LivenessTracker`.
- Produces: `supervise(device_manager, logger_future, liveness, stop_event, check_interval, stale_timeout, get_time=time.time) -> int` — a hardware-free supervisory loop returning an exit code (0 = clean stop, 1 = unrecoverable), extracted into `supervisor.py` so it is testable.

> This task extracts only the *supervisory decision loop* into `supervisor.py`. The
> full `main()` extraction (importing solar-monitor.py under test) is Phase 2 and is
> out of scope here; `solar-monitor.py` module scope stays as-is except for the
> edits below.

- [ ] **Step 1: Write the failing test for `supervise`**

Create `tests/test_main_supervision.py`:

```python
import threading
import supervisor


class _FakeFuture:
    def __init__(self, done=False):
        self._done = done

    def done(self):
        return self._done


class _FakeDM:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


def test_supervise_exits_1_when_logger_future_dies():
    dm = _FakeDM()
    fut = _FakeFuture(done=True)  # consumer thread died
    lt = supervisor.LivenessTracker()
    stop = threading.Event()
    rc = supervisor.supervise(dm, fut, lt, stop, check_interval=0.01, stale_timeout=999)
    assert rc == 1
    assert dm.stopped is True


def test_supervise_exits_1_when_all_devices_stale():
    clock = {"t": 0.0}
    lt = supervisor.LivenessTracker(get_time=lambda: clock["t"])
    lt.expect("reg")
    dm = _FakeDM()
    fut = _FakeFuture(done=False)
    stop = threading.Event()

    # advance the clock past the stale timeout on the first check
    def tick():
        clock["t"] += 100

    rc = supervisor.supervise(
        dm, fut, lt, stop, check_interval=0.01, stale_timeout=30,
        get_time=lambda: clock["t"], on_tick=tick,
    )
    assert rc == 1


def test_supervise_returns_0_on_clean_stop():
    dm = _FakeDM()
    fut = _FakeFuture(done=False)
    lt = supervisor.LivenessTracker()  # nothing expected -> never stale
    stop = threading.Event()
    stop.set()  # already asked to stop
    rc = supervisor.supervise(dm, fut, lt, stop, check_interval=0.01, stale_timeout=30)
    assert rc == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_main_supervision.py -v`
Expected: FAIL — `AttributeError: module 'supervisor' has no attribute 'supervise'`

- [ ] **Step 3: Implement `supervise`**

Add to `supervisor.py`:

```python
def supervise(device_manager, logger_future, liveness, stop_event,
              check_interval=30.0, stale_timeout=600.0, get_time=time.time,
              on_tick=None):
    """Watch the daemon's health until stop_event, then return an exit code.

    Returns 1 (so systemd restarts) if the consumer thread died or every
    expected device has gone stale; 0 on a clean requested stop.
    """
    while not stop_event.wait(check_interval):
        if on_tick is not None:
            on_tick()
        if logger_future is not None and logger_future.done():
            logging.error("Consumer thread has died; exiting for restart.")
            device_manager.stop()
            return 1
        if liveness.any_expected():
            stale = liveness.stale(stale_timeout)
            if len(stale) == len(liveness._last):  # every expected device is stale
                logging.error("No data from any device in %ss (%s); exiting for restart.",
                              stale_timeout, ", ".join(sorted(stale)))
                device_manager.stop()
                return 1
    return 0
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_main_supervision.py -v`
Expected: PASS

- [ ] **Step 5: Commit the supervise function**

```bash
git add supervisor.py tests/test_main_supervision.py
git commit -m "feat: supervisor.supervise watchdog returning an exit code (#44)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6: Rewire solar-monitor.py — imports and the logger thread**

In `solar-monitor.py`, add to the imports (after line 15):

```python
import signal
from supervisor import run_logger, LivenessTracker, supervise
```

Add a module-level stop event and liveness tracker after the queue is created (after line 63):

```python
stop_event = threading.Event()
liveness = LivenessTracker()
```

Delete the inline `threaded_logger` function (lines 74-91) and replace the submit (line 95). The new submit passes the stop event and records liveness:

```python
logger_future = executor.submit(
    run_logger, pipeline, datalogger, stop_event, liveness.record
)
```

- [ ] **Step 7: Register expected devices and fail on zero matches**

Replace the device-submission loop (lines 143-151) so it counts matches, registers each expected device with the liveness tracker, and `break`s after a match:

```python
matched = 0
for dev in device_manager.devices():
    logging.debug("Processing device {} {}".format(dev.mac_address, dev.alias()))
    for section in config.sections():
        if config.get(section, "mac", fallback=None) and config.get(section, "type", fallback=None):
            mac = config.get(section, "mac").lower()
            if dev.mac_address.lower() == mac:
                executor.submit(threaded_poller, dev, device_manager, section, config, datalogger, pipeline)
                liveness.expect(section)
                matched += 1
                logging.info("Waiting for device to connect")
                time.sleep(1)
                break

if matched == 0:
    logging.error("No configured devices were discovered; exiting for restart.")
    stop_event.set()
    sys.exit(1)
```

- [ ] **Step 8: Replace the run/shutdown tail with signals + supervised main loop**

Replace lines 153-165 (the `time.sleep(10)` … `device_manager.run()` … disconnect loop) with:

```python
def _handle_signal(signum, _frame):
    logging.info("Received signal %s; shutting down.", signum)
    stop_event.set()
    device_manager.stop()


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)

logging.debug("Waiting for devices to connect...")
time.sleep(10)

# Run the gatt main loop on a background thread so the main thread can supervise.
loop_thread = threading.Thread(target=device_manager.run, name="gatt-mainloop", daemon=True)
loop_thread.start()

logging.info("Supervising; terminate with Ctrl+C or SIGTERM")
exit_code = supervise(device_manager, logger_future, liveness, stop_event,
                      check_interval=30.0, stale_timeout=600.0)

stop_event.set()
device_manager.stop()
for dev in device_manager.devices():
    try:
        dev.disconnect()
    except Exception as e:
        logging.warning("Error disconnecting %s: %s", getattr(dev, "mac_address", "?"), e)

sys.exit(exit_code)
```

- [ ] **Step 9: Manual smoke check (no hardware) — syntax + import wiring**

Run a byte-compile and a stubbed import of the supervisor wiring:

Run: `python -m py_compile solar-monitor.py supervisor.py solardevice.py datalogger.py`
Expected: no output (all compile).

Run the full suite: `python -m pytest -v`
Expected: all green.

- [ ] **Step 10: Commit**

```bash
git add solar-monitor.py
git commit -m "feat: supervised main loop, signals, zero-device exit (#44)

Replaces the inline threaded_logger with supervisor.run_logger, runs the gatt
main loop on a thread, and supervises liveness + the consumer future — exiting
non-zero (so systemd restarts) on consumer death, total staleness, or zero
matched devices. Adds SIGTERM/SIGINT handling for clean shutdown.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: systemd unit — ordering, watchdog wiring, and readiness

**Files:**
- Modify: `solar-monitor.service`

**Interfaces:**
- Consumes: the exit-non-zero behavior from Task 10.
- Produces: a unit that starts after Bluetooth and restarts on the non-zero exits Phase 1 now produces.

> NOTE: full `Type=notify` + `sd_notify` watchdog pinging is deferred to Phase 4
> (it needs `python-systemd` and touches packaging). This task does the safe,
> dependency-free subset: correct ordering and restart-on-failure, which is what
> makes the new non-zero exits actually recover.

- [ ] **Step 1: Read the current unit**

Read `solar-monitor.service`. It currently has `After=network.target`, `Type=simple`, `Restart=always`.

- [ ] **Step 2: Add Bluetooth ordering and keep restart-on-failure**

Edit `solar-monitor.service`:

- Change `After=network.target` to:

```ini
After=network.target bluetooth.service
Wants=bluetooth.service
```

- Keep `Restart=always` and `RestartSec=13` (they now catch the Phase 1 non-zero exits). Confirm `Type=simple` remains.

- [ ] **Step 3: Verify the unit parses**

Run: `systemd-analyze verify ./solar-monitor.service 2>&1 || true`
Expected: no errors reported about `[Unit]`/`[Service]` keys. (If `systemd-analyze` is unavailable in this environment, visually confirm the `[Unit]`/`[Service]`/`[Install]` structure is intact.)

- [ ] **Step 4: Commit**

```bash
git add solar-monitor.service
git commit -m "fix: order service after bluetooth.service (#44)

The daemon runs discovery once at startup; starting before bluetoothd found
zero devices and idled forever. Order after bluetooth.service so discovery has
an adapter, and rely on Restart to catch the new non-zero exits.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] **Run the whole suite:** `. .venv/bin/activate && python -m pytest -v` — expect all green.
- [ ] **Byte-compile everything:** `python -m py_compile *.py` — no output.
- [ ] **Grep for regressions:**
  - `grep -n "self.queue.put(" solardevice.py` → no matches.
  - `grep -n "time.sleep" solardevice.py` → only in `device_poller`/`mqtt_poller` bodies (worker threads), NOT in `connect`, `connect_failed`, `disconnect_succeeded`.
  - `grep -n "sys.exit(299)" solar-monitor.py` → no matches.
- [ ] **Open the Phase 1 PR** for `feat/supervision-liveness` referencing #44, listing which findings from the design doc are addressed and which are deferred to later phases.

## Coverage against issue #44

| #44 checklist item | Task |
|---|---|
| threaded_logger catches per-item, no sys.exit(299) | 6, 10 |
| queue.put → put_nowait drop-and-count | 4, 5 |
| GLib-scheduled iterative reconnect | 9 |
| supervisory watchdog exits non-zero | 7, 10 |
| SIGTERM/SIGINT clean shutdown | 10 |
| requests.post timeout + RequestException | 8 |
| zero devices → non-zero exit | 10 |
| service ordered after bluetooth.service | 11 |

Deferred (documented, not in this plan): `Type=notify`+`sd_notify` watchdog ping (Phase 4); per-device reconnect config lookup and the thread-revival/lock fixes (Phase 3, issue #46); full `main()` extraction (Phase 2, issue #45).
