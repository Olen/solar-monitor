"""A value is remembered as sent only once it has been.

Committing to `logdata` before publishing meant a failed publish left the cache
claiming delivery, so the next identical reading compared equal and was never
resent.
"""

import configparser

import pytest

from datalogger import DataLogger


def make_config():
    config = configparser.ConfigParser()
    config["mqtt"] = {"broker": "mqtt.example.net", "hostname": "test-host"}
    config["datalogger"] = {}
    return config


@pytest.fixture
def logger():
    return DataLogger(make_config())


def states(logger, var="voltage"):
    return [p for p in logger.mqtt.client.published if p[0].endswith(f"/{var}/state")]


def test_a_value_is_published_and_remembered(logger):
    logger.log("battery_1", "voltage", 13.7)
    assert len(states(logger)) == 1
    assert logger.logdata["battery_1"]["voltage"]["value"] == 13.7


def test_an_unchanged_value_is_not_republished(logger):
    logger.log("battery_1", "voltage", 13.7)
    logger.log("battery_1", "voltage", 13.7)
    assert len(states(logger)) == 1


def test_a_failed_publish_is_not_remembered(logger):
    logger.mqtt.client.offline = True
    logger.log("battery_1", "voltage", 13.7)
    assert states(logger) == []
    assert logger.logdata["battery_1"]["voltage"]["value"] is None


def test_the_value_is_resent_once_the_broker_returns(logger):
    """The bug: the same reading after an outage used to compare equal."""
    logger.mqtt.client.offline = True
    logger.log("battery_1", "voltage", 13.7)
    logger.mqtt.client.offline = False
    logger.log("battery_1", "voltage", 13.7)
    assert len(states(logger)) == 1
    assert logger.logdata["battery_1"]["voltage"]["value"] == 13.7


def test_a_switch_state_survives_an_outage(logger):
    """Worst case: a toggle during an outage is the change you least want lost."""
    logger.log("regulator", "power_switch", "ON")
    logger.mqtt.client.offline = True
    logger.log("regulator", "power_switch", "OFF")
    logger.mqtt.client.offline = False
    logger.log("regulator", "power_switch", "OFF")
    published = [p[1] for p in states(logger, "power_switch")]
    assert published == ["ON", "OFF"]
