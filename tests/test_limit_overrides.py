"""Per-device limit overrides from the config section (#27).

The shipped bounds suit one set of hardware. A Rover 60 with two 24 V panels in
series reaches nearly 70 V, above the default input-voltage ceiling, and every
reading is then rejected as out of bands.
"""

import configparser

import pytest

from solardevice import RegulatorDevice


class _Parent:
    logger_name = "regulator"


def make_config(**options):
    config = configparser.ConfigParser()
    config["regulator"] = {"type": "SolarLink", "mac": "aa:bb:cc:dd:ee:ff", **options}
    return config


@pytest.fixture
def device():
    return RegulatorDevice(parent=_Parent())


def test_defaults_are_kept_without_overrides(device):
    before = dict(device._input_mvoltage)
    device.apply_limit_overrides(make_config(), "regulator")
    assert device._input_mvoltage == before


def test_max_is_overridden(device):
    device.apply_limit_overrides(make_config(input_mvoltage_max="96000"), "regulator")
    assert device._input_mvoltage["max"] == 96000


def test_all_three_bounds_are_tunable(device):
    device.apply_limit_overrides(
        make_config(input_mvoltage_min="10", input_mvoltage_max="96000",
                    input_mvoltage_maxdiff="48000"),
        "regulator",
    )
    assert device._input_mvoltage["min"] == 10
    assert device._input_mvoltage["max"] == 96000
    assert device._input_mvoltage["maxdiff"] == 48000


def test_an_overridden_ceiling_lets_the_reading_through(device):
    """The point of the issue: 70 V input is rejected until max is raised."""
    device._input_mvoltage["val"] = 60000
    assert device.validate("_input_mvoltage", 70000) is False   # above the default max

    device.apply_limit_overrides(make_config(input_mvoltage_max="96000"), "regulator")
    assert device.validate("_input_mvoltage", 70000) is None    # accepted
    assert device._input_mvoltage["val"] == 70000


def test_unknown_options_are_ignored(device):
    device.apply_limit_overrides(make_config(nonsense_max="1", type_max="2"), "regulator")
    assert device._input_mvoltage["max"] != 1


def test_a_non_numeric_override_keeps_the_default(device):
    default = device._input_mvoltage["max"]
    device.apply_limit_overrides(make_config(input_mvoltage_max="very high"), "regulator")
    assert device._input_mvoltage["max"] == default


def test_missing_section_is_harmless(device):
    before = dict(device._input_mvoltage)
    device.apply_limit_overrides(make_config(), "no-such-device")
    device.apply_limit_overrides(None, "regulator")
    assert device._input_mvoltage == before


def test_cell_mvoltage_is_not_mistaken_for_a_limit_dict(device):
    """`_cell_mvoltage` is a dict of cells, not a bounds definition."""
    device.apply_limit_overrides(make_config(cell_mvoltage_max="9"), "regulator")
    assert "max" not in device._cell_mvoltage
