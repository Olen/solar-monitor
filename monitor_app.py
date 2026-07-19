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
from connection import ConnectionCoordinator, run_connection_loop

DISCOVERY_WINDOW = 5     # stop discovery after this many seconds with no new devices
DISCOVERY_MAX_WAIT = 15  # hard cap on discovery duration (seconds)
CONNECT_TIMEOUT = 40.0   # per-attempt wait for a device to resolve services
DISCOVER_REFRESH = 3.0   # brief re-scan before a connect so BlueZ still knows the device
DRAIN_TIMEOUT = 4.0      # wait for a failed device to fully tear down before the next attempt
REDISCOVER_INTERVAL = 60.0  # how often to re-scan for configured devices that appear after startup


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

    # The connection coordinator connects devices one at a time (see
    # connection.py) instead of firing every connect concurrently — concurrent
    # attempts collide and abort BLE service resolution.
    coordinator = ConnectionCoordinator()
    # All configured devices (section -> mac), whether or not discovered yet.
    configured = {}
    for section in config.sections():
        mac = config.get(section, "mac", fallback=None)
        dtype = config.get(section, "type", fallback=None)
        if mac and dtype:
            configured[section] = mac.lower()
    devices = {}   # section -> SolarDevice, once registered

    def _refresh_discovery():
        """Briefly re-scan so BlueZ still knows the devices (it forgets ones it
        has not seen recently, causing 'Device does not exist' on connect) and so
        devices that start advertising after startup can be found. Stopped before
        any connect — scanning and connecting collide."""
        try:
            device_manager.start_discovery()
            time.sleep(DISCOVER_REFRESH)
            device_manager.stop_discovery()
            time.sleep(1)   # let discovery fully stop before we connect
        except Exception as e:
            logging.debug("Discovery refresh failed: %s", e)

    def _register(section):
        """Create and register a SolarDevice for a configured section whose MAC is
        currently discovered. Returns True if newly registered."""
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
        device.on_disconnect = (lambda key=section: coordinator.mark_disconnected(key))
        devices[section] = device
        coordinator.add(section)
        liveness.expect(section)
        logging.info("Registered device [%s] %s", section, mac)
        return True

    # Register the configured devices found during the startup scan.
    for section in configured:
        _register(section)

    if not devices:
        logging.error("No configured devices were discovered; exiting for restart.")
        stop_event.set()
        return 1

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

    def _drain(device):
        """Fully disconnect a failed device and wait for teardown, so a late
        callback from this attempt cannot bleed into the next one."""
        device._disconnect_event.clear()
        try:
            device.disconnect()
        except Exception:
            pass
        device._disconnect_event.wait(DRAIN_TIMEOUT)

    def connect_fn(key):
        """Connect one device and block until it resolves services, fails, or
        times out. Serialized by the connection loop — only one at a time.

        Deliberately does NOT scan here: scanning immediately before a connect
        collides with it and aborts service resolution (this is what the old
        concurrent code got right — it connected straight from the startup scan's
        still-fresh cache). Cache freshness is kept up by _on_idle instead."""
        device = devices[key]
        device._connect_ok = False
        device._connect_event.clear()
        logging.info("[%s] Connecting to %s", key, device.mac_address)
        try:
            device.connect()
        except Exception as e:
            logging.error("[%s] connect() raised: %s", key, e)
            _drain(device)
            return False
        ok = device._connect_event.wait(CONNECT_TIMEOUT) and device._connect_ok
        if not ok:
            if not device._connect_event.is_set():
                logging.warning("[%s] connect timed out after %ss", key, CONNECT_TIMEOUT)
            _drain(device)
        return ok

    rediscover = {"last": 0.0}

    def _on_idle():
        """Periodically re-scan while anything is not connected. This keeps
        BlueZ's device cache fresh for reconnects (it forgets devices it has not
        seen, which otherwise makes a later connect fail with 'Device does not
        exist') and registers configured devices that started advertising after
        startup (e.g. a battery whose BMS was reset). It runs here, between
        connects, NOT before each connect — scanning right before a connect
        collides with it and aborts service resolution."""
        missing = [s for s in configured if s not in devices]
        if not missing and coordinator.all_connected():
            return   # everything registered and connected — no need to scan
        now = time.time()
        if now - rediscover["last"] < REDISCOVER_INTERVAL:
            return
        rediscover["last"] = now
        if missing:
            logging.info("Re-discovering (late devices / cache refresh): %s", ", ".join(sorted(missing)))
        else:
            logging.debug("Re-discovering to refresh the cache for disconnected devices")
        _refresh_discovery()
        for section in missing:
            _register(section)

    conn_thread = threading.Thread(
        target=run_connection_loop, args=(coordinator, connect_fn, stop_event),
        kwargs={"on_idle": _on_idle},
        name="connection-loop", daemon=True)
    conn_thread.start()

    logging.info("Supervising; terminate with Ctrl+C or SIGTERM")
    exit_code = supervise(device_manager, logger_future, liveness, stop_event,
                          check_interval=30.0, stale_timeout=600.0)

    stop_event.set()
    device_manager.stop()
    conn_thread.join(timeout=2)   # let the connection loop finish its current step
    for device in devices.values():
        try:
            device.disconnect()
        except Exception as e:
            logging.warning("Error disconnecting %s: %s", getattr(device, "mac_address", "?"), e)

    return exit_code
