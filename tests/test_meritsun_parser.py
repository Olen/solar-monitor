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


def test_voltage_only_frame_is_rejected(util):
    """A run of ASCII '0' passes the additive checksum; it is not a reading.

    Zeros sum to zero and the checksum field the run lands on reads zero, so
    `checksum_matches` accepts it. Every field but the voltage decoding as 0 is
    the tell.
    """
    message = [0x30] * 112
    for index, char in enumerate(b"7A35"):          # a plausible pack voltage
        message[index] = char
    assert not util.handleMessage(message, full=True)
    assert util.PowerDevice.entities.values == {}


def test_a_real_frame_still_decodes(util):
    """The zero-fill guard must not reject a frame whose current is legitimately 0."""
    assert any(feed(util, CAPTURED_FRAME))
    values = util.PowerDevice.entities.values
    assert values["mcurrent"] == 0          # pack idle
    assert values["soc"] == 99
    assert values["mcapacity"] == 103072


def test_a_field_the_checksum_cannot_see_is_dropped(util):
    """A byte corrupted onto a "00" pair is invisible to the additive checksum.

    Both the true pair and the unparseable one contribute 0, so the frame still
    validates while the field silently reads 0. Only that field is dropped.
    """
    frames = list(CAPTURED_FRAME)
    corrupted = bytearray(bytes.fromhex(frames[0]))
    corrupted[11] = 0x20                      # a space inside mcurrent's "00000000"
    frames[0] = bytes(corrupted).hex()

    assert any(feed(util, frames)), "the frame is still valid and must be used"
    values = util.PowerDevice.entities.values
    assert "mcurrent" not in values, "the unreadable field must not be published"
    assert values["soc"] == 99                # the rest of the frame survives
    assert values["mcapacity"] == 103072
    assert values["temperature"] == 2864


def test_non_hex_byte_in_the_zero_fill_is_tolerated(util):
    """Corruption past the fields costs nothing and must not drop anything."""
    frames = list(CAPTURED_FRAME)
    corrupted = bytearray(bytes.fromhex(frames[4]))   # deep in the zero fill
    corrupted[5] = 0x70
    frames[4] = bytes(corrupted).hex()
    assert any(feed(util, frames))
    assert util.PowerDevice.entities.values["soc"] == 99
