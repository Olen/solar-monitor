"""Shared wire-format decoding helpers.

Separate from `solardevice` so plugins can import it without a cycle:
`solardevice` imports plugins, never the reverse.
"""

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
