"""The connection interval a peripheral renegotiates, and how it is put back."""

import ble
import hci


class _Result:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


CONNECTIONS = ("Connections:\n"
               "\t< LE 7C:01:0A:41:CA:F9 handle 64 state 1 lm CENTRAL \n"
               "\t< LE C4:F3:12:3B:C7:44 handle 65 state 1 lm CENTRAL \n")


def _runner(result=None, calls=None):
    def run(args):
        if calls is not None:
            calls.append(args)
        if args[1] == "con":
            return _Result(stdout=CONNECTIONS)
        return result if result is not None else _Result()
    return run


def test_handle_is_found_case_insensitively():
    assert hci.connection_handle("7c:01:0a:41:ca:f9", run=_runner()) == "64"
    assert hci.connection_handle("C4:F3:12:3B:C7:44", run=_runner()) == "65"


def test_unknown_mac_has_no_handle():
    assert hci.connection_handle("11:22:33:44:55:66", run=_runner()) is None


def test_milliseconds_become_hcitool_units():
    """hcitool counts in 1.25 ms units; the config is in milliseconds."""
    calls = []
    assert hci.set_connection_interval("7C:01:0A:41:CA:F9", 15, 30, run=_runner(calls=calls))
    assert calls[-1][:8] == ["hcitool", "lecup", "--handle", "64", "--min", "12", "--max", "24"]


def test_a_refused_command_is_reported():
    """Without the capability hcitool prints an error and exits 0."""
    run = _runner(result=_Result(stderr="Could not change connection params: "
                                        "Operation not permitted(1)"))
    assert not hci.set_connection_interval("7C:01:0A:41:CA:F9", 15, 30, run=run)


def test_interval_ranges_are_parsed():
    assert hci.parse_interval("15-30") == (15.0, 30.0)
    assert hci.parse_interval(" 7.5 - 15 ") == (7.5, 15.0)
    for bad in (None, "", "30", "30-15", "0-15", "fast"):
        assert hci.parse_interval(bad) is None


class _Dev:
    def __init__(self, interval=None, health=None):
        self.mac_address = "7C:01:0A:41:CA:F9"
        self.logger_name = "battery_1"
        self.connection_interval = interval
        self._health = health

    def frame_health(self):
        return self._health


def test_a_degraded_link_is_re_asserted(monkeypatch):
    asserted = []
    monkeypatch.setattr(hci, "set_connection_interval",
                        lambda mac, lo, hi, name="": asserted.append((mac, lo, hi)))
    ble._verify_link(_Dev(interval=(15, 30), health=(2, 200)))
    assert asserted == [("7C:01:0A:41:CA:F9", 15, 30)]


def test_a_healthy_link_is_left_alone(monkeypatch):
    asserted = []
    monkeypatch.setattr(hci, "set_connection_interval",
                        lambda mac, lo, hi, name="": asserted.append(mac))
    ble._verify_link(_Dev(interval=(15, 30), health=(85, 15)))
    assert asserted == []


def test_too_few_frames_to_judge(monkeypatch):
    """A quiet moment is not a bad link."""
    asserted = []
    monkeypatch.setattr(hci, "set_connection_interval",
                        lambda mac, lo, hi, name="": asserted.append(mac))
    ble._verify_link(_Dev(interval=(15, 30), health=(0, 3)))
    assert asserted == []


def test_devices_without_a_configured_interval_are_untouched(monkeypatch):
    asserted = []
    monkeypatch.setattr(hci, "set_connection_interval",
                        lambda mac, lo, hi, name="": asserted.append(mac))
    ble._verify_link(_Dev(interval=None, health=(0, 500)))
    ble._assert_connection_interval(_Dev(interval=None))
    assert asserted == []


def test_the_interval_is_asserted_on_connect(monkeypatch):
    asserted = []
    monkeypatch.setattr(hci, "set_connection_interval",
                        lambda mac, lo, hi, name="": asserted.append((mac, lo, hi)))
    ble._assert_connection_interval(_Dev(interval=(15, 30)))
    assert asserted == [("7C:01:0A:41:CA:F9", 15, 30)]
