import inspect
import solardevice


def _bare_device():
    # type=None -> __init__ returns early (no plugin/gatt setup), giving a
    # lightweight object with the connection-signalling attributes present.
    dev = solardevice.SolarDevice(mac_address="aa:bb:cc:dd:ee:ff", manager=None)
    dev.logger_name = "reg"
    dev.poller_thread = None
    dev.command_thread = None
    return dev


def test_signal_connect_result_sets_event_and_flag():
    dev = _bare_device()
    assert not dev._connect_event.is_set()
    dev._signal_connect_result(True)
    assert dev._connect_event.is_set()
    assert dev._connect_ok is True
    dev._connect_event.clear()
    dev._signal_connect_result(False)
    assert dev._connect_event.is_set()
    assert dev._connect_ok is False


def test_connect_failed_signals_failure_to_the_waiting_loop():
    dev = _bare_device()
    dev.connect_failed("le-connection-abort-by-local")
    assert dev._connect_event.is_set()
    assert dev._connect_ok is False
    assert dev._resolved is False


def test_disconnect_of_a_live_connection_requeues_via_on_disconnect():
    dev = _bare_device()
    dev._resolved = True                     # simulate a fully-connected device
    called = {"n": 0}
    dev.on_disconnect = lambda: called.__setitem__("n", called["n"] + 1)
    dev.disconnect_succeeded()
    assert called["n"] == 1                  # live drop -> re-queued
    assert dev._connect_event.is_set()       # also unblocks any waiter
    assert dev._resolved is False


def test_set_trusted_is_defensive_when_dbus_object_missing():
    # On a bare (unmanaged) device the gatt dbus properties object isn't set up;
    # set_trusted must not raise, just return False and log.
    dev = _bare_device()
    assert dev.set_trusted() is False


def test_disconnect_sets_the_drain_event():
    # A failed connect_fn drains by waiting on _disconnect_event; disconnect_
    # succeeded must set it so teardown can't bleed into the next attempt.
    dev = _bare_device()
    assert not dev._disconnect_event.is_set()
    dev.disconnect_succeeded()
    assert dev._disconnect_event.is_set()


def test_disconnect_during_a_failed_attempt_does_not_requeue():
    dev = _bare_device()
    dev._resolved = False                    # was never resolved (attempt failed)
    called = {"n": 0}
    dev.on_disconnect = lambda: called.__setitem__("n", called["n"] + 1)
    dev.disconnect_succeeded()
    assert called["n"] == 0                  # the connection loop handles this one
    assert dev._connect_event.is_set()


def test_no_time_sleep_or_glib_reconnect_in_gatt_callbacks():
    # gatt callbacks must not block, and must not schedule their own reconnect
    # (retry/backoff is the coordinator's job now).
    src = inspect.getsource(solardevice.SolarDevice.connect_failed)
    src += inspect.getsource(solardevice.SolarDevice.disconnect_succeeded)
    src += inspect.getsource(solardevice.SolarDevice.connect)
    assert "time.sleep" not in src, "gatt callback must not block on time.sleep"
    assert "GLib" not in src, "device must not schedule its own reconnect"
