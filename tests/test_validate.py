"""`PowerDevice.validate` bounds checking and the un-latching escape.

The maxdiff guard rejects readings that jump further than physically plausible.
Rejecting for ever latches the entity: `charge_cycles` is monotonic with
maxdiff 1, so one missed notification made every later reading out of band and
the value never moved again.
"""

import pytest

from solardevice import BatteryDevice


class _Parent:
    """`PowerDevice.name` is a read-only property reading through to the parent."""
    logger_name = "test-pack"


@pytest.fixture
def device():
    return BatteryDevice(parent=_Parent())


def set_cycles(dev, value):
    """validate() returns False on reject, None on accept."""
    return dev.validate('_charge_cycles', value) is None


def test_normal_increment_is_accepted(device):
    device._charge_cycles['val'] = 63
    assert set_cycles(device, 64)
    assert device._charge_cycles['val'] == 64


def test_a_jump_is_rejected_first(device):
    device._charge_cycles['val'] = 63
    assert not set_cycles(device, 65)
    assert device._charge_cycles['val'] == 63


def test_a_persistent_jump_is_eventually_believed(device):
    """The wedge: 64 was missed, so the pack now reports 65 for ever."""
    device._charge_cycles['val'] = 63
    assert not set_cycles(device, 65)
    assert not set_cycles(device, 65)
    assert set_cycles(device, 65)          # believed on the third
    assert device._charge_cycles['val'] == 65


def test_scattered_noise_is_never_believed(device):
    device._charge_cycles['val'] = 63
    for spurious in (400, 9000, 120, 7777, 250, 3000):
        assert not set_cycles(device, spurious)
    assert device._charge_cycles['val'] == 63


def test_the_counter_resets_after_an_accepted_value(device):
    device._charge_cycles['val'] = 63
    assert not set_cycles(device, 65)      # one rejection banked
    assert set_cycles(device, 64)          # normal reading accepted
    assert not set_cycles(device, 66)      # ...so this starts from scratch
    assert not set_cycles(device, 66)
    assert set_cycles(device, 66)


def test_hard_bounds_are_never_escaped(device):
    """min/max are physical limits, not rate limits -- no escape from them."""
    device._charge_cycles['val'] = 63
    for _ in range(5):
        assert not set_cycles(device, 99999)   # above max
        assert not set_cycles(device, -1)      # below min
    assert device._charge_cycles['val'] == 63
