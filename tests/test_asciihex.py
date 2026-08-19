"""`asciihex.field_value` — reading an ASCII-hex field from a frame."""

import pytest

from asciihex import field_value


FRAME = [ord(c) for c in "0123456789AB"]


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [(0, 3, 0x2301), (0, 7, 0x67452301), (4, 11, 0xAB896745)],
)
def test_ascii_hex_reads_low_pair_first(start, end, expected):
    assert field_value(FRAME, start, end) == expected


@pytest.mark.parametrize(
    ("start", "end"),
    [(0, 12), (10, 40), (12, 15), (-1, 3)],
)
def test_truncated_frame_returns_default_instead_of_raising(start, end):
    """Topband used to raise IndexError here, straight into the BLE callback."""
    assert field_value(FRAME, start, end) == 0


def test_default_is_configurable():
    assert field_value(FRAME, 0, 40, default=None) is None


def test_non_hex_payload_returns_default():
    assert field_value([ord(c) for c in "ZZZZ"], 0, 3) == 0


def test_end_before_start_is_rejected():
    assert field_value(FRAME, 6, 2) == 0


# --- checksum_matches --------------------------------------------------------

from asciihex import checksum_matches


def ascii_hex_frame(text):
    return [ord(c) for c in text]


def test_a_frame_whose_trailing_sum_matches_is_accepted():
    """Four fields of 0x01 are summed; the trailing two hold that sum, 0x0004."""
    assert checksum_matches(ascii_hex_frame("X010101010004"), 13) is True


def test_a_frame_whose_trailing_sum_does_not_match_is_rejected():
    assert checksum_matches(ascii_hex_frame("X010101019900"), 13) is False
