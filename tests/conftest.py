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


_install_dbus_stub()
_install_gatt_stub()
