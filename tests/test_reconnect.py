import solardevice


def _reconnecting_device():
    dev = solardevice.SolarDevice(mac_address="aa:bb:cc:dd:ee:ff", manager=None)
    dev.auto_reconnect = True
    dev.logger_name = "reg"
    dev.poller_thread = None
    dev.command_thread = None
    return dev


def test_schedule_reconnect_uses_glib_and_does_not_recurse(fake_glib):
    dev = _reconnecting_device()
    connect_calls = {"n": 0}
    dev.connect = lambda: connect_calls.__setitem__("n", connect_calls["n"] + 1)

    dev._schedule_reconnect()

    # It scheduled a delayed retry rather than calling connect() synchronously.
    assert connect_calls["n"] == 0
    assert len(fake_glib.scheduled) == 1
    delay, cb = fake_glib.scheduled[0]
    assert delay == 10
    # The scheduled callback returns False (one-shot) and calls connect once.
    assert cb() is False
    assert connect_calls["n"] == 1


def test_schedule_reconnect_noop_when_disabled(fake_glib):
    dev = _reconnecting_device()
    dev.auto_reconnect = False
    dev._schedule_reconnect()
    assert fake_glib.scheduled == []


import inspect


def test_no_time_sleep_in_gatt_callbacks():
    src = inspect.getsource(solardevice.SolarDevice.connect_failed)
    src += inspect.getsource(solardevice.SolarDevice.disconnect_succeeded)
    assert "time.sleep" not in src, "gatt callback must not block on time.sleep"
