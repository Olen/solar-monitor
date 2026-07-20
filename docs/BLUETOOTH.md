# Bluetooth / BLE notes for solar-monitor

This monitor talks to several BLE devices (solar regulator, batteries, inverter)
at once. Keeping multiple simultaneous BLE connections alive is the hardest part
of running it on a Raspberry Pi. This file documents the failure modes we hit and
every change made to the host, so the setup is reproducible.

## The big one: 2.4 GHz WiFi ↔ Bluetooth coexistence

**Symptom:** several devices fail to connect with
`org.bluez.Error.Failed le-connection-abort-by-local`, often the *same* devices
every time, while one or two others connect fine. It can look device-specific or
like a "too many connections" limit, but it is neither.

**Root cause:** the Raspberry Pi's built-in wireless is a **combo chip** (BCM4345
family) that shares one radio/antenna between WiFi and Bluetooth. If the Pi also
runs a **2.4 GHz WiFi access point**, the constant AP traffic starves Bluetooth,
and BLE *connection establishment* fails with `le-connection-abort-by-local`. The
weaker/slower-advertising devices lose the airtime fight and never connect;
stronger ones sometimes get through, which is what makes it look device-specific.

This is not a hardware limit on the number of links — the same Pi happily held
five concurrent BLE connections for years. A move to a newer OS (BlueZ 5.82 /
kernel 6.18 on Raspberry Pi OS trixie) tightened the WiFi/BT coexistence
arbitration and tipped a marginal 2.4 GHz-AP setup over the edge.

**Diagnosis:**

```bash
# Is the AP on 2.4 GHz? hw_mode=g and a channel of 1-13 means yes.
sudo grep -iE 'hw_mode|channel' /etc/hostapd/hostapd.conf

# Proof: stop the 2.4 GHz AP and the "dead" BLE devices connect immediately.
sudo systemctl stop hostapd      # BLE devices connect, 0 aborts
sudo systemctl start hostapd     # back to failing
```

**Fix: get the WiFi AP off 2.4 GHz so Bluetooth has that band to itself.**
Move the access point to 5 GHz (all clients must support 5 GHz), or run the AP on
a separate radio (USB WiFi dongle), or move Bluetooth to a USB BT dongle.

The 5 GHz `hostapd.conf` change made on leveld (from `hw_mode=g` channel 1):

```ini
country_code=NO      # required for 5 GHz
ieee80211d=1
hw_mode=a            # 5 GHz
channel=36           # non-DFS (36/40/44/48) — starts instantly, no radar wait,
                     # so it comes up reliably on an unattended reboot
```

Use a **non-DFS** channel (36-48). DFS channels (52-144) require a radar
availability check that delays or blocks AP startup — bad for an unattended host.
Back up the working config first (`hostapd.conf.bak24`), and when changing an AP
you can only reach over a separate link (e.g. 4G/VPN), keep a watchdog that
reverts after a few minutes unless you confirm success.

## The app-side fix: serialize connection *establishment*

Independently of coexistence, there is a real BlueZ/controller constraint: only
**one** LE "Create Connection" can be in flight at a time. If two threads call
`connect()` simultaneously, the controller cancels one and **both** fail with
`le-connection-abort-by-local`. The monitor serializes establishment with a
single lock (`connect_lock` in `monitor_app.main()`): only one device is ever in
its connect→resolve window at a time, held just for that window, then released —
while already-resolved links stay held. Several devices can be *connected* at
once; only the act of *connecting* is serialized.

## Connection model (persistent vs rotating)

- **Persistent (recommended for all devices):** each device is held connected
  continuously (`persistent = True` in its ini section). A healthy adapter holds
  them all. Required for **pure-notify** devices (e.g. Meritsun batteries) that
  never answer polls — they only push notifications, so they must stay connected
  to deliver any data at all.
- **Rotating (fallback):** if a controller genuinely cannot hold that many links,
  leave devices non-persistent and they share one slot — connect, read for
  `rotate_dwell` seconds, disconnect, next (`rotate_gap` between). Poor fit for
  pure-notify devices, which may not push data within a short dwell.

## Optional host connection-parameter tuning

`/etc/bluetooth/main.conf` `[LE]` — raising the supervision timeout reduces
spurious BLE timeouts (reportedly 42→200 helps). Loaded into the kernel defaults
at adapter power-on; verify with
`sudo cat /sys/kernel/debug/bluetooth/hci0/supervision_timeout`. debugfs values
are **not** persistent across reboots — `main.conf` is the durable source. This
tuning is secondary; it does **not** fix the coexistence problem above.

## Operational gotchas

- **A dead device just won't advertise.** A battery whose BMS has shut down (deep
  discharge, or after being physically disconnected) stops advertising, so it is
  never discovered and never connects — 0 discovery events in the log, no RSSI in
  `bluetoothctl info`. That is a hardware problem, not a BLE bug. Confirm with a
  scan: `sudo timeout 8 bluetoothctl scan on` — if the MAC never appears, the
  device is silent. (Some BMSes need a load-disconnect for ~10 min to restart
  advertising; a fully depleted battery needs recovery/replacement.)

- **Don't hammer the adapter.** Rapid connect/disconnect cycles, resets, or
  repeated `bluetoothctl connect` one-shots can push the controller into a wedged
  state where nothing connects (every attempt aborts) — and `bluetoothctl connect`
  is not a faithful test anyway (it doesn't hold the GATT session like the app).
  Resets don't clear the wedge; leaving the adapter undisturbed does.

- **A bluetoothd restart orphans the running monitor.** The BLE library caches
  D-Bus proxies bound to bluetoothd's unique name. If `bluetooth.service` restarts
  while the monitor keeps running, every call fails with
  `org.freedesktop.DBus.Error.ServiceUnknown: The name :1.x was not provided ...`.
  Fix: restart the monitor so it re-binds. Diagnose by comparing
  `docker inspect -f '{{.State.StartedAt}}' solar-monitor` with
  `systemctl show bluetooth -p ActiveEnterTimestamp --value` — if bluetoothd is
  newer, the monitor is orphaned.

- **rfkill on boot:** `systemd-rfkill` persists rfkill state, so an adapter blocked
  once comes back blocked every boot. Clear the saved blocked state if BT is
  unexpectedly soft-blocked after a reboot.
