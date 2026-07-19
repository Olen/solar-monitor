"""Per-device BLE connection maintenance.

Root cause (found on real hardware): with multiple BLE devices, a link connects
but often aborts during GATT service resolution; it is transient and succeeds on
retry. The behaviour that actually works on the hardware is the *old* code's:
connect every device concurrently (one thread each) straight after discovery,
and let the transient aborts be ridden out by retrying — strict serialization
made it worse, not better.

This module provides that: one `maintain_device` loop per device (run in its own
thread, so connects happen concurrently), with exponential backoff between failed
attempts. Trusting the device (done by the caller via SolarDevice.set_trusted)
keeps BlueZ from removing it as a 'temporary' device after ~30s and lets BlueZ
auto-reconnect it.

It is gatt-free and unit-testable: the actual gatt connect is supplied as
`connect_fn`.
"""
import logging
import random
import time

_MAX_BACKOFF_EXP = 30   # clamp the exponent so backoff can't grow to a bigint


def backoff_seconds(attempt, base=10.0, maximum=300.0, jitter=5.0, rand=None):
    """Exponential backoff for the Nth (1-based) consecutive failure, capped,
    with a random +/- `jitter` seconds. The jitter spreads out otherwise-
    synchronized retries across devices so their connect attempts don't all land
    at the same moment and collide (e.g. first retry lands somewhere in ~5-15s,
    not all at 10s). `rand` is injectable for deterministic tests."""
    if rand is None:
        rand = random.uniform
    attempt = min(max(attempt, 1), _MAX_BACKOFF_EXP)
    delay = min(base * (2 ** (attempt - 1)), maximum)
    return max(delay + rand(-jitter, jitter), 0.0)


def maintain_device(name, connect_fn, stop_event, base_backoff=10.0,
                    max_backoff=300.0, jitter=5.0, rand=None, sleep=None):
    """Keep one device connected until stop_event is set.

    `connect_fn()` performs one full connect attempt and BLOCKS until the device
    is no longer connected. It returns True if the device had connected (and has
    since dropped) or False if the attempt never connected. After a good
    connection we retry promptly; after a failed attempt we back off
    exponentially so a device that is off/out of range is not hammered.

    `sleep` defaults to `stop_event.wait` so backoff is interruptible on
    shutdown; tests inject their own.
    """
    if sleep is None:
        sleep = stop_event.wait
    attempt = 0
    while not stop_event.is_set():
        try:
            was_connected = connect_fn()
        except Exception as e:
            logging.error("[%s] connection loop error: %r", name, e)
            was_connected = False
        if stop_event.is_set():
            break
        if was_connected:
            attempt = 0                      # had a good connection — retry promptly
            continue
        attempt += 1
        delay = backoff_seconds(attempt, base_backoff, max_backoff, jitter, rand)
        logging.info("[%s] connect failed; retrying in %.1fs", name, delay)
        sleep(delay)
