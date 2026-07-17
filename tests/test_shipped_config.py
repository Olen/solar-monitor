import configparser
import os

DIST = os.path.join(os.path.dirname(os.path.dirname(__file__)), "solar-monitor.ini.dist")


def _read_dist():
    cp = configparser.ConfigParser()
    read = cp.read(DIST)
    assert read, "solar-monitor.ini.dist should be readable"
    return cp


def test_every_device_type_maps_to_a_real_plugin():
    cp = _read_dist()
    plugins_dir = os.path.join(os.path.dirname(DIST), "plugins")
    for section in cp.sections():
        dtype = cp.get(section, "type", fallback=None)
        if not dtype:
            continue
        assert os.path.isdir(os.path.join(plugins_dir, dtype)), (
            f"[{section}] type = {dtype} has no plugins/{dtype} directory"
        )


def test_no_active_datalogger_url_by_default():
    cp = _read_dist()
    # A fresh install must not POST to a placeholder host on first run.
    url = cp.get("datalogger", "url", fallback=None) if cp.has_section("datalogger") else None
    assert not url, f"datalogger url should be commented out by default, got {url!r}"


def test_no_credential_looking_token():
    cp = _read_dist()
    token = cp.get("datalogger", "token", fallback="") if cp.has_section("datalogger") else ""
    assert token in ("", "your-token-here"), (
        f"shipped token should be a placeholder, got {token!r}"
    )
