import textwrap
import pytest
import monitor_app  # conftest stubs gatt/dbus/paho/gi so this imports


def _write(tmp_path, body):
    p = tmp_path / "sm.ini"
    p.write_text(textwrap.dedent(body))
    return str(p)


def test_load_config_missing_file_raises_configerror(tmp_path):
    missing = str(tmp_path / "nope.ini")
    with pytest.raises(monitor_app.ConfigError):
        monitor_app.load_config(missing)


def test_load_config_without_monitor_section_raises(tmp_path):
    ini = _write(tmp_path, """
        [mqtt]
        broker = localhost
    """)
    with pytest.raises(monitor_app.ConfigError):
        monitor_app.load_config(ini)


def test_load_config_valid_returns_config(tmp_path):
    ini = _write(tmp_path, """
        [monitor]
        adapter = hci0
    """)
    cfg = monitor_app.load_config(ini)
    assert cfg.get("monitor", "adapter") == "hci0"


def test_load_config_applies_overrides(tmp_path):
    ini = _write(tmp_path, """
        [monitor]
        adapter = hci0
        debug = False
    """)
    cfg = monitor_app.load_config(ini, adapter="hci1", debug=True)
    assert cfg.get("monitor", "adapter") == "hci1"
    assert cfg.getboolean("monitor", "debug") is True
