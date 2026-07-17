"""Test-only stubs so the BLE modules import without hardware.

`gatt` is a Linux/dbus/BlueZ library that cannot be imported in CI. We install
minimal fakes into sys.modules BEFORE any test imports solardevice.py.
"""
import sys
import types


def _install_dbus_stub():
    if "dbus" in sys.modules:
        return

    exceptions = types.ModuleType("dbus.exceptions")

    class DBusException(Exception):
        pass

    exceptions.DBusException = DBusException

    dbus = types.ModuleType("dbus")
    dbus.exceptions = exceptions

    sys.modules["dbus"] = dbus
    sys.modules["dbus.exceptions"] = exceptions


def _install_gatt_stub():
    if "gatt" in sys.modules:
        return

    errors = types.ModuleType("gatt.errors")

    class _GattError(Exception):
        pass

    class InProgress(_GattError):
        pass

    class Failed(_GattError):
        pass

    errors.InProgress = InProgress
    errors.Failed = Failed

    gatt = types.ModuleType("gatt")

    class DeviceManager:
        def __init__(self, *args, **kwargs):
            pass

    class Device:
        def __init__(self, *args, **kwargs):
            pass

        def connect(self):
            pass

        def connect_succeeded(self):
            pass

        def connect_failed(self, error):
            pass

        def disconnect_succeeded(self):
            pass

        def services_resolved(self):
            pass

        def characteristic_value_updated(self, characteristic, value):
            pass

    gatt.DeviceManager = DeviceManager
    gatt.Device = Device
    gatt.errors = errors

    sys.modules["gatt"] = gatt
    sys.modules["gatt.errors"] = errors


def _install_paho_stub():
    """`paho-mqtt` is not installed in the test venv. datalogger.py only needs
    `import paho.mqtt.client as paho` to succeed at module level — no test
    exercises DataLogger.__init__ (which would call paho.Client(...)), so the
    stub just needs to make that import resolve."""
    if "paho" in sys.modules:
        return

    paho = types.ModuleType("paho")
    mqtt = types.ModuleType("paho.mqtt")
    client = types.ModuleType("paho.mqtt.client")

    mqtt.client = client
    paho.mqtt = mqtt

    sys.modules["paho"] = paho
    sys.modules["paho.mqtt"] = mqtt
    sys.modules["paho.mqtt.client"] = client


def _install_gi_stub():
    """`gi` (PyGObject) is a system package, not pip-installable into a venv.
    solardevice.py only needs `from gi.repository import GLib` to succeed at
    module level — the `fake_glib` fixture below monkeypatches
    `solardevice.GLib` for the reconnect tests, so this stub just needs a
    harmless `timeout_add_seconds`."""
    if "gi" in sys.modules:
        return

    gi = types.ModuleType("gi")
    repository = types.ModuleType("gi.repository")

    class GLib:
        @staticmethod
        def timeout_add_seconds(delay, callback):
            return 1  # a fake source id

    repository.GLib = GLib
    gi.repository = repository

    sys.modules["gi"] = gi
    sys.modules["gi.repository"] = repository


_install_dbus_stub()
_install_gatt_stub()
_install_paho_stub()
_install_gi_stub()


import pytest


class _FakeGLib:
    def __init__(self):
        self.scheduled = []  # list of (delay, callback)

    def timeout_add_seconds(self, delay, callback):
        self.scheduled.append((delay, callback))
        return 1  # a fake source id


@pytest.fixture
def fake_glib(monkeypatch):
    import solardevice
    fake = _FakeGLib()
    monkeypatch.setattr(solardevice, "GLib", fake, raising=False)
    return fake
