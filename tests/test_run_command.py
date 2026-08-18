"""`run_command` against plugins that do and don't implement cmdRequest.

Four of the six plugins (Hacien, Meritsun, RenogyBatt, Topband) are read-only
and define no `cmdRequest`. An MQTT `set` addressed to one of those used to
raise AttributeError out of `run_command`.
"""

import pytest

from solardevice import SolarDevice


class _Util:
    """A plugin that implements commands."""

    def __init__(self):
        self.calls = []

    def cmdRequest(self, command, value):
        self.calls.append((command, value))
        return [b"\x01\x02", b"\x03"]


class _ReadOnlyUtil:
    """A plugin that does not -- four of the six shipped ones."""


@pytest.fixture
def device():
    dev = SolarDevice.__new__(SolarDevice)      # bypass BLE setup
    dev.logger_name = "test-device"
    dev.type = "Meritsun"
    dev.device_write_characteristic_commands = "char-uuid"
    dev.writes = []
    dev.characteristic_write_value = lambda data, char: dev.writes.append((data, char))
    return dev


def test_command_reaches_the_device(device):
    device.util = _Util()
    device.run_command("power_switch", "on")
    assert device.util.calls == [("power_switch", "on")]
    assert device.writes == [(b"\x01\x02", "char-uuid"), (b"\x03", "char-uuid")]


def test_read_only_plugin_does_not_raise(device):
    device.util = _ReadOnlyUtil()
    device.run_command("power_switch", "on")     # must not raise
    assert device.writes == []


def test_read_only_plugin_is_logged(device, caplog):
    device.util = _ReadOnlyUtil()
    with caplog.at_level("WARNING"):
        device.run_command("power_switch", "on")
    assert "accepts no commands" in caplog.text
    assert "test-device" in caplog.text
