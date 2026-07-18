# Phase 2 — Testability Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` checkboxes.

**Goal:** Make solar-monitor importable and testable (issue #45): extract the config/discovery/orchestration out of `solar-monitor.py` module scope into an importable `monitor_app.py`, fix the two defects that rotted there unseen (dead config `try/except`, discovery off-by-one), and stand up the repo's first CI.

**Architecture:** `solar-monitor.py` (hyphenated → not importable) becomes a 3-line shim that calls `monitor_app.main()`. All logic moves to `monitor_app.py`, which has **no import-time side effects** (no argparse, no discovery, no logging setup at module scope). The pure, testable pieces — `load_config` and `discovery_complete` — get unit tests. `main()` stays integration glue, verified by `py_compile` and by being import-safe.

**Tech stack:** Python 3.11, pytest (venv), GitHub Actions.

## Global Constraints
- Dev deps via venv, never `pip install --user`. The test venv needs `pip install pytest requests` (requests is a real runtime dep imported by datalogger; gatt/dbus/paho/gi are stubbed in `tests/conftest.py`).
- `monitor_app.py` must be importable with NO side effects (conftest stubs gatt/dbus/paho/gi already make the BLE imports work).
- The systemd/Docker/README entrypoint is `solar-monitor.py` — it MUST keep working unchanged as an invocation (`python solar-monitor.py …`). Keep the filename, shebang, and CLI behavior identical.
- Keep the existing 26 tests green throughout.
- Commits use explicit file lists (no `git add -A`). Commit trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

## File Structure
- **Create `monitor_app.py`** — importable app core: `parse_args`, `ConfigError`, `load_config`, `discovery_complete`, `run_discovery`, `threaded_poller`, `main`.
- **Rewrite `solar-monitor.py`** — thin shim: `from monitor_app import main; sys.exit(main())`.
- **Create `tests/test_config.py`, `tests/test_discovery.py`** — unit tests for the extracted pure functions.
- **Create `.github/workflows/ci.yml`** — pytest + py_compile on 3.11.
- **Create `tests/test_hacien_golden.py` + `tests/fixtures/hacien_frames.json`** (Task 5, best-effort) — characterization of the Hacien decoder against real captured frames.

---

## Task 1: Extract config loading into monitor_app.py (with the validation fix)

**Files:** Create `monitor_app.py`; Create `tests/test_config.py`.

**Interfaces produced:**
- `class ConfigError(Exception)`
- `load_config(ini_file, adapter=None, debug=False) -> configparser.ConfigParser` — raises `ConfigError` if the file is missing/empty/unreadable or lacks `[monitor]`; applies adapter/debug overrides.
- `parse_args(argv=None) -> argparse.Namespace`

- [ ] **Step 1: Write failing tests** — Create `tests/test_config.py`:

```python
import textwrap
import pytest
import monitor_app  # conftest stubs gatt/dbus/paho/gi so this imports


def _write(tmp_path, body):
    p = tmp_path / "sm.ini"
    p.write_text(textwrap.dedent(body))
    return str(p)


def test_load_config_missing_file_raises_configerror(tmp_path):
    missing = str(tmp_path / "nope.ini")
    with pytest.raises(monitor_app.ConfigError):
        monitor_app.load_config(missing)


def test_load_config_without_monitor_section_raises(tmp_path):
    ini = _write(tmp_path, """
        [mqtt]
        broker = localhost
    """)
    with pytest.raises(monitor_app.ConfigError):
        monitor_app.load_config(ini)


def test_load_config_valid_returns_config(tmp_path):
    ini = _write(tmp_path, """
        [monitor]
        adapter = hci0
    """)
    cfg = monitor_app.load_config(ini)
    assert cfg.get("monitor", "adapter") == "hci0"


def test_load_config_applies_overrides(tmp_path):
    ini = _write(tmp_path, """
        [monitor]
        adapter = hci0
        debug = False
    """)
    cfg = monitor_app.load_config(ini, adapter="hci1", debug=True)
    assert cfg.get("monitor", "adapter") == "hci1"
    assert cfg.getboolean("monitor", "debug") is True
```

- [ ] **Step 2: Run, verify fail** — `. .venv/bin/activate && python -m pytest tests/test_config.py -v` → `ModuleNotFoundError: No module named 'monitor_app'`.

- [ ] **Step 3: Create monitor_app.py** with the header, imports, and these functions (only these for this task — later tasks add more):

```python
#!/usr/bin/env python3
"""Importable application core for solar-monitor.

Split out of the solar-monitor.py entrypoint so config and discovery logic are
testable without a Bluetooth adapter. solar-monitor.py is a thin shim that calls
main(). This module MUST have no import-time side effects.
"""
from argparse import ArgumentParser
import configparser
import concurrent.futures
import logging
import queue
import signal
import sys
import threading
import time

from solardevice import SolarDeviceManager, SolarDevice
from datalogger import DataLogger
import duallog
from supervisor import run_logger, LivenessTracker, supervise

DISCOVERY_WINDOW = 5     # stop discovery after this many seconds with no new devices
DISCOVERY_MAX_WAIT = 15  # hard cap on discovery duration (seconds)


class ConfigError(Exception):
    """The ini file is missing/unreadable or lacks the [monitor] section."""


def parse_args(argv=None):
    p = ArgumentParser(description="Solar Monitor")
    p.add_argument('--adapter', help="Name of Bluetooth adapter. Overrides what is set in .ini")
    p.add_argument('-d', '--debug', action='store_true', help="Enable debug")
    p.add_argument('--ini', help="Path to .ini-file. Defaults to 'solar-monitor.ini'")
    return p.parse_args(argv)


def load_config(ini_file, adapter=None, debug=False):
    """Read and validate the ini file.

    configparser.read() silently returns [] for a missing file, so the old
    try/except around it was dead code — a missing ini surfaced much later as a
    misleading error. Validate explicitly here instead.
    """
    config = configparser.ConfigParser()
    try:
        read_ok = config.read(ini_file)
    except configparser.Error as e:
        raise ConfigError("Unable to parse ini-file {}: {}".format(ini_file, e))
    if not read_ok:
        raise ConfigError("Unable to read ini-file {} (missing or empty)".format(ini_file))
    if not config.has_section('monitor'):
        raise ConfigError("ini-file {} has no [monitor] section".format(ini_file))
    if adapter:
        config.set('monitor', 'adapter', adapter)
    if debug:
        config.set('monitor', 'debug', '1')
    return config
```

- [ ] **Step 4: Run, verify pass** — `python -m pytest tests/test_config.py -v` → 4 passed. Then full suite `python -m pytest -q` → 30 passed.

- [ ] **Step 5: Commit** — `git add monitor_app.py tests/test_config.py` then commit `feat: extract load_config with validation into monitor_app (#45)`.

---

## Task 2: Discovery termination helper (off-by-one fix)

**Files:** Modify `monitor_app.py`; Create `tests/test_discovery.py`.

**Interface produced:** `discovery_complete(found, window=DISCOVERY_WINDOW) -> bool` — `found` is the list of cumulative device counts sampled once per second; returns True when the count `window` seconds ago equals the current count (no new devices in the last `window` seconds).

Background: the old inline check was `if len(found) > 5: if found[len(found)-5] == f`, i.e. it compared `found[-5]` to `found[-1]` — indices 4 apart = a **4-second** window, not 5. The fix compares `found[-1]` to `found[-1-window]`.

- [ ] **Step 1: Write failing tests** — Create `tests/test_discovery.py`:

```python
import monitor_app


def test_not_complete_before_window_filled():
    # Fewer than window+1 samples: cannot yet conclude "no new devices".
    assert monitor_app.discovery_complete([1, 1, 1, 1, 1], window=5) is False


def test_not_complete_when_count_changed_within_window():
    # A device appeared 5s ago -> count differs from window ago -> keep scanning.
    assert monitor_app.discovery_complete([1, 2, 3, 4, 5, 6], window=5) is False


def test_complete_when_stable_across_full_window():
    # 6 samples, count unchanged across the last 5 seconds -> done.
    assert monitor_app.discovery_complete([3, 3, 3, 3, 3, 3], window=5) is True


def test_window_is_five_seconds_not_four():
    # This list is stable over the last 4 samples but changed 5s ago;
    # a 4-second window would wrongly stop, a correct 5-second one keeps going.
    assert monitor_app.discovery_complete([1, 2, 2, 2, 2, 2], window=5) is False
```

- [ ] **Step 2: Run, verify fail** — `python -m pytest tests/test_discovery.py -v` → AttributeError: no `discovery_complete`.

- [ ] **Step 3: Add to monitor_app.py** (after `load_config`):

```python
def discovery_complete(found, window=DISCOVERY_WINDOW):
    """True when the device count `window` seconds ago equals the current count,
    i.e. no new devices appeared in the last `window` one-second samples."""
    if len(found) <= window:
        return False
    return found[-1] == found[-1 - window]
```

- [ ] **Step 4: Run, verify pass** — `python -m pytest tests/test_discovery.py -v` → 4 passed. Full suite → 34 passed.

- [ ] **Step 5: Commit** — `git add monitor_app.py tests/test_discovery.py` then `fix: correct discovery 5-second window off-by-one (#45)`.

---

## Task 3: Move orchestration into main(); make solar-monitor.py a shim

**Files:** Modify `monitor_app.py` (add `run_discovery`, `threaded_poller`, `main`); Rewrite `solar-monitor.py`.

**Interfaces produced:**
- `run_discovery(device_manager, max_wait=DISCOVERY_MAX_WAIT, window=DISCOVERY_WINDOW, sleep=time.sleep)` — runs the discovery loop using `discovery_complete`.
- `threaded_poller(dev, device_manager, logger_name, config, datalogger, queue)` — unchanged behavior, moved from the script.
- `main(argv=None) -> int` — full orchestration; returns an exit code (0 clean, 1 unrecoverable). No `sys.exit` inside; the shim calls `sys.exit(main())`.

- [ ] **Step 1: Add `run_discovery`, `threaded_poller`, `main` to monitor_app.py.** Append:

```python
def run_discovery(device_manager, max_wait=DISCOVERY_MAX_WAIT, window=DISCOVERY_WINDOW, sleep=time.sleep):
    device_manager.update_devices()
    logging.info("Starting discovery...")
    device_manager.start_discovery()
    found = []
    waited = 0
    while True:
        sleep(1)
        waited += 1
        f = len(device_manager.devices())
        logging.debug("Found {} BLE-devices so far".format(f))
        found.append(f)
        if discovery_complete(found, window) or waited >= max_wait:
            break
    device_manager.stop_discovery()
    logging.info("Found {} BLE-devices".format(len(device_manager.devices())))


def threaded_poller(dev, device_manager, logger_name, config, datalogger, queue):
    logging.info("Trying to connect to {}...".format(dev.mac_address))
    try:
        device = SolarDevice(mac_address=dev.mac_address, manager=device_manager,
                             logger_name=logger_name, config=config,
                             datalogger=datalogger, queue=queue)
    except Exception as e:
        logging.error(e)
        return
    device.connect()


def main(argv=None):
    args = parse_args(argv)
    ini_file = args.ini or "solar-monitor.ini"
    try:
        config = load_config(ini_file, adapter=args.adapter, debug=args.debug)
    except ConfigError as e:
        print(str(e))
        return 1

    debug = config.getboolean('monitor', 'debug', fallback=False)
    if debug:
        print("Debug enabled")
    level = logging.DEBUG if debug else logging.INFO
    duallog.setup('solar-monitor', minLevel=level, fileLevel=level, rotation='daily', keep=30)

    pipeline = queue.Queue(maxsize=10000)
    stop_event = threading.Event()
    liveness = LivenessTracker()

    try:
        datalogger = DataLogger(config)
    except Exception as e:
        logging.error("Unable to set up datalogger")
        logging.error(e)
        return 1

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=100)
    logger_future = executor.submit(run_logger, pipeline, datalogger, stop_event, liveness.record)

    device_manager = SolarDeviceManager(adapter_name=config['monitor']['adapter'])
    logging.info("Adapter status - Powered: {}".format(device_manager.is_adapter_powered))
    if not device_manager.is_adapter_powered:
        logging.info("Powering on the adapter ...")
        device_manager.is_adapter_powered = True
        logging.info("Powered on")

    run_discovery(device_manager)

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
        return 1

    def _handle_signal(signum, _frame):
        logging.info("Received signal %s; shutting down.", signum)
        stop_event.set()
        device_manager.stop()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logging.debug("Waiting for devices to connect...")
    time.sleep(10)

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

    return exit_code
```

- [ ] **Step 2: Rewrite `solar-monitor.py`** to the shim (keep shebang so the systemd/Docker entrypoint is unchanged):

```python
#!/usr/bin/env python3
"""Entry point shim. Real logic lives in the importable monitor_app module."""
import sys

from monitor_app import main

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Add an import-safety test** — Create `tests/test_import_safe.py`:

```python
def test_importing_monitor_app_has_no_side_effects():
    # Must import with no adapter, no argparse, no discovery — proves the
    # module-scope side effects are gone (the whole point of the extraction).
    import monitor_app
    assert callable(monitor_app.main)
    assert callable(monitor_app.load_config)
```

- [ ] **Step 4: Verify** — `python -m py_compile solar-monitor.py monitor_app.py` (no output). `python -m pytest -q` → 35 passed. Sanity-check the shim: `python solar-monitor.py --help` prints the argparse help and exits 0 (proves the entrypoint still works end-to-end without hardware).

- [ ] **Step 5: Commit** — `git add monitor_app.py solar-monitor.py tests/test_import_safe.py` then `refactor: move orchestration into monitor_app.main(), shim the entrypoint (#45)`.

---

## Task 4: GitHub Actions CI

**Files:** Create `.github/workflows/ci.yml`.

Rationale: first CI the repo has ever had. Runs the suite on the same Python the Dockerfile targets (3.11). No strict linter (the legacy code would light up hundreds of warnings and make CI permanently red); `py_compile` is the "does it parse" gate. `requests` is installed because datalogger imports it and one test drives it; the BLE/system libs stay stubbed.

- [ ] **Step 1: Create `.github/workflows/ci.yml`:**

```yaml
name: CI

on:
  push:
    branches: [master]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install test dependencies
        # gatt/dbus/paho/gi are stubbed in tests/conftest.py; requests is a real
        # runtime dep imported by datalogger and exercised by a test.
        run: pip install pytest requests
      - name: Byte-compile (syntax gate)
        run: python -m py_compile monitor_app.py solar-monitor.py supervisor.py solardevice.py datalogger.py duallog.py
      - name: Run tests
        run: python -m pytest -q
```

- [ ] **Step 2: Validate YAML locally** — `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('yaml ok')"` (if PyYAML unavailable, visually confirm structure).

- [ ] **Step 3: Commit** — `git add .github/workflows/ci.yml` then `ci: add GitHub Actions running pytest + byte-compile (#45)`. (CI runs on the PR once pushed — watch it go green.)

---

## Task 5: Golden-frame characterization tests for the Hacien decoder (BEST-EFFORT)

**Files:** Create `tests/fixtures/hacien_frames.json`; Create `tests/test_hacien_golden.py`.

This is characterization, not correctness: pin what the CURRENT Hacien decoder does with REAL captured frames, so Phase 3 (#46) can refactor the decoder and diff behavior. The Hacien plugin has confirmed bugs (IndexError on short frames, a De Morgan cell-skip). Where a real frame triggers a known bug, mark the test `xfail`/`skip` with a `# Phase 3 #46` reference rather than asserting broken output as "correct".

**BEST-EFFORT:** if extracting/wiring the frames proves too fiddly to do cleanly without hardware, commit whatever solid subset works and note the rest as a Phase 3 follow-up in the report. Do NOT block the PR on richer assertions.

- [ ] **Step 1: Extract a small frame fixture** from `plugins/Hacien/dev/bms-raw-2024-03-20.json` (Wireshark export; RX frames live in `_source.layers.btatt["btgatt.nordic.uart_rx_raw"]`). Write a one-off extraction (in scratchpad, not committed) that reassembles CRC-valid frames (Modbus CRC, see `plugins/Hacien/dev/parse.py`) and saves ~5–10 representative frames (function 0x4C cell-voltage and 0x32 status) as hex strings to `tests/fixtures/hacien_frames.json`, e.g. `[{"desc": "0x4C cell voltages", "hex": "014c..."}, ...]`.

- [ ] **Step 2: Study the Hacien plugin's decode entry point** (`plugins/Hacien/__init__.py` — `Util.notificationUpdate` / `handleMessage` / `validate`) to learn exactly how a frame is fed in and where decoded values land (which `PowerDevice` entities). Then write `tests/test_hacien_golden.py` that constructs the plugin `Util` against a fake device, feeds each fixture frame, and asserts the resulting entity values equal the pinned expected values you observed. For any frame that raises due to a known bug, wrap with `pytest.mark.xfail(reason="Hacien short-frame IndexError — Phase 3 #46", strict=False)`.

- [ ] **Step 3: Verify** — `python -m pytest tests/test_hacien_golden.py -v` (green or xfail, no unexpected errors). Full suite green.

- [ ] **Step 4: Commit** — `git add tests/fixtures/hacien_frames.json tests/test_hacien_golden.py` then `test: characterize Hacien decoder against captured frames (#45)`.

---

## Final verification & PR
- [ ] `python -m pytest -q` all green; `python -m py_compile` all modules clean.
- [ ] `python solar-monitor.py --help` works (entrypoint intact).
- [ ] Push `feat/testability-foundation`, open PR closing #45, watch CI to green.

## Coverage vs issue #45
| #45 item | Task |
|---|---|
| Extract main() behind an importable boundary | 1, 3 |
| Config validation (dead try/except, [monitor]) | 1 |
| Discovery off-by-one | 2 |
| Golden-frame decoder tests from Hacien/dev captures | 5 |
| GitHub Actions CI | 4 |
Deferred/noted: the deeper discovery redesign (terminate on "all configured MACs found" rather than a count plateau) is a larger behavioral change — noted as a follow-up, not in this phase.
