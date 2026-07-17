import threading
import supervisor


class _FakeFuture:
    def __init__(self, done=False):
        self._done = done

    def done(self):
        return self._done


class _FakeDM:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


def test_supervise_exits_1_when_logger_future_dies():
    dm = _FakeDM()
    fut = _FakeFuture(done=True)  # consumer thread died
    lt = supervisor.LivenessTracker()
    stop = threading.Event()
    rc = supervisor.supervise(dm, fut, lt, stop, check_interval=0.01, stale_timeout=999)
    assert rc == 1
    assert dm.stopped is True


def test_supervise_exits_1_when_all_devices_stale():
    clock = {"t": 0.0}
    lt = supervisor.LivenessTracker(get_time=lambda: clock["t"])
    lt.expect("reg")
    dm = _FakeDM()
    fut = _FakeFuture(done=False)
    stop = threading.Event()

    # advance the clock past the stale timeout on the first check
    def tick():
        clock["t"] += 100

    rc = supervisor.supervise(
        dm, fut, lt, stop, check_interval=0.01, stale_timeout=30,
        get_time=lambda: clock["t"], on_tick=tick,
    )
    assert rc == 1


def test_supervise_returns_0_on_clean_stop():
    dm = _FakeDM()
    fut = _FakeFuture(done=False)
    lt = supervisor.LivenessTracker()  # nothing expected -> never stale
    stop = threading.Event()
    stop.set()  # already asked to stop
    rc = supervisor.supervise(dm, fut, lt, stop, check_interval=0.01, stale_timeout=30)
    assert rc == 0
