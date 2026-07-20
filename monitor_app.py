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
import threading
import time

from solardevice import SolarDeviceManager, SolarDevice
from datalogger import DataLogger
import duallog
from supervisor import run_logger, LivenessTracker, supervise
from connection import maintain_device, rotate_devices

DISCOVERY_WINDOW = 5     # stop discovery after this many seconds with no new devices
DISCOVERY_MAX_WAIT = 15  # hard cap on discovery duration (seconds)
CONNECT_TIMEOUT = 40.0   # per-attempt wait for a persistent device to resolve services
CONNECT_STAGGER = 1.0    # delay between starting each device's connect (like the old code)
HOLD_POLL = 5.0          # while connected, how often to check the device is still up
REDISCOVER_INTERVAL = 120.0  # how often to re-scan for configured devices that appear after startup

# Hybrid poller (fallback for constrained controllers): devices flagged
# `persistent` in the ini each keep a permanent slot (maintain_device); any
# non-persistent devices share ONE rotating slot (rotate_devices) — connect,
# hold to read, disconnect, next. A healthy adapter can hold every device
# persistently; see docs/BLUETOOTH.md (the usual cause of apparent link limits
# is 2.4 GHz WiFi/Bluetooth coexistence, not the controller).
ROTATE_DWELL = 30.0            # seconds to hold each rotating device to collect readings
ROTATE_GAP = 5.0              # settle time between rotating devices (lets teardown finish)
ROTATE_CONNECT_TIMEOUT = 25.0  # per-attempt resolve wait for a rotating device (shorter so a
                               # dead device doesn't stall the whole rotation)
DISCONNECT_TIMEOUT = 5.0       # wait for a device's teardown to finish before the next connect


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


