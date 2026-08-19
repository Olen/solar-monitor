"""Retained discovery configs are republished occasionally, not constantly.

`log()` passes `refresh=True` on its timed resend, and `publish()` treated that
as "rewrite this entity's discovery config" — so every entity's config went to
the broker every few minutes. The surviving intent of the `NewBattery` branch
(2024-03-25); its other half, a longer resend interval, became #67.
"""

import configparser
from datetime import datetime, timedelta

import pytest

import datalogger
from datalogger import DataLogger


def make_logger(refresh_minutes=10):
    config = configparser.ConfigParser()
    config["mqtt"] = {"broker": "mqtt.example.net", "hostname": "test-host"}
    config["datalogger"] = {"refresh": str(refresh_minutes)}
    return DataLogger(config)


def config_publishes(logger, var="voltage"):
    return [topic for topic, *_ in logger.mqtt.client.published
            if topic.startswith("homeassistant/") and topic.endswith(f"/{var}/config")]


def force_resend_due(logger, device="battery_1", var="voltage"):
    """Age the stored timestamp so log() takes its timed-resend branch."""
    logger.logdata[device][var]["ts"] = datetime.now() - timedelta(minutes=99)


def test_a_new_entity_publishes_its_config_once():
    logger = make_logger()
    logger.log("battery_1", "voltage", 13.7)
    assert len(config_publishes(logger)) == 1


def test_a_timed_resend_does_not_republish_the_config():
    logger = make_logger()
    logger.log("battery_1", "voltage", 13.7)
    for _ in range(5):
        force_resend_due(logger)
        logger.log("battery_1", "voltage", 13.7)
    assert len(config_publishes(logger)) == 1


def test_the_config_is_republished_once_the_interval_has_passed(monkeypatch):
    """A broker that lost its retained store still gets the configs back."""
    clock = [0.0]
    monkeypatch.setattr(datalogger.time, "monotonic", lambda: clock[0])

    logger = make_logger()
    logger.log("battery_1", "voltage", 13.7)          # config published at t=0

    clock[0] = datalogger.DISCOVERY_REPUBLISH_SECONDS - 1
    force_resend_due(logger)
    logger.log("battery_1", "voltage", 13.7)          # still inside the interval
    assert len(config_publishes(logger)) == 1

    clock[0] = datalogger.DISCOVERY_REPUBLISH_SECONDS + 1
    force_resend_due(logger)
    logger.log("battery_1", "voltage", 13.7)
    assert len(config_publishes(logger)) == 2


def test_the_state_is_still_sent_on_every_resend():
    """Throttling the config must not throttle the reading itself."""
    logger = make_logger()
    logger.log("battery_1", "voltage", 13.7)
    for _ in range(5):
        force_resend_due(logger)
        logger.log("battery_1", "voltage", 13.7)
    states = [t for t, *_ in logger.mqtt.client.published if t.endswith("/voltage/state")]
    assert len(states) == 6
