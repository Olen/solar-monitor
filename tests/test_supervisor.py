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
