"""ASCII-hex framing, shared by the plugins that speak it.

Every byte is two ASCII hex characters, least significant pair first, and a
frame is protected by a 16-bit additive checksum. Frame layouts and packet types
differ per device and belong in the plugin.
"""

import logging


def field_value(frame, start, end, default=0):
    """Read the ASCII-hex field `frame[start:end]` inclusive, low pair first.

    Each byte is written as two ASCII hex characters and the pairs run least
    significant first, so "0123" is 0x2301.

    A truncated frame is normal on a BLE stream, not exceptional: return
    `default` and say so at debug rather than raising into the notification
    callback, or swallowing every error and publishing a fabricated value.
    """
    if start < 0 or end < start or end >= len(frame):
        logging.debug("field [%d:%d] outside a frame of %d bytes", start, end, len(frame))
        return default
    characters = [chr(byte) for byte in frame[start:end + 1]]
    pairs = ["".join(pair) for pair in zip(characters[0::2], characters[1::2])]
    try:
        return int("".join(reversed(pairs)), 16)
    except ValueError:
        logging.debug("field [%d:%d] is not ASCII-hex: %r", start, end, "".join(characters))
        return default


def checksum_matches(frame, content_end):
    """Does the frame's trailing checksum match the sum of its byte fields?

    Every two-character field from index 1 is summed; the running total is
    compared against the 16-bit value held in the two fields at the end of the
    content. `content_end` is where the frame's content stops -- the checksum
    itself occupies `content_end - 5` onwards.
    """
    total = 0
    position = 1
    while position < content_end - 5:
        total += field_value(frame, position, position + 1)
        position += 2
    stated = (field_value(frame, position, position + 1) << 8) + \
        field_value(frame, position + 2, position + 3)
    return total == stated