def discovery_complete(found, window=DISCOVERY_WINDOW):
    """True when the device count `window` seconds ago equals the current count,
    i.e. no new devices appeared in the last `window` one-second samples."""
    if len(found) <= window:
        return False
    return found[-1] == found[-1 - window]


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

    # All configured devices (section -> mac), whether or not discovered yet.
    configured = {}
    for section in config.sections():
        mac = config.get(section, "mac", fallback=None)
        dtype = config.get(section, "type", fallback=None)
        if mac and dtype:
            configured[section] = mac.lower()
    devices = {}   # section -> SolarDevice, once registered

    # Hybrid poller wiring: which devices get a permanent slot vs. the shared
    # rotating one. Devices marked `persistent = True` in the ini are held open
    # continuously; the rest are cycled through a single rotating slot so we
    # never exceed the controller's ~2 concurrent-link ceiling.
    persistent = {s for s in configured if config.getboolean(s, 'persistent', fallback=False)}
    rotate_dwell = config.getfloat('monitor', 'rotate_dwell', fallback=ROTATE_DWELL)
    rotate_gap = config.getfloat('monitor', 'rotate_gap', fallback=ROTATE_GAP)
    logging.info("Persistent devices: %s; rotating: %s",
                 ", ".join(sorted(persistent)) or "(none)",
                 ", ".join(sorted(s for s in configured if s not in persistent)) or "(none)")

    # Mark every configured device offline until it actually connects, so HA
    # shows its entities as Unavailable (not a stale last value) for anything
    # that never resolves — e.g. a dead battery. services_resolved flips a
    # device to online once it is up.
    for section in configured:
        datalogger.set_available(section, False)

    def _handle_signal(signum, _frame):
        logging.info("Received signal %s; shutting down.", signum)
        stop_event.set()
        device_manager.stop()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # The gatt main loop must run so connection callbacks (services_resolved,
    # connect_failed, disconnect_succeeded) fire while we connect.
    loop_thread = threading.Thread(target=device_manager.run, name="gatt-mainloop", daemon=True)
    loop_thread.start()

    # Serialize the *establishment* of connections. The controller allows only
    # one LE "Create Connection" in flight at a time: if two threads call
    # connect() at once (e.g. the persistent regulator and the rotating slot),
    # BlueZ cancels one and both fail with le-connection-abort-by-local. So only
    # one device may be in the connect->resolve window at a time. The lock is
    # held only during establishment, then released — several *resolved* links
    # can still be held concurrently (up to the controller's ~2-link ceiling).
    connect_lock = threading.Lock()

    def _make_connect_fn(device):
        """One connect attempt for maintain_device: connect, and if it resolves,
        hold until it drops. Returns True if it had connected (and has now
        dropped), False if it never connected."""
        def connect_once():
            device._connect_ok = False
            device._connect_event.clear()
            established = False
            with connect_lock:                  # serialize establishment
                logging.info("[%s] Connecting to %s", device.logger_name, device.mac_address)
                try:
                    device.connect()
                    established = (device._connect_event.wait(CONNECT_TIMEOUT)
                                  and device._connect_ok)
                except Exception as e:
                    logging.error("[%s] connect() raised: %s", device.logger_name, e)
            if not established:
                return False
            # Connected and resolved — hold the connection until it drops.
            device._disconnect_event.clear()
            while not stop_event.is_set():
                if device._disconnect_event.wait(HOLD_POLL):
                    break
            return True
        return connect_once

    def _safe_disconnect(device):
        try:
            device.disconnect()
        except Exception as e:
            logging.debug("[%s] disconnect error: %s", device.logger_name, e)

    def _make_rotating_connect_fn(device):
        """One rotating-slot cycle: connect, hold for a dwell window so the
        poller collects readings, then disconnect and wait for teardown so the
        next device connects into a free slot. Always releases the slot."""
        def connect_once():
            device._connect_ok = False
            device._connect_event.clear()
            device._disconnect_event.clear()
            resolved = False
            with connect_lock:                  # serialize establishment
                logging.info("[%s] Connecting (rotating slot) to %s",
                             device.logger_name, device.mac_address)
                try:
                    device.connect()
                    resolved = (device._connect_event.wait(ROTATE_CONNECT_TIMEOUT)
                                and device._connect_ok)
                except Exception as e:
                    logging.error("[%s] connect() raised: %s", device.logger_name, e)
            if resolved and not stop_event.is_set():
                stop_event.wait(rotate_dwell)   # hold the slot; poller reads here
            # Free the slot for the next device, whether or not it resolved.
            _safe_disconnect(device)
            device._disconnect_event.wait(DISCONNECT_TIMEOUT)
            return resolved
        return connect_once

    def _rotating_connect_for(name):
        device = devices.get(name)
        if device is None:
            return lambda: False
        return _make_rotating_connect_fn(device)

    def _rotating_names():
        return [s for s in devices if s not in persistent]

    def _register(section):
        """Create + trust a SolarDevice for a discovered configured section.
        A persistent device gets its own maintenance thread; a rotating device
        is just added to `devices` — the single rotation thread picks it up.
        Returns True if newly registered."""
        if section in devices:
            return False
        mac = configured[section]
        disc = next((d for d in device_manager.devices() if d.mac_address.lower() == mac), None)
        if disc is None:
            return False
        try:
            device = SolarDevice(mac_address=disc.mac_address, manager=device_manager,
                                 logger_name=section, config=config,
                                 datalogger=datalogger, queue=pipeline)
        except Exception as e:
            logging.error("Could not set up device [%s]: %s", section, e)
            return False
        # Trust it so BlueZ keeps it (no ~30s temporary-device removal) and can
        # auto-reconnect it — the device is discovered here, so its object exists.
        device.set_trusted()
        devices[section] = device
        liveness.expect(section)
        if section in persistent:
            threading.Thread(target=maintain_device,
                             args=(section, _make_connect_fn(device), stop_event),
                             name="connect-%s" % section, daemon=True).start()
            logging.info("Registered persistent device [%s] %s", section, mac)
        else:
            logging.info("Registered rotating device [%s] %s", section, mac)
        return True

    # Start each discovered device's connect, staggered. Persistent devices each
    # spin up a maintenance thread here; rotating devices are handled by the
    # single rotation thread started below.
    for section in configured:
        if _register(section):
            time.sleep(CONNECT_STAGGER)

    if not devices:
        logging.error("No configured devices were discovered; exiting for restart.")
        stop_event.set()
        return 1

    # One rotation thread services every non-persistent device through a single
    # shared slot, so total concurrent links stay within the controller's limit.
    threading.Thread(target=rotate_devices,
                     args=(_rotating_names, _rotating_connect_for, stop_event),
                     kwargs={"gap": rotate_gap},
                     name="rotate", daemon=True).start()

    def _late_discovery_loop():
        """Occasionally re-scan for configured devices that started advertising
        after startup (e.g. a battery whose BMS was reset) and start maintaining
        them. Trusted devices persist, so this only runs while something is still
        missing — and it is the one place we scan while connections may be held,
        so it is infrequent."""
        while not stop_event.wait(REDISCOVER_INTERVAL):
            missing = [s for s in configured if s not in devices]
            if not missing:
                continue
            logging.info("Re-discovering for late devices: %s", ", ".join(sorted(missing)))
            # Hold connect_lock: a scan running while a connect is being
            # established collides on the radio and aborts it (abort-by-local).
            try:
                with connect_lock:
                    device_manager.start_discovery()
                    stop_event.wait(DISCOVERY_WINDOW)
                    device_manager.stop_discovery()
            except Exception as e:
                logging.debug("Late discovery scan failed: %s", e)
            for section in missing:
                _register(section)

    threading.Thread(target=_late_discovery_loop, name="late-discovery", daemon=True).start()

    logging.info("Supervising; terminate with Ctrl+C or SIGTERM")
    exit_code = supervise(device_manager, logger_future, liveness, stop_event,
                          check_interval=30.0, stale_timeout=600.0)

    stop_event.set()
    device_manager.stop()
    for device in devices.values():
        try:
            device.disconnect()
        except Exception as e:
            logging.warning("Error disconnecting %s: %s", getattr(device, "mac_address", "?"), e)

    return exit_code
