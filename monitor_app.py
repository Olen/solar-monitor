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
