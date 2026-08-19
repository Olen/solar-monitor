"""Each device class's effective validation bounds.

`PowerDevice.__init__` defined `_mvoltage` twice — 48 V at its structural
position, then 15 V appended at the end of the block, which silently won. The
15 V value was a 12 V assumption that got its proper home in `BatteryDevice`
three days later (2020-06-29 c43473a, 2020-07-02 dcad6bf) and was left behind
in the base. `RegulatorDevice` never overrides, so it inherited the 12 V cap and
rejected every reading on a 24 V or 48 V system.

These assertions are cheap and would have caught a shadowed definition.
"""

import pytest

from solardevice import (BatteryDevice, InverterDevice, PowerDevice,
                         RectifierDevice, RegulatorDevice)


class _Parent:
    logger_name = "test-device"


@pytest.mark.parametrize(
    ("cls", "expected_max"),
    [
        (PowerDevice, 48000),       # 48 V, as its sibling voltages
        (RegulatorDevice, 48000),   # inherits; must cover 24 V and 48 V systems
        (BatteryDevice, 15000),     # a 12 V pack, declared on the subclass
        (RectifierDevice, 50000),
        (InverterDevice, 250000),
    ],
)
def test_effective_voltage_ceiling(cls, expected_max):
    assert cls(parent=_Parent())._mvoltage["max"] == expected_max


def test_a_24v_regulator_reading_is_accepted():
    """The bug: 29 V on a 24 V bank was rejected by the inherited 12 V cap."""
    regulator = RegulatorDevice(parent=_Parent())
    assert regulator.validate("_mvoltage", 29000) is None
    assert regulator._mvoltage["val"] == 29000


def test_a_48v_bank_still_needs_an_override():
    """Known limit, deliberately pinned.

    "48 V" is a nominal system voltage; such a bank charges to 54-58 V, above
    this ceiling. Deleting the shadowed definition fixes 12 V and 24 V systems.
    A 48 V one still needs `mvoltage_max` in its config section (#27/#63).
    """
    regulator = RegulatorDevice(parent=_Parent())
    assert regulator.validate("_mvoltage", 58000) is False


def test_a_battery_still_rejects_an_impossible_reading():
    """Narrowing on the subclass must survive: a 12 V pack is not 52 V."""
    battery = BatteryDevice(parent=_Parent())
    assert battery.validate("_mvoltage", 52000) is False


def test_powerdevice_bounds_are_all_real_rate_limits():
    """Every bound the base declares has maxdiff < max.

    That was the tell that the deleted definition was a draft: at 15000/15000
    it was the only entry here where the two were equal, permitting any jump
    inside range. (RectifierDevice and InverterDevice do use maxdiff == max on
    their own overrides, so this is a property of the base block, not the file.)
    """
    base = PowerDevice(parent=_Parent())
    for name, definition in base.__dict__.items():
        if isinstance(definition, dict) and {"min", "max", "maxdiff"} <= set(definition):
            assert definition["maxdiff"] < definition["max"], name
