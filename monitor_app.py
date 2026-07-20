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

from solardevice import SolarDevice
from datalogger import DataLogger
import duallog
from supervisor import run_logger, LivenessTracker, supervise
import ble

DISCOVERY_WINDOW = 5     # stop discovery after this many seconds with no new devices
DISCOVERY_MAX_WAIT = 15  # hard cap on discovery duration (seconds)
REDISCOVER_INTERVAL = 120.0  # how often to re-scan for configured devices that appear after startup


class ConfigError(Exception):
    """The ini file is missing/unreadable or lacks the [monitor] section."""


class _NullManager:
    """Satisfies supervise()'s `device_manager.stop()` call; the real shutdown
    of BleManager is done explicitly in main() after supervise() returns."""
    def stop(self):
        pass


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

    manager = ble.BleManager(adapter=config['monitor'].get('adapter') or None)
    manager.start()

    def _handle_signal(signum, _frame):
        logging.info("Received signal %s; shutting down.", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # All configured devices (section -> mac), whether or not discovered yet.
    configured = {}
    for section in config.sections():
        mac = config.get(section, "mac", fallback=None)
        dtype = config.get(section, "type", fallback=None)
        if mac and dtype:
            configured[section] = mac.lower()

    # Mark every configured device offline until it actually connects, so HA
    # shows its entities as Unavailable (not a stale last value) for anything
    # that never resolves — e.g. a dead battery.
    for section in configured:
        datalogger.set_available(section, False)

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
