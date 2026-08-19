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


def test_plugins_agree_with_the_shared_accessor():
    """Meritsun and Topband hand-rolled this identically; both now delegate."""
    from plugins.Meritsun import Util as Meritsun
    from plugins.Topband import Util as Topband

    for start, end in ((0, 3), (0, 7), (4, 11)):
        expected = field_value(FRAME, start, end)
        assert Meritsun.getValue(None, FRAME, start, end) == expected
        assert Topband.getValue(None, FRAME, start, end) == expected
