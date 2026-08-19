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


def _capture_post(monkeypatch, status=200):
    """Record the kwargs of a successful POST."""
    calls = {}

    def fake_post(*args, **kwargs):
        calls.update(kwargs)

        class _R:
            status_code = status
        return _R()

    monkeypatch.setattr(requests, "post", fake_post)
    return calls


def test_the_auth_header_is_sent_when_a_token_is_configured(monkeypatch):
    calls = _capture_post(monkeypatch)
    dl = _make_url_only_logger()
    dl.token = "s3cret"
    dl.send_to_server("reg", "voltage", 13.2)
    assert calls["headers"]["Authorization"] == "Bearer s3cret"


def test_no_auth_header_without_a_token(monkeypatch):
    """'Bearer None' is worse than no header at all."""
    calls = _capture_post(monkeypatch)
    dl = _make_url_only_logger()
    dl.token = None
    dl.send_to_server("reg", "voltage", 13.2)
    assert "Authorization" not in calls["headers"]


def test_a_url_without_a_token_can_be_configured():
    """`config.get('datalogger', 'token')` had no fallback, so a url without a
    token raised NoOptionError at startup."""
    import configparser
    config = configparser.ConfigParser()
    config["datalogger"] = {"url": "https://ingest.example.com/api/"}
    dl = datalogger.DataLogger(config)
    assert dl.url == "https://ingest.example.com/api/"
    assert dl.token is None


def test_no_datalogger_section_at_all():
    import configparser
    dl = datalogger.DataLogger(configparser.ConfigParser())
    assert dl.url is None and dl.token is None
    assert dl.refresh_interval == 10
