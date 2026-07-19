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
