import queue
import re

import solardevice  # conftest stubs gatt


def _make_device():
    # SolarDevice.__init__ returns early (no plugin import) when type is None,
    # which is exactly the lightweight object we want for enqueue tests.
    dev = solardevice.SolarDevice(
        mac_address="11:22:33:44:55:66", manager=None, queue=queue.Queue(maxsize=1)
    )
    return dev


def test_enqueue_puts_item_when_space():
    dev = _make_device()
    dev._enqueue(("regulator", "voltage", 13.2))
    assert dev.queue.qsize() == 1
    assert dev._dropped == 0


def test_enqueue_drops_and_counts_when_full_without_blocking():
    dev = _make_device()
    dev._enqueue(("regulator", "voltage", 13.2))   # fills the maxsize=1 queue
    dev._enqueue(("regulator", "current", 5.0))    # would block a real put(); must drop
    assert dev.queue.qsize() == 1
    assert dev._dropped == 1


def test_no_blocking_queue_put_calls_remain():
    with open("solardevice.py") as fh:
        src = fh.read()
    # self.queue.put( ... ) blocks; only self.queue.put_nowait / try_put allowed.
    assert not re.search(r"self\.queue\.put\(", src), (
        "found a blocking self.queue.put( in solardevice.py"
    )


def test_power_device_power_switch_setter_enqueues_via_parent():
    # PowerDevice is NOT a SolarDevice subclass; it holds a `parent` reference
    # to the owning SolarDevice and has no _enqueue of its own. The setter
    # must therefore call self.parent._enqueue(...), not self._enqueue(...).
    dev = _make_device()
    power_device = solardevice.PowerDevice(parent=dev)

    power_device.power_switch = 1

    assert dev.queue.qsize() == 1
    assert dev.queue.get_nowait() == (dev.logger_name, "power_switch", 1)
    assert dev._dropped == 0
