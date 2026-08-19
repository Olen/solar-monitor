# Meritsun: connection interval governs frame integrity

A pack that connects, publishes one burst of values and then goes quiet is not a
parser problem. Check the BLE connection interval first.

## What happens

The pack streams ~13 notifications/second on `0000ffe4-…` unprompted. Shortly
after connecting it sends a connection-parameter update requesting a **195 ms
interval**, which BlueZ grants. That leaves ~5 transmit opportunities per second
for 13 notifications, so the pack's own TX buffer fills in about five seconds and
drops chunks from then on. Frames arrive truncated or merged and fail the
checksum; the parser is working correctly and has nothing to work with.

Measured on one pack, same code, same day (`dev/`):

| interval | frames | full length | pass checksum |
|---|---|---|---|
| 195 ms | 857 | 7 (1%) | 6 (1%) |
| 15 ms | 70 | 65 (93%) | 56 (80%) |

Published values follow: ~2 per minute at 195 ms, ~40 per minute at 15 ms.

The regulator (`SolarLink`) requests 18.75 ms and is unaffected. Nothing in the
plugin, in bleak or in BlueZ chooses 195 ms -- the pack asks for it.

## Diagnosing

Frame integrity, independent of this code -- `btmon` reads the HCI stream:

```
sudo btmon > /tmp/bt.txt        # ATT handle 0x0018 is 0xffe4
grep -A1 "Handle Value Notification" /tmp/bt.txt | grep "Handle:" | sort | uniq -c
```

The negotiated interval, per connection:

```
grep -A9 "LE Connection Complete\|LE Connection Update Complete" /tmp/bt.txt \
  | grep -E "Peer address:|Connection interval:"
```

`dev/frame_integrity.py` reports intact and checksum-passing frames for a
capture taken with `debug = True` in `[monitor]`.

## Fixing

Force the interval back on a live connection:

```
h=$(sudo hcitool con | awk '/7C:01:0A:41:CA:F9/ {for(i=1;i<=NF;i++) if($i=="handle") print $(i+1)}')
sudo hcitool lecup --handle "$h" --min 12 --max 24 --latency 0 --timeout 500
```

A `[ConnectionParameters]` block in
`/var/lib/bluetooth/<adapter>/<mac>/info` sets the interval the connection
*starts* at, but the pack overrides it seconds later, so it has to be
re-asserted after each connect.
