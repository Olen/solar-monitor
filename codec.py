"""Shared wire-format decoding helpers.

Separate from `solardevice` so plugins can import it without a cycle:
`solardevice` imports plugins, never the reverse.
"""

import logging

# Two's-complement wrap points. A reading above the signed maximum is negative
# and wraps by 2**bits. Every plugin open-coded this with its own constant and
# each was short of 2**bits: Meritsun and Topband by one LSB (2**32 - 1),
# RenogyBatt by two (65534, not 65536, for both current and temperature). So
# every negative reading came out high -- by +0.02 A on RenogyBatt current,
# which integrates into roughly 1.7 Ah/day of phantom charge.
UINT16_WRAP = 1 << 16      # 65536
UINT32_WRAP = 1 << 32      # 4294967296
INT16_MAX = (1 << 15) - 1  # 32767
INT32_MAX = (1 << 31) - 1  # 2147483647


def to_signed(value, wrap, threshold):
    """Interpret a two's-complement reading as signed.

    `wrap` and `threshold` are in the same units as `value`, so a caller that
    has already scaled the raw word passes scaled bounds (see RenogyBatt).
    `threshold` is separate from `wrap // 2 - 1` because some devices use a
    practical bound rather than the arithmetic sign bit.
    """
    return value - wrap if value > threshold else value


def ascii_hex_value(buf, start, end, default=0):
    """Read an ASCII-hex field from `buf[start:end]` inclusive, low pair first.

    The wire format writes each byte as two ASCII hex characters, least
    significant pair first, so "0123" is 0x2301.

    Truncated frames are the normal failure here, not an exceptional one: a
    notification can be short or the framing can slip. Return `default` and say
    so at debug rather than raising into the BLE callback (where it costs the
    whole notification) or swallowing every exception silently (where it hides
    real bugs).
    """
    if start < 0 or end < start or end >= len(buf):
        logging.debug("field [%d:%d] outside a frame of %d bytes", start, end, len(buf))
        return default
    chars = [chr(c) for c in buf[start:end + 1]]
    pairs = ["".join(pair) for pair in zip(chars[0::2], chars[1::2])]
    try:
        return int("".join(reversed(pairs)), 16)
    except ValueError:
        logging.debug("field [%d:%d] is not ASCII-hex: %r", start, end, "".join(chars))
        return default
