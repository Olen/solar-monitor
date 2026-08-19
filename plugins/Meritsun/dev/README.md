# Captures

Both from pack `12V100Ah-027` (`7C:01:0A:41:CA:F9`) on 2026-08-19, one line per
notification as written by the plugin's `debug = True` hook. See
[../NOTES.md](../NOTES.md).

| file | connection interval |
|---|---|
| `capture-slow-interval-195ms.log` | 195 ms, as the pack requests it |
| `capture-fast-interval-15ms.log` | 15 ms, forced with `hcitool lecup` |

`frame_integrity.py <capture>` reports intact and checksum-passing frames.
