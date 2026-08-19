"""Modbus RTU framing, shared by the plugins that speak it.

What differs per device -- which registers to poll, how to build a request, how
to interpret a response -- belongs in the plugin.
"""

import logging

import libscrc

FUNCTION_WRITE_RESPONSE = 6   # a reply to a write; carries no payload to check
HEADER_BYTES = 3              # address, function, length
CRC_BYTES = 2


def bytes_to_int(frame, offset, length):
    """Read `length` bytes of `frame` at `offset` as an unsigned integer.

    A positive length reads forwards, most significant byte first. A negative
    length reads the `abs(length)` bytes *ending* at `offset`, least significant
    byte first -- which is how a Modbus frame's trailing CRC is laid out.

    Returns 0 rather than raising if the frame is too short.
    """
    if len(frame) < (offset + length):
        return 0
    if length > 0:
        start, end, byteorder = offset, offset + length, "big"
    else:
        start, end, byteorder = offset + length + 1, offset + 1, "little"
    return int.from_bytes(frame[start:end], byteorder=byteorder)


def high_byte(value):
    """The most significant byte of a 16-bit value."""
    return (value >> 8) & 0xFF


def low_byte(value):
    """The least significant byte of a 16-bit value."""
    return value & 0xFF


def validate_frame(frame):
    """Is this a well-formed Modbus response with an intact CRC?

    Checks the frame is long enough, that its declared payload length matches
    what arrived, and that the trailing CRC-16/MODBUS covers the rest.
    """
    if frame is None or len(frame) < HEADER_BYTES + CRC_BYTES:
        logging.warning("Invalid frame {}".format(frame))
        return False

    if frame[1] == FUNCTION_WRITE_RESPONSE:
        return True

    declared_length = frame[2]
    if len(frame) - (HEADER_BYTES + CRC_BYTES) != int(declared_length):
        logging.warning("Invalid frame (wrong length) {}".format(frame))
        return False

    expected = libscrc.modbus(bytes(frame[:-CRC_BYTES]))
    received = bytes_to_int(frame, offset=len(frame) - 1, length=-CRC_BYTES)
    if expected == received:
        return True
    logging.warning("CRC Failed: {} - Check: {}".format(expected, received))
    return False


def ack_payload(response):
    """The acknowledgement these devices expect after a response."""
    return bytearray("main recv da ta[{0:02x}] [".format(response[0]), "ascii")
