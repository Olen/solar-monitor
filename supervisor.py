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
