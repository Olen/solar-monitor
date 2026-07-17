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
