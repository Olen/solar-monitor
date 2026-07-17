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
