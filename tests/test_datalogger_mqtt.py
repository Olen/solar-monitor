"""MQTT datalogger: the configured port, and the topic-registry growth."""

import configparser

import pytest

from datalogger import DataLogger


def make_config(**mqtt):
    config = configparser.ConfigParser()
    config["mqtt"] = {"broker": "mqtt.example.net", "hostname": "test-host", **mqtt}
    config["datalogger"] = {}
    config["battery_1"] = {"type": "Meritsun", "mac": "11:11:11:11:11:11"}
    return config


def test_default_port_is_used_when_unset():
    logger = DataLogger(make_config())
    assert logger.mqtt.client.connected_to == ("mqtt.example.net", 1883)


@pytest.mark.parametrize("configured", ["1883", "8883"])
def test_a_configured_port_reaches_paho_as_an_int(configured):
    """config.get returns a string, and paho does `if port <= 0` on it, so any
    explicitly configured port -- even the default -- used to raise TypeError."""
    logger = DataLogger(make_config(port=configured))
    assert logger.mqtt.client.connected_to == ("mqtt.example.net", int(configured))


def test_republishing_a_topic_does_not_grow_the_registry():
    """`refresh=True` re-registered an already-known topic every time."""
    logger = DataLogger(make_config())
    for _ in range(50):
        logger.mqtt.publish("battery_1", "voltage", 13.7, refresh=True)
    assert len(logger.mqtt.sensors) == 1


def test_distinct_topics_are_all_registered():
    logger = DataLogger(make_config())
    for var in ("voltage", "current", "soc"):
        logger.mqtt.publish("battery_1", var, 1)
    assert len(logger.mqtt.sensors) == 3
