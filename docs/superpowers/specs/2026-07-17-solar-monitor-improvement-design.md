# solar-monitor — Stabilization & Testability Design

**Date:** 2026-07-17
**Status:** Approved (design), pending implementation plan
**Author:** Ola Thoresen (with Claude Code review)
**Scope decision:** Stabilize, then make it testable. Keep the current architecture and the `gatt` library this round. Migration to `bleak` is explicitly deferred (see §8).

---

## 1. Context

`solar-monitor` is a Python 3 daemon that connects to Bluetooth LE solar charge
controllers, batteries and inverters, polls them, and publishes readings to MQTT
(Home Assistant auto-discovery) and/or an HTTP endpoint. It runs as root under
systemd (`Type=simple`, `Restart=always`, `RestartSec=13`) on Raspberry Pi
hardware — often a single-core Pi Zero, frequently off-grid, sometimes months
between physical access.

The codebase dates to 2020, went threaded in Jan 2025, and has never had tests or
CI. A five-way parallel code review on 2026-07-17 (against `master` at `d63b9cc`,
after PRs #41 and #42 merged) produced ~76 findings. This document turns those
findings into a sequenced, reviewable improvement plan.

The review reports themselves live alongside this doc as the evidentiary record;
this spec is the actionable synthesis.

## 2. The central finding

The review's five reviewers had isolated context and non-overlapping scopes. They
could not see each other's work. **All five independently converged on the same
terminal failure state:**

> A fault occurs → a thread dies or blocks → the process stays *alive* →
> `Restart=always` never fires → the daemon is silently dead for months.

This is the worst possible failure shape for the deployment target. The
supervision layer systemd provides is defeated precisely *because* the failures do
not exit the process. Every high-severity finding is a different entrance to this
one room.

The canonical chain (proven end-to-end across three reviewers):

```
HTTP endpoint blips
  → requests.post (no timeout) raises ConnectionError
  → `except TimeoutError` misses it (ConnectionError subclasses OSError, not TimeoutError)
  → exception escapes DataLogger.log()
  → threaded_logger's `except Exception` → sys.exit(299)
  → SystemExit swallowed by the never-inspected ThreadPoolExecutor Future
  → consumer thread dead
  → 10,000-slot queue fills
  → solardevice.py queue.put() blocks FOREVER inside the dbus callback thread
  → device_manager.run() stops dispatching → every device silent
  → process still alive → systemd never restarts
```

Four distinct triggers reach this chain: broker restart, HTTP blip, an MQTT prefix
containing a `/`, or a `/set` message arriving before its trigger is registered.

## 3. Constraints that shape the plan

### 3.1 No live hardware (during this work)

Decoder correctness cannot be validated against real devices. This splits every
plugin/decoder change into two tiers:

- **Tier 1 — Provable.** Correct regardless of wire format: arithmetic errors
  (two's-complement divisors), crashes on truncated frames, the `_mvoltage`
  double-assignment, the `validate()` latch. These ship, covered by golden tests
  built from crafted frames and the `plugins/Hacien/dev/` capture corpus.
- **Tier 2 — Format-dependent.** Anything needing a real device to confirm
  (VEDirect signed-current handling, the `65533–65535` sentinels). These are
  **documented, not changed** — or gated behind a flag defaulting to today's
  behavior. We do not replace confirmed-correct behavior with a guess.

### 3.2 Deployed users exist

Ordering principle: **stop active harm before improving structure.** Bug fixes on
the current architecture land first; structural change follows.

## 4. Branch reconciliation

Three unmerged remote branches intersect the findings and are folded into the plan
rather than treated as separate work:

| Branch | State | Disposition |
|---|---|---|
| `charge-power` | 2 ahead, clean WIP (SolarLink `charge_power = V×I`; `entities.charge_power` confirmed to exist at `solardevice.py:696`/publish list `:232`) | **Merge early**, before the Phase 3 plugin refactor rebases SolarLink under the shared base. |
| `refresh-interval` | 2 ahead, **buggy** | Makes the refresh interval configurable (addresses a finding), but writes `self.refresh_inteval` (typo) and reads `self.refresh_interval` → `AttributeError`; also `config.get()` returns a str → `timedelta(minutes='10')` → `TypeError`. Either kills the consumer → the §2 deadlock. **Fix (typo + `getint`), then merge in the datalogger phase — only after Phase 1 makes the consumer unkillable.** |
| `NewBattery` | 1 ahead, 22 behind, stale | Encodes the intent of finding #10 (drop `refresh=True` to stop MQTT sensor-recreation churn). **Salvage the intent in Phase 3; delete the branch.** |
| `mqtt-fix-hostname` | 0 ahead | Already subsumed by master. Delete. |

`refresh-interval` is itself proof of the central thesis: a well-intentioned
feature branch reintroduces the deadlock because the consumer thread is still
killable. Phase 1 is the guardrail that makes all future feature work — including
the maintainer's own — safe.

## 5. Phased plan

Each phase is one or more independently-reviewable PRs, ordered highest
safety-per-line first.

### Phase 0 — Ship-blocker hotfix (two one-liners)

Fresh installs following the README verbatim are broken today. Land as a tiny,
cherry-pickable PR.

- **`solar-monitor.ini.dist`: `type = VictronConnect` → `VEDirect`.** `VictronConnect`
  is a plugin that has never existed in the tree or any commit; introduced by the
  very commit meant to sync the ini (`7361955`). Victron support the README
  advertises does not work from the shipped config. *(CONFIRMED)*
- **`solar-monitor.ini.dist`: comment out the active `[datalogger]` block** pointed
  at placeholder host `http://server/solar/api/`. A default install triggers the
  §2 hang on first run. *(CONFIRMED)*

### Phase 1 — Supervision & liveness (the keystone)

Design rule: **no gatt/dbus callback may ever block, and the process must exit
when it cannot work.**

- `threaded_logger` never dies on a per-item exception — catch *inside* the loop,
  log, continue. Remove `sys.exit(299)`. *(addresses the §2 chain)*
- Every `queue.put()` → `put_nowait()` with drop-and-count on `queue.Full`. A
  stalled consumer can never freeze the dbus thread. `solardevice.py:238,245,246,255,263,716`
- `connect_failed`/`disconnect_succeeded`: replace `time.sleep(10) + self.connect()`
  with `GLib.timeout_add_seconds(...)`. Fixes the shared-main-loop stall **and**
  makes reconnect iterative — kills the ~55-minute `RecursionError` (CONFIRMED:
  RecursionError after 66 cycles at reduced limit). `solardevice.py:138-142,156-160`
- Supervisory main thread with a **liveness watchdog**: if no device has produced a
  reading in N minutes, or the logger future is dead, log the reason and
  `sys.exit(1)`. Wire `Type=notify` + `WatchdogSec` with an `sd_notify` ping so
  systemd finally sees a hung daemon. `solar-monitor.py:129-161`
- Signal handling (SIGTERM/SIGINT) → set a stop `Event`, `device_manager.stop()`,
  `executor.shutdown()`. Fixes the hang-at-shutdown (CONFIRMED: exit code 124).
- `requests.post`: add `timeout=(connect, read)`; catch
  `requests.exceptions.RequestException`, not `TimeoutError`. `datalogger.py:257-259`
- Zero-devices-discovered becomes a non-zero exit, not an infinite idle.
  `solar-monitor.py:139-155`

### Phase 2 — Testability foundation (the pivot)

Nothing is testable today because importing `solar-monitor.py` runs a 15-second BLE
scan and calls `sys.exit()` in module scope.

- Extract `main()` behind `if __name__ == "__main__":`; make discovery and config
  loading injectable functions. `solar-monitor.py:21-127`
- First tests target exactly what rotted silently since 2020:
  - config validation — `config.read()` returns `[]` on a missing file, so the
    existing `try/except` + `sys.exit(1)` is dead code for its own case (CONFIRMED);
    validate `[monitor]` exists; check `config.read()` return value.
  - the discovery termination off-by-one (`found[len(found)-5]` = 4s window, not 5;
    CONFIRMED it can miss a late-appearing device).
  - golden-frame decoder tests from `plugins/Hacien/dev/` captures.
- Add GitHub Actions CI: lint + the new test suite. First CI the repo has ever had.

### Phase 3 — Plugin & value-layer consolidation

The six plugins are three copy-paste pairs plus VEDirect; `solardevice.py` is a BLE
transport layer stapled to a ~670-line value hierarchy of ~40 near-identical
getter/setter pairs. Duplication is *why* the same decode bug exists four times
with four different wrong constants.

- Introduce `ModbusPlugin` base (owns `Bytes2Int`/`Int2Bytes`/`Validate`/
  `create_poll_request`) and `AsciiHexFramer` base (owns the byte-scanner state
  machine, parameterized by head/end/frame-len). Subclasses declare only a register
  table. Collapses ~400 of 1765 plugin lines.
- **One** signed-integer decoder replaces four hand-rolled magic-constant
  subtractions. This single change fixes the Tier-1 "silently wrong data" family:
  - RenogyBatt current: `655.34` → correct signed decode (`655.36`); the +0.02 A
    bias is integrated by `updateCapacityFromCurrent` into ~1.7 Ah/day phantom
    charge. *(CONFIRMED)*
  - RenogyBatt temperature: `6553.4` → `6553.6`. *(CONFIRMED)*
  - Meritsun/Topband current: `4294967295` → `4294967296`. *(CONFIRMED)*
- **One** bounds-checked frame accessor replaces the inconsistent truncated-frame
  handling (Meritsun silently coerces to 0; Topband/Hacien raise IndexError into the
  BLE callback on identical input). *(CONFIRMED via crafted CRC-valid short frames)*
- `validate()` (`solardevice.py:756`): change from a **latch** to a **rate limit** —
  track consecutive rejects, accept after N agreeing samples. Today one missed
  notification wedges `_charge_cycles` (maxdiff=1, monotonic) permanently. *(CONFIRMED)*
- `_mvoltage` double-assignment (`solardevice.py:395/437`): delete the dead first
  assignment; move the 15 V limit to the 12 V subclass so 24 V/48 V regulators stop
  having every voltage reading silently rejected. *(CONFIRMED)*
- `cmdRequest`: give the base a default returning `[]` — 4 of 6 plugins lack it and
  the unguarded call at `solardevice.py:334` kills the poller thread on any MQTT
  `set`. *(CONFIRMED)*
- Give each poller thread a private stop `Event` captured at creation; set flags from
  `services_resolved`, not from inside the thread; `join()` the previous thread
  before starting a new one. Fixes the thread-revival write-storm. *(CONFIRMED)*
- Add a `threading.Lock` around writes; pass the failed payload through the callback
  rather than shared `self.writing`. *(CONFIRMED, currently masked by the dead retry
  path — `if error == "In Progress"` compares an exception instance to a str, always
  False, `solardevice.py:289`.)*
- Fold in `NewBattery`'s churn-fix intent (gate discovery-config republish behind a
  much longer interval than the state refresh; `datalogger.py:53,64` — `self.sensors`
  list → `set`, measured 1000 entries for 1 unique topic).
- Fold in `refresh-interval` (typo + `getint`) once Phase 1 lands.
- Commit `logdata` only *after* a successful send, and check publish return codes —
  today a state change during a broker outage is lost permanently, not delayed.
  `datalogger.py:67,233-237`
- `config.getint('mqtt','port', ...)` — a string port raises TypeError → crash loop
  for anyone using a non-1883/TLS port. `datalogger.py:201`
- MQTT robustness: `on_connect` re-subscribe; wrap `on_message` body in
  try/except; `topic.rsplit("/", 2)`; `.get()` for trigger/sets lookups.

### Phase 4 — Ops, packaging, security

- `solar-monitor.service`: stop running root over user-writable code — move the
  checkout to a root-owned path (`/opt/solar-monitor`), keep only config/logs
  writable. Run as a dedicated user in the `bluetooth` group (gatt reaches BlueZ
  purely over the D-Bus system bus — CONFIRMED — so capabilities are the wrong tool;
  D-Bus policy is the gate). Add `After=bluetooth.service`, `NoNewPrivileges`,
  `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp`. *(the `Adapter1.Powered`
  write is the one operation to verify works non-root on real Raspbian.)*
- Add `.dockerignore` (`.git`, `*.ini`, `__pycache__`, `plugins/*/dev`); `COPY
  requirements.txt` before `COPY . .`. Today `COPY . .` can bake a real ini's
  secrets into an image layer. Multi-stage build to drop the compiler toolchain and
  the hours-long Pi Zero rebuild.
- Move `plugins/Hacien/dev/` (9.2 MB pcapng + 5.9 MB JSON) out of the shipped
  package; retain as a test corpus reference outside the tree.
- Pin the full dependency set (currently one pin, `PyGObject==3.50.0`, undocumented
  and load-bearing — document why). Publish a pre-built multi-arch image from CI.
- Base image bullseye → bookworm (verify the `PyGObject` pin against the base
  image's girepository version).
- Docs: document `username`/`password`/`port` in the `.dist`; instruct `chmod 600`;
  make the datalogger example `https://`; replace the MD5-looking dummy token with
  `your-token-here`; state the GPLv3 license in the README; link `PLUGINS.md`.

## 6. Testing strategy

- **Golden-frame tests** from `plugins/Hacien/dev/` captures + crafted frames
  (truncated, CRC-valid-but-short, boundary values) — no hardware required, and
  exactly the input class that produced the crash findings.
- **Config/discovery unit tests** enabled by the Phase 2 `main()` extraction.
- **Tier 2 findings** get regression tests pinning *current* behavior, with a
  `# TODO: verify against hardware` marker, so a future maintainer with a device
  knows precisely what to check.
- CI runs lint + tests on every push and PR.

## 7. Success criteria

1. No single-point failure (broker down, HTTP down, device out of range, malformed
   frame) leaves the process alive-but-idle; each either self-heals or exits non-zero
   for systemd to restart.
2. A fresh install from the shipped `.dist` + README produces working data flow on
   first run.
3. Tier-1 decoder bugs fixed once, in shared code, under golden tests.
4. The repo has CI, and `solar-monitor.py` is importable without a Bluetooth adapter.
5. The daemon no longer runs root over user-writable code.

## 8. Out of scope (documented follow-up)

**Migration off `gatt` to `bleak`.** `gatt` last shipped 2017-11-21 (~9 years), has
no upstream, and already emits `PyGIDeprecationWarning` for `GObject.MainLoop` on
the pinned PyGObject; when that shim is removed the app dies with no upstream fix.
This is the correct long-term direction and the real root cause of the packaging
pain (the hand-listed `dbus-python`/`PyGObject`/`pycairo` toolchain). It is deferred
because it is a rewrite of the BLE core that **requires hardware to validate**, which
is unavailable this cycle. Track as a standalone future spec.

## 9. Findings not otherwise scheduled

Lower-severity confirmed items to sweep opportunistically within their phase's files:
`ackData` signature mismatch (2 variants); `SolarLink` hardcoded device id 255;
`Validate()` returning True before CRC on function 6; RenogyBatt `TotalCapacity`
dead branch and missing `updateParamSettingData`; RenogyBatt SoC fraction-vs-percent
comparison (13.2 V branch always returns 50); Hacien De Morgan cell-skip error;
VEDirect `int(str(value[4]),16)` decimal/hex confusion; dead scaffolding
(`run_connect`/`connect_thread`, `RegulatorDevice.parse_notification`); duallog
absolute-path log bug and handler non-idempotence (retired if migrated to the shared
`olen` logger per the org convention); bare `except:` clauses swallowing
`KeyboardInterrupt`/`SystemExit`.
