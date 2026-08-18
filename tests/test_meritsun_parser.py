"""Regression tests for the Meritsun frame parser.

The notifications below are a real capture from a 12V100Ah pack (2026-08-18).
They decode to one complete frame; the pack was idle at the time, hence 0 A.
"""

import pytest

from plugins.Meritsun import Util


# One frame as delivered by BlueZ: 20-byte notifications, marker 0xC9.
CAPTURED_FRAME = [
    "c937463335303030303030303030303030",
    "4130393230313030334630303633303033303042",
    "3830383838374236343030453133304431363044",
    "3136304430303030303030303030303030303030",
    "3030303030303030303030303030303030303030",
    "303030303030303030303030303542440c0c0c0c",
    "0c0c0c0c92374633353030303030303030303030",
]


class _Entities:
    def __init__(self):
        self.values = {}

    def __setattr__(self, key, value):
        if key == "values":
            return object.__setattr__(self, key, value)
        self.values[key] = value


class _Config:
    def getboolean(self, *args, **kwargs):
        return False


class _Device:
    def __init__(self):
        self.config = _Config()
        self.entities = _Entities()

    def alias(self):
        return "test-pack"


@pytest.fixture
def util():
    return Util(_Device())


def feed(util, frames):
    return [util.notificationUpdate(bytes.fromhex(f), None) for f in frames]


def test_captured_frame_is_accepted(util):
    """A real frame must survive framing, the checksum gate and decoding."""
    assert any(feed(util, CAPTURED_FRAME)), "no frame accepted from a real capture"
    values = util.PowerDevice.entities.values
    assert values["mvoltage"] == 13695
    assert values["soc"] == 99
    assert values["temperature"] == 2864
    assert values["mcapacity"] == 103072


def test_cell_voltages_are_decoded(util):
    """Cells live past byte 40 and must come through on a full frame."""
    feed(util, CAPTURED_FRAME)
    assert "cell_mvoltage" in util.PowerDevice.entities.values


def test_c9_and_92_are_both_frame_markers(util):
    """0xC9 carries most frames; treating it as 'some other packet' loses them."""
    assert CAPTURED_FRAME[0].startswith("c9")


def test_fragments_are_rejected(util):
    """A truncated frame must not decode: the checksum is the only gate."""
    truncated = [f[:20] for f in CAPTURED_FRAME]
    assert not any(feed(util, truncated))
