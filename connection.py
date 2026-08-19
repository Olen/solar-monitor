"""Shared BLE connection-retry helpers.

Root cause (found on real hardware): with multiple BLE devices, a link connects
but often aborts during GATT service resolution; it is transient and succeeds on
retry. Exponential backoff (with jitter, so retries across devices don't all
land at once) is the shared policy used for retrying failed connects.

The thread-based connection loops that used to live here (`maintain_device`,
`rotate_devices`, built on the abandoned `gatt` library) were replaced by the
asyncio `maintain_device` in `ble.py` (bleak-based), which imports
`backoff_seconds` from this module.
"""
import asyncio
import logging
import random

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


async def write_with_retry(client, char_uuid, value, lock=None, attempts=2,
                           delay=0.2, sleep=None, name=""):
    """Write a characteristic, retrying a transient failure once.

    Commands only. A poll payload is already stale by the time its write fails
    and the next poll asks the same question a moment later, so `ble._hold`
    deliberately does not use this. A command is a user action that nothing
    else repeats -- if the switch write is dropped, the switch simply does not
    move -- so it is worth one more attempt.

    Returns True if the write was accepted.
    """
    sleep = sleep or asyncio.sleep
    for attempt in range(1, attempts + 1):
        try:
            if lock is not None:
                async with lock:
                    await client.write_gatt_char(char_uuid, value)
            else:
                await client.write_gatt_char(char_uuid, value)
            return True
        except Exception as e:
            if attempt < attempts:
                logging.debug("[%s] write failed (%r); retrying", name, e)
                await sleep(delay)
                continue
            logging.warning("[%s] write failed after %d attempts: %r", name, attempts, e)
    return False
