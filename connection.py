"""Serialized, patient BLE connection coordinator.

Root cause (found on real hardware): BLE links connect but then abort during
GATT service resolution (`le-connection-abort-by-local`). It is transient and
succeeds on retry, but the old code fired every device's connect and every
10-second reconnect concurrently, so attempts collided and never let the
devices/adapter settle.

This module owns the *policy* — which device to (re)connect next, one at a time,
with exponential backoff — and is deliberately gatt-free so it is unit-testable
without Bluetooth. The actual connect is performed by a caller-supplied
`connect_fn` (see run_connection_loop), which does the gatt connect and blocks
until the device resolves services or the attempt fails/times out.
"""
import logging
import time


class ConnectionCoordinator:
    """Tracks per-device connection state and decides what to connect next.

    Only ever hands out one device at a time via next_due(); the caller connects
    it (blocking) and reports the outcome to record_result(). Failures back off
    exponentially so a flapping device does not get hammered.
    """

    def __init__(self, base_backoff=5.0, max_backoff=300.0, get_time=time.time):
        self._get_time = get_time
        self.base_backoff = base_backoff
        self.max_backoff = max_backoff
        self._state = {}  # key -> {"connected": bool, "attempts": int, "next_attempt": float}

    def add(self, key):
        """Register a device to be kept connected."""
        self._state.setdefault(key, {"connected": False, "attempts": 0, "next_attempt": 0.0})

    def _backoff(self, attempts):
        return min(self.base_backoff * (2 ** (attempts - 1)), self.max_backoff)

    def next_due(self):
        """The key of the next disconnected device whose backoff has elapsed, or
        None. Earliest-due first, then by key for determinism."""
        now = self._get_time()
        due = [(s["next_attempt"], k) for k, s in self._state.items()
               if not s["connected"] and s["next_attempt"] <= now]
        if not due:
            return None
        due.sort()
        return due[0][1]

    def record_result(self, key, success):
        """Report the outcome of a connection attempt for `key`."""
        s = self._state[key]
        if success:
            s["connected"] = True
            s["attempts"] = 0
            s["next_attempt"] = 0.0
        else:
            s["attempts"] += 1
            s["next_attempt"] = self._get_time() + self._backoff(s["attempts"])

    def mark_disconnected(self, key):
        """A previously-connected device dropped; queue it for reconnect after a
        short settle delay (not immediately, to avoid hammering a flapper)."""
        s = self._state.get(key)
        if s is None:
            return
        s["connected"] = False
        s["attempts"] = 0
        s["next_attempt"] = self._get_time() + self.base_backoff

    def connected_count(self):
        return sum(1 for s in self._state.values() if s["connected"])

    def all_connected(self):
        return all(s["connected"] for s in self._state.values()) if self._state else True


def run_connection_loop(coordinator, connect_fn, stop_event, get_time=time.time,
                        sleep=time.sleep, on_idle=None, idle_sleep=1.0):
    """Serially connect due devices until stop_event is set.

    connect_fn(key) -> bool performs the actual (blocking) gatt connect and
    returns True if the device resolved services. Because it blocks, only ONE
    connection attempt is ever in flight — that serialization is the whole point.
    on_idle() is called whenever nothing is due (useful to check for completion).
    """
    while not stop_event.is_set():
        key = coordinator.next_due()
        if key is None:
            if on_idle is not None:
                on_idle()
            if stop_event.is_set():
                break
            sleep(idle_sleep)
            continue
        try:
            success = connect_fn(key)
        except Exception as e:
            logging.error("connect_fn(%s) raised: %r", key, e)
            success = False
        coordinator.record_result(key, success)
