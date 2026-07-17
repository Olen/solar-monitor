import types
import sys
import requests
import datalogger


def _make_url_only_logger(monkeypatch_url="http://unreachable.invalid/api"):
    """Build a DataLogger with only the HTTP sink wired, bypassing __init__
    (which needs a full config). We set just the attributes send_to_server uses."""
    dl = datalogger.DataLogger.__new__(datalogger.DataLogger)
    dl.url = monkeypatch_url
    dl.token = "t"
    dl.mqtt = None
    dl.logdata = {}
    return dl


def test_post_is_called_with_a_timeout(monkeypatch):
    calls = {}

    def fake_post(*args, **kwargs):
        calls.update(kwargs)

        class _R:
            status_code = 200
        return _R()

    monkeypatch.setattr(requests, "post", fake_post)
    dl = _make_url_only_logger()
    dl.send_to_server("reg", "voltage", 13.2)
    assert "timeout" in calls and calls["timeout"] is not None


def test_connection_error_is_swallowed_not_raised(monkeypatch):
    def boom(*args, **kwargs):
        raise requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr(requests, "post", boom)
    dl = _make_url_only_logger()
    # Must NOT raise — a network blip must never propagate to the consumer loop.
    dl.send_to_server("reg", "voltage", 13.2)
