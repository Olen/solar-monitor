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


# --- ascii_hex_value -------------------------------------------------------

from codec import ascii_hex_value

FRAME = [ord(c) for c in "0123456789AB"]


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [(0, 3, 0x2301), (0, 7, 0x67452301), (4, 11, 0xAB896745)],
)
def test_ascii_hex_reads_low_pair_first(start, end, expected):
    assert ascii_hex_value(FRAME, start, end) == expected


@pytest.mark.parametrize(
    ("start", "end"),
    [(0, 12), (10, 40), (12, 15), (-1, 3)],
)
def test_truncated_frame_returns_default_instead_of_raising(start, end):
    """Topband used to raise IndexError here, straight into the BLE callback."""
    assert ascii_hex_value(FRAME, start, end) == 0


def test_default_is_configurable():
    assert ascii_hex_value(FRAME, 0, 40, default=None) is None


def test_non_hex_payload_returns_default():
    assert ascii_hex_value([ord(c) for c in "ZZZZ"], 0, 3) == 0


def test_end_before_start_is_rejected():
    assert ascii_hex_value(FRAME, 6, 2) == 0


def test_plugins_agree_with_the_shared_accessor():
    """Meritsun and Topband hand-rolled this identically; both now delegate."""
    from plugins.Meritsun import Util as Meritsun
    from plugins.Topband import Util as Topband

    for start, end in ((0, 3), (0, 7), (4, 11)):
        expected = ascii_hex_value(FRAME, start, end)
        assert Meritsun.getValue(None, FRAME, start, end) == expected
        assert Topband.getValue(None, FRAME, start, end) == expected
