"""Set the connection interval of an established BLE link.

BlueZ grants a peripheral's connection-parameter update request whenever it is
within the spec's absolute bounds -- the kernel's `hci_check_conn_params()` never
consults the adapter's configured limits -- so a device that asks for a slow
interval gets one. The Meritsun packs ask for 195 ms and then lose most of every
frame, because they push ~13 notifications/second into ~5 transmit opportunities.

Neither BlueZ's D-Bus API nor bleak exposes connection parameters, so this goes
through `hcitool`. That needs CAP_NET_RAW/CAP_NET_ADMIN, granted to the binary
alone through file capabilities so the daemon keeps running unprivileged; see
the Dockerfile and `cap_add` in docker-compose.yaml.
"""
import logging
import re
import subprocess

HCITOOL = "hcitool"
UNITS_PER_MS = 0.8            # hcitool counts in 1.25 ms units


def _run(args):
    return subprocess.run(args, capture_output=True, text=True, timeout=10)


def connection_handle(mac, run=_run):
    """The controller's handle for an established link, or None."""
    try:
        result = run([HCITOOL, "con"])
    except Exception as error:
        logging.debug("hcitool con failed: %r", error)
        return None
    pattern = re.compile(re.escape(mac.upper()) + r".*?handle (\d+)", re.IGNORECASE)
    match = pattern.search(result.stdout or "")
    return match.group(1) if match else None


def set_connection_interval(mac, min_ms, max_ms, name="", run=_run):
    """Ask the controller for a new interval on an established link.

    Returns True when the command was accepted. The peripheral may renegotiate
    afterwards, which is why callers re-assert on reconnect. `name` is the
    device's logger name: log lines identify devices by name, never by address.
    """
    handle = connection_handle(mac, run=run)
    if handle is None:
        logging.debug("[%s] no connection handle; cannot set the interval", name)
        return False
    args = [HCITOOL, "lecup", "--handle", handle,
            "--min", str(round(min_ms * UNITS_PER_MS)),
            "--max", str(round(max_ms * UNITS_PER_MS)),
            "--latency", "0", "--timeout", "500"]
    try:
        result = run(args)
    except Exception as error:
        logging.warning("[%s] setting the connection interval failed: %r", name, error)
        return False
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0 or "Operation not permitted" in output or "Could not" in output:
        logging.warning("[%s] could not set the connection interval: %s",
                        name, output.strip() or f"exit {result.returncode}")
        return False
    logging.info("[%s] connection interval set to %g-%g ms", name, min_ms, max_ms)
    return True


def parse_interval(value):
    """Parse a `min-max` millisecond range from config, or None."""
    if not value:
        return None
    match = re.fullmatch(r"\s*([\d.]+)\s*-\s*([\d.]+)\s*", value)
    if not match:
        logging.warning("connection_interval %r is not a 'min-max' range in ms", value)
        return None
    low, high = float(match.group(1)), float(match.group(2))
    if low <= 0 or high < low:
        logging.warning("connection_interval %r is not a usable range", value)
        return None
    return low, high
