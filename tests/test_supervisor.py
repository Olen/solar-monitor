import queue
import threading
import time

import supervisor


def test_try_put_returns_true_when_space():
    q = queue.Queue(maxsize=2)
    assert supervisor.try_put(q, ("a", "b", 1)) is True
    assert q.qsize() == 1


def test_try_put_returns_false_when_full_and_does_not_block():
    q = queue.Queue(maxsize=1)
    assert supervisor.try_put(q, ("a", "b", 1)) is True
    # Second put would block a blocking put() forever; try_put must return False.
    assert supervisor.try_put(q, ("c", "d", 2)) is False
    assert q.qsize() == 1


class _FlakyLogger:
    def __init__(self):
        self.logged = []
        self.calls = 0

    def log(self, name, item, value):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient sink failure")
        self.logged.append((name, item, value))


def test_run_logger_survives_a_sink_exception_and_keeps_going():
    q = queue.Queue()
    q.put(("reg", "voltage", 1))   # first call raises
    q.put(("reg", "voltage", 2))   # must still be processed
    stop = threading.Event()
    logger = _FlakyLogger()
    seen = []

    t = threading.Thread(
        target=supervisor.run_logger,
        args=(q, logger, stop),
        kwargs={"on_item": seen.append},
    )
    t.start()
    # wait until both items drained, then stop
    for _ in range(100):
        if logger.logged:
            break
        time.sleep(0.02)
    stop.set()
    t.join(timeout=3)

    assert not t.is_alive()               # loop did not die on the exception
    assert ("reg", "voltage", 2) in logger.logged
    assert "reg" in seen                  # on_item fired for the successful log


def test_run_logger_stops_when_event_set():
    q = queue.Queue()
    stop = threading.Event()
    stop.set()
    # Should return promptly because stop is already set.
    supervisor.run_logger(q, _FlakyLogger(), stop)


def test_liveness_reports_stale_after_timeout():
    clock = {"t": 1000.0}
    lt = supervisor.LivenessTracker(get_time=lambda: clock["t"])
    lt.expect("reg")
    lt.record("reg")            # fresh at t=1000
    clock["t"] = 1000.0 + 40
    assert lt.stale(30) == ["reg"]      # 40s > 30s timeout


def test_liveness_not_stale_when_recent():
    clock = {"t": 500.0}
    lt = supervisor.LivenessTracker(get_time=lambda: clock["t"])
    lt.expect("reg")
    clock["t"] = 500.0 + 10
    lt.record("reg")            # recorded at t=510
    clock["t"] = 500.0 + 20
    assert lt.stale(30) == []           # only 10s since last record


def test_expect_seeds_a_baseline_so_a_never_reporting_device_goes_stale():
    clock = {"t": 0.0}
    lt = supervisor.LivenessTracker(get_time=lambda: clock["t"])
    lt.expect("reg")            # baseline at t=0, never records
    clock["t"] = 100.0
    assert lt.stale(30) == ["reg"]
    assert lt.any_expected() is True
