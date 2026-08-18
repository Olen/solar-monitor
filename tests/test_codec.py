"""Two's-complement decoding shared by the battery plugins.

Each plugin used to open-code this with its own constant, and all four were one
LSB short (2**bits - 1 instead of 2**bits).
"""

import pytest

from codec import INT32_MAX, UINT16_WRAP, UINT32_WRAP, to_signed
from plugins.RenogyBatt import CURRENT_WRAP, SIGN_THRESHOLD, TEMPERATURE_WRAP


def test_positive_values_pass_through():
    assert to_signed(1000, UINT32_WRAP, INT32_MAX) == 1000
    assert to_signed(INT32_MAX, UINT32_WRAP, INT32_MAX) == INT32_MAX


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (UINT32_WRAP - 1, -1),
        (UINT32_WRAP - 1000, -1000),
        (INT32_MAX + 1, -(INT32_MAX + 1)),
    ],
)
def test_negative_32bit_values(raw, expected):
    assert to_signed(raw, UINT32_WRAP, INT32_MAX) == expected


def test_one_lsb_negative_is_not_zero():
    """The old constant (2**32 - 1) decoded -1 as 0."""
    assert to_signed(UINT32_WRAP - 1, UINT32_WRAP, INT32_MAX) == -1
    assert (UINT32_WRAP - 1) - (UINT32_WRAP - 1) == 0  # what it used to do


def test_renogy_wrap_points():
    assert CURRENT_WRAP == 655.36
    assert TEMPERATURE_WRAP == 6553.6


def test_renogy_current_smallest_discharge():
    """Raw 65535 is one LSB negative: -0.01 A, not the +0.01 A it used to give."""
    assert to_signed(65535 * .01, CURRENT_WRAP, SIGN_THRESHOLD) == pytest.approx(-0.01)
    assert 65535 * .01 - 655.34 == pytest.approx(+0.01)  # the old bias, 0.02 A high


def test_renogy_current_charging_unaffected():
    assert to_signed(12.34, CURRENT_WRAP, SIGN_THRESHOLD) == pytest.approx(12.34)


def test_renogy_temperature_below_zero():
    assert to_signed(65531 * .1, TEMPERATURE_WRAP, SIGN_THRESHOLD) == pytest.approx(-0.5)


def test_threshold_is_practical_not_arithmetic():
    """Renogy signs off 255, not the 16-bit sign bit -- a 300 A reading is negative."""
    assert SIGN_THRESHOLD == 255
    assert to_signed(300.0, CURRENT_WRAP, SIGN_THRESHOLD) < 0
    assert UINT16_WRAP // 2 - 1 != SIGN_THRESHOLD
