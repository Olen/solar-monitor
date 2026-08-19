#!/usr/bin/env python3
"""Report how many frames in a capture are intact and pass the checksum.

Takes a capture written by the plugin's `debug = True` hook: one notification
per line, `<timestamp> <- <hex>`.
"""
import re
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
import asciihex                                            # noqa: E402

FRAME = 121
MARKERS = (0x92, 0xC9)


def frame_end(packet):
    end = 0
    for i in range(1, min(len(packet), 122)):
        if packet[i] == 0x0C and end < 110:
            end = i + 1
    return end


def passes_checksum(packet):
    buf = [0] * 122
    for k in range(min(len(packet), 122)):
        buf[k] = packet[k]
    end = frame_end(packet)
    return end >= 60 and asciihex.checksum_matches(buf, end)


def main(path):
    notifications = [bytes.fromhex(m.group(1)) for m in
                     (re.search(r"<- ([0-9a-f]+)$", line.strip()) for line in open(path)) if m]
    stream = b"".join(notifications)
    marks = [i for i, b in enumerate(stream) if b in MARKERS]
    frames = [stream[a:b] for a, b in zip(marks, marks[1:])]
    intact = sum(1 for f in frames if len(f) == FRAME)
    good = sum(1 for f in frames if passes_checksum(f))
    print(f"{len(notifications)} notifications, {len(frames)} frames")
    print(f"  full length : {intact:>4} ({100 * intact / max(len(frames), 1):.0f}%)")
    print(f"  checksum ok : {good:>4} ({100 * good / max(len(frames), 1):.0f}%)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(f"usage: {sys.argv[0]} <capture.log>")
    main(sys.argv[1])
