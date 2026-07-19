import threading
import connection


def test_backoff_grows_then_caps():
    assert connection.backoff_seconds(1, base=5, maximum=300) == 5
    assert connection.backoff_seconds(2, base=5, maximum=300) == 10
    assert connection.backoff_seconds(3, base=5, maximum=300) == 20
    assert connection.backoff_seconds(4, base=5, maximum=300) == 40
    assert connection.backoff_seconds(100, base=5, maximum=300) == 300   # capped


def test_backoff_clamped_not_a_bigint():
    # A device that free-runs forever must not compute an ever-growing 2**attempt.
    assert connection.backoff_seconds(10_000, base=5, maximum=300) == 300


def test_backoff_attempt_floor():
    assert connection.backoff_seconds(0, base=5, maximum=300) == 5   # treated as attempt 1


def test_maintain_backs_off_on_repeated_failure():
    # connect_fn always fails -> backoff delays should be 5, 10, 20, ... until stop.
    delays = []
    stop = threading.Event()

    def connect_fn():
        return False                      # never connects

    def fake_sleep(d):
        delays.append(d)
        if len(delays) >= 4:
            stop.set()                    # end the loop after 4 backoffs

    connection.maintain_device("reg", connect_fn, stop, base_backoff=5,
                               max_backoff=300, sleep=fake_sleep)
    assert delays == [5, 10, 20, 40]      # exponential


def test_maintain_resets_backoff_after_a_good_connection():
    # fail, fail, then a good connection (returns True) resets the backoff so the
    # next failure starts at base again.
    outcomes = iter([False, False, True, False])
    delays = []
    stop = threading.Event()

    def connect_fn():
        try:
            return next(outcomes)
        except StopIteration:
            stop.set()
            return False

    def fake_sleep(d):
        delays.append(d)

    connection.maintain_device("reg", connect_fn, stop, base_backoff=5,
                               max_backoff=300, sleep=fake_sleep)
    # delays: 5 (after 1st fail), 10 (after 2nd fail), [True resets], 5 (after next fail)
    assert delays == [5, 10, 5]


def test_maintain_stops_on_event_without_calling_connect():
    stop = threading.Event()
    stop.set()
    calls = {"n": 0}

    def connect_fn():
        calls["n"] += 1
        return False

    connection.maintain_device("reg", connect_fn, stop, sleep=lambda d: None)
    assert calls["n"] == 0                 # already stopped -> never attempts


def test_maintain_treats_connect_exception_as_failure():
    delays = []
    stop = threading.Event()

    def connect_fn():
        raise RuntimeError("boom")

    def fake_sleep(d):
        delays.append(d)
        stop.set()

    connection.maintain_device("reg", connect_fn, stop, base_backoff=5, sleep=fake_sleep)
    assert delays == [5]                   # exception -> backoff, no crash
