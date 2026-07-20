import threading
import connection

NO_JITTER = lambda a, b: 0.0   # deterministic rand for exact-value assertions


def test_backoff_grows_then_caps():
    b = lambda n: connection.backoff_seconds(n, base=5, maximum=300, rand=NO_JITTER)
    assert b(1) == 5
    assert b(2) == 10
    assert b(3) == 20
    assert b(4) == 40
    assert b(100) == 300   # capped


def test_backoff_clamped_not_a_bigint():
    assert connection.backoff_seconds(10_000, base=5, maximum=300, rand=NO_JITTER) == 300


def test_backoff_attempt_floor():
    assert connection.backoff_seconds(0, base=5, maximum=300, rand=NO_JITTER) == 5


def test_backoff_applies_jitter_to_spread_retries():
    # With jitter, the delay is offset by rand(-jitter, jitter). A rand that
    # returns its upper bound gives delay + jitter; never negative.
    hi = connection.backoff_seconds(1, base=10, jitter=5, rand=lambda a, b: b)
    lo = connection.backoff_seconds(1, base=10, jitter=5, rand=lambda a, b: a)
    assert hi == 15 and lo == 5                         # first retry spread over 5..15
    # jitter never drives the delay below zero
    assert connection.backoff_seconds(1, base=1, jitter=100, rand=lambda a, b: a) == 0.0


def test_maintain_backs_off_on_repeated_failure():
    delays = []
    stop = threading.Event()

    def connect_fn():
        return False

    def fake_sleep(d):
        delays.append(d)
        if len(delays) >= 4:
            stop.set()

    connection.maintain_device("reg", connect_fn, stop, base_backoff=5,
                               max_backoff=300, rand=NO_JITTER, sleep=fake_sleep)
    assert delays == [5, 10, 20, 40]


def test_maintain_resets_backoff_after_a_good_connection():
    outcomes = iter([False, False, True, False])
    delays = []
    stop = threading.Event()

    def connect_fn():
        try:
            return next(outcomes)
        except StopIteration:
            stop.set()
            return False

    connection.maintain_device("reg", connect_fn, stop, base_backoff=5,
                               max_backoff=300, rand=NO_JITTER, sleep=delays.append)
    assert delays == [5, 10, 5]     # good connection resets the backoff


def test_maintain_stops_on_event_without_calling_connect():
    stop = threading.Event()
    stop.set()
    calls = {"n": 0}

    def connect_fn():
        calls["n"] += 1
        return False

    connection.maintain_device("reg", connect_fn, stop, sleep=lambda d: None)
    assert calls["n"] == 0


def test_maintain_treats_connect_exception_as_failure():
    delays = []
    stop = threading.Event()

    def connect_fn():
        raise RuntimeError("boom")

    def fake_sleep(d):
        delays.append(d)
        stop.set()

    connection.maintain_device("reg", connect_fn, stop, base_backoff=5,
                               rand=NO_JITTER, sleep=fake_sleep)
    assert delays == [5]            # exception -> backoff, no crash


# --- rotate_devices: the "rotating slot" of the hybrid poller ----------------

def test_rotate_visits_devices_round_robin():
    visited = []
    stop = threading.Event()

    def names_fn():
        return ["a", "b", "c"]

    def connect_fn_for(name):
        def go():
            visited.append(name)
            if len(visited) >= 7:
                stop.set()
            return True
        return go

    connection.rotate_devices(names_fn, connect_fn_for, stop, gap=0,
                              rand=NO_JITTER, sleep=lambda d: None)
    assert visited == ["a", "b", "c", "a", "b", "c", "a"]


def test_rotate_sleeps_gap_between_devices():
    slept = []
    stop = threading.Event()

    def fake_sleep(d):
        slept.append(d)
        if len(slept) >= 3:
            stop.set()

    connection.rotate_devices(lambda: ["a", "b"], lambda n: (lambda: True),
                              stop, gap=5, rand=NO_JITTER, sleep=fake_sleep)
    assert slept == [5, 5, 5]       # a gap after each visited device


def test_rotate_waits_when_no_devices_yet():
    calls = {"n": 0}
    slept = []
    stop = threading.Event()

    def connect_fn_for(name):
        calls["n"] += 1
        return lambda: True

    def fake_sleep(d):
        slept.append(d)
        if len(slept) >= 3:
            stop.set()

    connection.rotate_devices(lambda: [], connect_fn_for, stop, gap=7,
                              rand=NO_JITTER, sleep=fake_sleep)
    assert calls["n"] == 0          # nothing to connect
    assert slept == [7, 7, 7]       # just idles on the gap


def test_rotate_continues_after_connect_exception():
    visited = []
    stop = threading.Event()

    def connect_fn_for(name):
        def go():
            visited.append(name)
            if name == "a" and visited.count("a") == 1:
                raise RuntimeError("boom")     # first visit to a blows up
            if len(visited) >= 4:
                stop.set()
            return True
        return go

    connection.rotate_devices(lambda: ["a", "b"], connect_fn_for, stop, gap=0,
                              rand=NO_JITTER, sleep=lambda d: None)
    assert visited == ["a", "b", "a", "b"]     # exception didn't stop rotation


def test_rotate_stops_on_event_without_connecting():
    stop = threading.Event()
    stop.set()

    def connect_fn_for(name):
        raise AssertionError("connect_fn_for must not be called after stop")

    connection.rotate_devices(lambda: ["a"], connect_fn_for, stop,
                              sleep=lambda d: None)
