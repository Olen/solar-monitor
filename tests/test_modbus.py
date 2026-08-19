"""`modbus` — RTU framing shared by RenogyBatt and SolarLink.

These assertions were written against the two plugins' own copies (#72), where
they pinned that the copies agreed. The copies are now one module; the
assertions are unchanged, they just call it directly.
"""

import pytest

import modbus


# --- bytes_to_int: forwards for a positive length, backwards for negative ----

BYTES_TO_INT_CASES = [
    # (frame,                    offset, length, expected)
    ([0x00, 0x01, 0x02, 0x03],   0,      1,      0x00),
    ([0x00, 0x01, 0x02, 0x03],   1,      1,      0x01),
    ([0x00, 0x01, 0x02, 0x03],   1,      2,      0x0102),
    ([0x00, 0x01, 0x02, 0x03],   0,      4,      0x00010203),
    ([0x12, 0x34, 0x56, 0x78],   3,     -2,      0x7856),   # reads backwards
    ([0x12, 0x34],               0,      4,      0),        # past the end -> 0
    ([],                         0,      1,      0),        # empty -> 0
]


@pytest.mark.parametrize(("frame", "offset", "length", "expected"), BYTES_TO_INT_CASES)
def test_bytes_to_int(frame, offset, length, expected):
    assert modbus.bytes_to_int(frame, offset, length) == expected


# --- high_byte / low_byte ----------------------------------------------------

@pytest.mark.parametrize(
    ("value", "high", "low"),
    [
        (0x0000, 0x00, 0x00),
        (0x00FF, 0x00, 0xFF),
        (0xFF00, 0xFF, 0x00),
        (0x1234, 0x12, 0x34),
        (266,    0x01, 0x0A),      # the SolarLink load register
    ],
)
def test_a_16_bit_value_splits_into_its_two_bytes(value, high, low):
    assert modbus.high_byte(value) == high
    assert modbus.low_byte(value) == low


# --- ack_payload -------------------------------------------------------------

def test_ack_payload_echoes_the_first_response_byte():
    assert modbus.ack_payload([0xAB]) == bytearray(b"main recv da ta[ab] [")


# --- validate_frame ----------------------------------------------------------

def modbus_frame(payload, crc_value):
    """address, function, length, payload..., then the CRC.

    `validate_frame` reads the trailing CRC with a negative length — a
    little-endian read of the last two bytes — so they go low byte first.
    """
    body = [0x01, 0x03, len(payload)] + list(payload)
    return body + [modbus.low_byte(crc_value), modbus.high_byte(crc_value)]


def patch_crc(monkeypatch, value):
    """Force the CRC so validate_frame's own logic is what is under test."""
    monkeypatch.setattr(modbus.libscrc, "modbus", lambda _bytes: value)


def test_a_frame_whose_crc_matches_is_accepted(monkeypatch):
    patch_crc(monkeypatch, 0xBEEF)
    assert modbus.validate_frame(modbus_frame([0x11, 0x22], 0xBEEF)) is True


def test_a_frame_whose_crc_does_not_match_is_rejected(monkeypatch):
    patch_crc(monkeypatch, 0xBEEF)
    assert modbus.validate_frame(modbus_frame([0x11, 0x22], 0xDEAD)) is False


@pytest.mark.parametrize("frame", [None, [], [0x01, 0x03], [0x01, 0x03, 0x02, 0x00]])
def test_a_frame_that_is_too_short_is_rejected(frame):
    assert modbus.validate_frame(frame) is False


def test_a_write_response_is_accepted_without_a_length_check():
    """Function 6 is the reply to a write and carries no payload to check."""
    assert modbus.validate_frame([0x01, modbus.FUNCTION_WRITE_RESPONSE, 0x99, 0x00, 0x00]) is True
