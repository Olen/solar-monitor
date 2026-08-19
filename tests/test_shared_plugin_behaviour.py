"""Pins the behaviour of the plugin methods that are candidates for sharing.

Written before any code moves (#46). Each test asserts that both members of a
pair produce the *same* result for the same input — which is the property that
licenses sharing them at all — and pins what that result is, so a later move
into a common module cannot change it unnoticed.

Only genuinely identical methods are covered. `notificationUpdate`,
`create_poll_request`, `pollRequest` and `handleMessage` differ per device by
design and are deliberately absent.
"""

import pytest

from plugins.Meritsun import Util as MeritsunUtil
from plugins.RenogyBatt import Util as RenogyBattUtil
from plugins.SolarLink import Util as SolarLinkUtil
from plugins.Topband import Util as TopbandUtil

MODBUS_PLUGINS = [RenogyBattUtil, SolarLinkUtil]
ASCII_HEX_PLUGINS = [MeritsunUtil, TopbandUtil]


def make_decoder(plugin_class):
    """A plugin instance usable for pure decoding, with no device attached."""
    return plugin_class(power_device=None)


# --- Bytes2Int: big-endian for a positive length, little-endian for negative --

BYTES2INT_CASES = [
    # (frame,                    offset, length, expected)
    ([0x00, 0x01, 0x02, 0x03],   0,      1,      0x00),
    ([0x00, 0x01, 0x02, 0x03],   1,      1,      0x01),
    ([0x00, 0x01, 0x02, 0x03],   1,      2,      0x0102),
    ([0x00, 0x01, 0x02, 0x03],   0,      4,      0x00010203),
    ([0x12, 0x34, 0x56, 0x78],   3,     -2,      0x7856),   # negative reads backwards
    ([0x12, 0x34],               0,      4,      0),        # past the end -> 0
    ([],                         0,      1,      0),        # empty -> 0
]


@pytest.mark.parametrize("plugin_class", MODBUS_PLUGINS)
@pytest.mark.parametrize(("frame", "offset", "length", "expected"), BYTES2INT_CASES)
def test_bytes2int_is_identical_across_modbus_plugins(plugin_class, frame, offset, length, expected):
    assert make_decoder(plugin_class).Bytes2Int(frame, offset, length) == expected


# --- Int2Bytes: the high or low byte of a 16-bit value -----------------------

INT2BYTES_CASES = [
    (0x0000, 0x00, 0x00),
    (0x00FF, 0x00, 0xFF),
    (0xFF00, 0xFF, 0x00),
    (0x1234, 0x12, 0x34),
    (266,    0x01, 0x0A),      # the SolarLink load register
]


@pytest.mark.parametrize("plugin_class", MODBUS_PLUGINS)
@pytest.mark.parametrize(("value", "high", "low"), INT2BYTES_CASES)
def test_int2bytes_is_identical_across_modbus_plugins(plugin_class, value, high, low):
    decoder = make_decoder(plugin_class)
    assert decoder.Int2Bytes(value, 0) == high
    assert decoder.Int2Bytes(value, 1) == low


@pytest.mark.parametrize("plugin_class", MODBUS_PLUGINS)
def test_int2bytes_returns_zero_for_an_unknown_position(plugin_class):
    assert make_decoder(plugin_class).Int2Bytes(0x1234, 2) == 0


# --- ackData -----------------------------------------------------------------

@pytest.mark.parametrize("plugin_class", MODBUS_PLUGINS)
def test_ackdata_is_identical_across_modbus_plugins(plugin_class):
    assert make_decoder(plugin_class).ackData([0xAB]) == bytearray(b"main recv da ta[ab] [")


# --- Validate: modbus frame checks, with the CRC pinned ----------------------

def modbus_frame(payload, crc_value):
    """address, function, length, payload..., then the CRC.

    `Validate` reads the trailing CRC with `Bytes2Int(offset=len-1, length=-2)`,
    a little-endian read of the last two bytes, so they go low byte first.
    """
    body = [0x01, 0x03, len(payload)] + list(payload)
    return body + [crc_value & 0xFF, crc_value >> 8]


def patch_crc(monkeypatch, plugin_class, value):
    """Force the modbus CRC so Validate's own logic is what is under test."""
    module = __import__(plugin_class.__module__, fromlist=["libscrc"])
    monkeypatch.setattr(module.libscrc, "modbus", lambda _bytes: value)


@pytest.mark.parametrize("plugin_class", MODBUS_PLUGINS)
def test_validate_accepts_a_frame_whose_crc_matches(plugin_class, monkeypatch):
    patch_crc(monkeypatch, plugin_class, 0xBEEF)
    assert make_decoder(plugin_class).Validate(modbus_frame([0x11, 0x22], 0xBEEF)) is True


@pytest.mark.parametrize("plugin_class", MODBUS_PLUGINS)
def test_validate_rejects_a_frame_whose_crc_does_not_match(plugin_class, monkeypatch):
    patch_crc(monkeypatch, plugin_class, 0xBEEF)
    assert make_decoder(plugin_class).Validate(modbus_frame([0x11, 0x22], 0xDEAD)) is False


@pytest.mark.parametrize("plugin_class", MODBUS_PLUGINS)
@pytest.mark.parametrize("frame", [None, [], [0x01, 0x03], [0x01, 0x03, 0x02, 0x00]])
def test_validate_rejects_a_frame_that_is_too_short(plugin_class, frame):
    assert make_decoder(plugin_class).Validate(frame) is False


@pytest.mark.parametrize("plugin_class", MODBUS_PLUGINS)
def test_validate_accepts_a_write_response_without_checking_length(plugin_class):
    """Function 6 is the reply to a write and is passed through."""
    assert make_decoder(plugin_class).Validate([0x01, 0x06, 0x99, 0x00, 0x00]) is True


# --- validateChecksum: the ASCII-hex pair ------------------------------------

def ascii_hex_frame(text):
    return [ord(c) for c in text]


@pytest.mark.parametrize("plugin_class", ASCII_HEX_PLUGINS)
def test_validatechecksum_accepts_a_frame_whose_sum_matches(plugin_class):
    decoder = make_decoder(plugin_class)
    # Four bytes of 0x01 are summed; the trailing two hold that sum, 0x0004.
    decoder.end = 13
    assert decoder.validateChecksum(ascii_hex_frame("X010101010004")) is True


@pytest.mark.parametrize("plugin_class", ASCII_HEX_PLUGINS)
def test_validatechecksum_rejects_a_frame_whose_sum_does_not_match(plugin_class):
    decoder = make_decoder(plugin_class)
    decoder.end = 13
    assert decoder.validateChecksum(ascii_hex_frame("X010101019900")) is False


@pytest.mark.parametrize("plugin_class", ASCII_HEX_PLUGINS)
def test_validatechecksum_is_identical_across_ascii_hex_plugins(plugin_class):
    """Both implementations must agree field for field, not just accept/reject."""
    decoder = make_decoder(plugin_class)
    decoder.end = 13
    frame = ascii_hex_frame("X010101010004")
    reference = MeritsunUtil(power_device=None)
    reference.end = 13
    assert decoder.validateChecksum(frame) == reference.validateChecksum(frame)
