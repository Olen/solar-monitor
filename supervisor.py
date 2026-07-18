"""Hardware-free supervision helpers: queueing, the logger loop, liveness.

This module deliberately does NOT import gatt so it can be unit-tested without
Bluetooth. solar-monitor.py and solardevice.py import from here.
"""
import logging
import queue
import time


def try_put(q, item):
    """Enqueue without ever blocking. Returns True on success, False if full."""
    try:
        q.put_nowait(item)
        return True
    except queue.Full:
        return False


def run_logger(queue_obj, datalogger, stop_event, on_item=None, get_time=time.time):
    """Drain the queue into datalogger.log(), forever, until stop_event is set.

    A per-item failure (sink down, decode bug) is logged and skipped — it must
    NEVER terminate this loop, because the producers block behind a full queue.
    """
    last_report = get_time()
    while not stop_event.is_set():
        try:
            logger_name, item, value = queue_obj.get(timeout=1.0)
        except queue.Empty:
            continue
        try:
            datalogger.log(logger_name, item, value)
            if on_item is not None:
                on_item(logger_name)
        except Exception as e:
            logging.error("datalogger.log failed for %s/%s: %s", logger_name, item, e)

        now = get_time()
        if now > last_report + 1 and not queue_obj.empty():
            logging.debug("Queue size = %s", queue_obj.qsize())
            last_report = now


class LivenessTracker:
    """Tracks the last time each expected device produced a reading."""

    def __init__(self, get_time=time.time):
        self._get_time = get_time
        self._last = {}

    def expect(self, name):
        """Register a device we require data from; seeds a baseline timestamp."""
        self._last.setdefault(name, self._get_time())

    def record(self, name):
        """Note that `name` just produced a reading."""
        self._last[name] = self._get_time()

    def stale(self, timeout_s):
        """Return the names with no reading within the last `timeout_s` seconds."""
        now = self._get_time()
        return [n for n, t in self._last.items() if now - t > timeout_s]

    def any_expected(self):
        return bool(self._last)

    def expected_count(self):
        """Number of devices registered via expect()."""
        return len(self._last)


def supervise(device_manager, logger_future, liveness, stop_event,
              check_interval=30.0, stale_timeout=600.0, get_time=time.time,
              on_tick=None):
    """Watch the daemon's health until stop_event, then return an exit code.

    Returns 1 (so systemd restarts) if the consumer thread died or every
    expected device has gone stale; 0 on a clean requested stop.
    """
    while not stop_event.wait(check_interval):
        if on_tick is not None:
            on_tick()
        if logger_future is not None and logger_future.done():
            exc = logger_future.exception()
            if exc is not None:
                logging.error("Consumer thread died: %r; exiting for restart.", exc, exc_info=exc)
            else:
                logging.error("Consumer thread exited unexpectedly; exiting for restart.")
            device_manager.stop()
            return 1
        if liveness.any_expected():
            stale = liveness.stale(stale_timeout)
            if len(stale) == liveness.expected_count():  # every expected device is stale
                logging.error("No data from any device in %ss (%s); exiting for restart.",
                              stale_timeout, ", ".join(sorted(stale)))
                device_manager.stop()
                return 1
    return 0
