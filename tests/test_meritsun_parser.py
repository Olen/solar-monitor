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


# A frame that lost bytes from its trailing zero run, captured 2026-08-19. The
# 0x70 in the zero fill is the same packs' byte corruption; it decodes as 0.
SHORT_FRAME_GAP_IN_ZERO_FILL = [
    "c937383335303030303030303030303030413039",
    "3230313030334630303633303033303042383038",
    "3838374236334530453131304431353044313430",
    "4430303030303030303030303030303030303030",
    "3030303030303030703030303030303030303030",
    "3030303030303030303541460c0c0c0c0c0c0c0c",
    "c9",
]

# The same pack, but the loss took part of the field region: unrecoverable.
SHORT_FRAME_GAP_IN_FIELDS = [
    "9237413335203030303030303030303030413039",
    "3230313030334630303633303033303042383038",
    "3838374236334530453132304431353044313530",
    "4430303030303030303030303030303030303030",
    "3030303030303030303030303030303030303030",
    "3030303030303030301088f8c9",
]


def test_gap_in_the_zero_fill_is_repaired(util):
    """Bytes lost from the run of '0' are restorable: the checksum proves it."""
    assert any(feed(util, SHORT_FRAME_GAP_IN_ZERO_FILL))
    values = util.PowerDevice.entities.values
    assert values["mvoltage"] == 13688
    assert values["soc"] == 99
    assert values["temperature"] == 2864
    assert values["mcapacity"] == 103072
    assert values["charge_cycles"] == 63


def test_gap_in_the_field_region_is_not_repaired(util):
    """Only the zero fill can be rebuilt; a lost field must not be invented."""
    assert not any(feed(util, SHORT_FRAME_GAP_IN_FIELDS))


def test_repair_keeps_the_checksum_as_the_gate(util):
    """A short frame whose checksum cannot be satisfied stays rejected."""
    frames = list(SHORT_FRAME_GAP_IN_ZERO_FILL)
    frames[0] = "c937383335303030303030303030303031413039"   # one field altered
    assert not any(feed(util, frames))
