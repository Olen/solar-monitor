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


_install_dbus_stub()
_install_gatt_stub()
_install_paho_stub()
