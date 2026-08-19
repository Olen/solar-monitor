"""SolarLink derives charge power from the voltage and current it reports.

Originally the `charge-power` branch (2026-07-17), which could not be merged:
it predates the protocol-module refactor and calls a method that no longer
exists.
"""

import pytest

from plugins.SolarLink import Util as SolarLinkPlugin


class _Entities:
    """Records what the plugin assigns, applying the same W -> mW scaling as
    the real `charge_power` property. Everything else is stored as given."""

    def __init__(self):
        self.charge_mpower = None

    @property
    def charge_power(self):
        return round(self.charge_mpower / 1000, 1)

    @charge_power.setter
    def charge_power(self, watts):
        self.charge_mpower = watts * 1000


class _Device:
    def __init__(self):
        self.entities = _Entities()
        self.device_id = 1


def battery_param_frame(decivolts, centiamps):
    """A full BatteryParamInfo response.

    header(3), soc(2), charge voltage(2), charge current(2), device temp(1),
    battery temp(1), load voltage(2), load current(2), load power(2).
    """
    return [0x01, 0x03, 0x0E,
            0x00, 0x64,                              # soc 100
            decivolts >> 8, decivolts & 0xFF,        # charge voltage, /10 V
            centiamps >> 8, centiamps & 0xFF,        # charge current, /100 A
            0x19,                                    # device temperature
            0x14,                                    # battery temperature
            0x00, 0x87,                              # load voltage
            0x00, 0x32,                              # load current
            0x00, 0x2A]                              # load power


@pytest.mark.parametrize(
    ("decivolts", "centiamps", "expected_watts"),
    [
        (135, 250, 13.5 * 2.5),      # 13.5 V at 2.5 A
        (0, 0, 0),                   # nothing coming in
        (288, 1000, 28.8 * 10.0),    # a 24 V bank charging hard
    ],
)
def test_charge_power_is_voltage_times_current(decivolts, centiamps, expected_watts):
    device = _Device()
    plugin = SolarLinkPlugin(power_device=device)
    plugin.updateBatteryParamInfo(battery_param_frame(decivolts, centiamps))
    assert device.entities.charge_power == pytest.approx(round(expected_watts, 1))


def test_voltage_and_current_are_still_reported():
    device = _Device()
    SolarLinkPlugin(power_device=device).updateBatteryParamInfo(battery_param_frame(135, 250))
    assert device.entities.charge_voltage == pytest.approx(13.5)
    assert device.entities.charge_current == pytest.approx(2.5)
