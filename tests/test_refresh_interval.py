"""The resend interval for values that have not changed.

Lived on the `refresh-interval` branch, which never worked: it assigned
`refresh_inteval` and read `refresh_interval`, so the first refresh check
raised AttributeError, and `config.get` fed a string into `timedelta`.
"""

import configparser
from datetime import datetime, timedelta

import pytest

from datalogger import DataLogger


def make_config(**datalogger):
    config = configparser.ConfigParser()
    config["mqtt"] = {"broker": "mqtt.example.net", "hostname": "test-host"}
    config["datalogger"] = dict(datalogger)
    return config


def states(logger, var="voltage"):
    return [p for p in logger.mqtt.client.published if p[0].endswith(f"/{var}/state")]


def test_default_interval_is_ten_minutes():
    assert DataLogger(make_config()).refresh_interval == 10


def test_a_configured_interval_is_an_int():
    """config.get would hand timedelta a string and raise TypeError."""
    logger = DataLogger(make_config(refresh="45"))
    assert logger.refresh_interval == 45
    assert isinstance(logger.refresh_interval, int)


def test_an_unchanged_value_is_not_resent_before_the_interval():
    logger = DataLogger(make_config(refresh="30"))
    logger.log("battery_1", "voltage", 13.7)
    logger.logdata["battery_1"]["voltage"]["ts"] = datetime.now() - timedelta(minutes=20)
    logger.log("battery_1", "voltage", 13.7)
    assert len(states(logger)) == 1


def test_an_unchanged_value_is_resent_after_the_interval():
    logger = DataLogger(make_config(refresh="30"))
    logger.log("battery_1", "voltage", 13.7)
    logger.logdata["battery_1"]["voltage"]["ts"] = datetime.now() - timedelta(minutes=31)
    logger.log("battery_1", "voltage", 13.7)
    assert len(states(logger)) == 2


def test_the_refresh_path_does_not_raise():
    """The branch's typo made exactly this call raise AttributeError."""
    logger = DataLogger(make_config())
    logger.log("battery_1", "voltage", 13.7)
    logger.logdata["battery_1"]["voltage"]["ts"] = datetime.now() - timedelta(minutes=11)
    logger.log("battery_1", "voltage", 13.7)          # must not raise
    assert len(states(logger)) == 2
