import threading
import connection


def test_add_and_next_due_returns_disconnected_device():
    c = connection.ConnectionCoordinator(get_time=lambda: 100.0)
    c.add("reg")
    assert c.next_due() == "reg"


def test_next_due_none_when_all_connected():
    c = connection.ConnectionCoordinator(get_time=lambda: 100.0)
    c.add("reg")
    c.record_result("reg", True)
    assert c.next_due() is None


def test_success_marks_connected_and_resets_attempts():
    clock = {"t": 0.0}
    c = connection.ConnectionCoordinator(get_time=lambda: clock["t"])
    c.add("reg")
    c.record_result("reg", False)     # one failure -> backoff
    c.record_result("reg", True)      # then success
    assert c.connected_count() == 1
    assert c.next_due() is None


def test_backoff_grows_on_repeated_failure():
    clock = {"t": 0.0}
    c = connection.ConnectionCoordinator(base_backoff=5.0, max_backoff=300.0,
                                         get_time=lambda: clock["t"])
    c.add("reg")
    c.record_result("reg", False)     # attempt 1 -> next at t+5
    assert c.next_due() is None       # not due yet
    clock["t"] = 5.0
    assert c.next_due() == "reg"      # now due
    c.record_result("reg", False)     # attempt 2 -> next at t+10
    clock["t"] = 9.0
    assert c.next_due() is None
    clock["t"] = 15.0
    assert c.next_due() == "reg"


def test_backoff_capped_at_max():
    clock = {"t": 0.0}
    c = connection.ConnectionCoordinator(base_backoff=5.0, max_backoff=20.0,
                                         get_time=lambda: clock["t"])
    c.add("reg")
    for _ in range(10):
        c.record_result("reg", False)
    # next_attempt must never be more than max_backoff away
    clock["t"] = 20.0
    assert c.next_due() == "reg"


def test_mark_disconnected_requeues_a_connected_device():
    clock = {"t": 0.0}
    c = connection.ConnectionCoordinator(base_backoff=5.0, get_time=lambda: clock["t"])
    c.add("reg")
    c.record_result("reg", True)
    assert c.next_due() is None
    c.mark_disconnected("reg")        # dropped -> requeue with backoff
    assert c.next_due() is None       # brief backoff first
    clock["t"] = 5.0
    assert c.next_due() == "reg"


def test_run_loop_is_serial_and_applies_backoff():
    # connect_fn records call order and returns per a script; the loop must call
    # it ONE AT A TIME and stop when everything is connected.
    clock = {"t": 0.0}
    c = connection.ConnectionCoordinator(base_backoff=5.0, get_time=lambda: clock["t"])
    for k in ("reg", "batt", "inv"):
        c.add(k)

    calls = []
    inflight = {"n": 0, "max": 0}
    lock = threading.Lock()
    results = {"reg": [True], "batt": [False, True], "inv": [True]}

    def connect_fn(key):
        with lock:
            inflight["n"] += 1
            inflight["max"] = max(inflight["max"], inflight["n"])
        calls.append(key)
        clock["t"] += 5.0            # advance clock so backoff elapses between rounds
        outcome = results[key].pop(0)
        with lock:
            inflight["n"] -= 1
        return outcome

    stop = threading.Event()

    def on_idle():
        # stop once every device is connected
        if c.all_connected():
            stop.set()

    connection.run_connection_loop(
        c, connect_fn, stop, get_time=lambda: clock["t"],
        sleep=lambda s: None, on_idle=on_idle,
    )

    assert inflight["max"] == 1               # never more than one connect in flight
    assert c.all_connected()                  # every device ended connected
    assert calls.count("batt") == 2           # batt retried after its one failure


def test_run_loop_stops_on_event():
    c = connection.ConnectionCoordinator()
    stop = threading.Event()
    stop.set()
    # already stopped -> returns immediately without calling connect_fn
    connection.run_connection_loop(c, lambda k: True, stop, sleep=lambda s: None)


def test_backoff_exponent_is_clamped_not_a_bigint():
    # A device that free-runs for a very long time must not compute an ever-
    # growing 2**attempts; the exponent is clamped and the result stays <= max.
    c = connection.ConnectionCoordinator(base_backoff=5.0, max_backoff=300.0,
                                         get_time=lambda: 0.0)
    assert c._backoff(1000) == 300.0        # clamped, no MemoryError / huge int


def test_coordinator_is_thread_safe_under_concurrent_access():
    # The real system calls mark_disconnected() from the gatt callback thread
    # while next_due()/record_result() run on the connection-loop thread. With
    # the lock this must not deadlock or raise; without it, _state access races.
    import time as _time
    c = connection.ConnectionCoordinator(base_backoff=0.0)
    for k in ("a", "b", "c", "d"):
        c.add(k)
    stop = threading.Event()
    errors = []

    def loop_worker():
        try:
            while not stop.is_set():
                k = c.next_due()
                if k is not None:
                    c.record_result(k, True)
        except Exception as e:  # pragma: no cover - failure path
            errors.append(e)

    def drop_worker():
        try:
            while not stop.is_set():
                for k in ("a", "b", "c", "d"):
                    c.mark_disconnected(k)
        except Exception as e:  # pragma: no cover - failure path
            errors.append(e)

    threads = [threading.Thread(target=loop_worker) for _ in range(3)]
    threads += [threading.Thread(target=drop_worker) for _ in range(3)]
    for t in threads:
        t.start()
    _time.sleep(0.3)
    stop.set()
    for t in threads:
        t.join(timeout=2)
    assert errors == []
    assert not any(t.is_alive() for t in threads)
