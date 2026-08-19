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


def test_every_shipped_option_is_read_by_the_code():
    """An option in the .dist that nothing reads is a promise the code breaks.

    `persistent` was documented and offered for a year after the rotating
    connection model it selected had been deleted, and `reconnect` was shipped
    in seven places while no code ever read it (#76).
    """
    import glob
    import re

    root = os.path.dirname(DIST)
    sources = "\n".join(
        open(f, encoding="utf-8").read()
        for f in glob.glob(os.path.join(root, "*.py"))
        + glob.glob(os.path.join(root, "plugins", "*", "__init__.py"))
    )

    cp = _read_dist()
    unread = []
    for section in cp.sections():
        for option in cp.options(section):
            if not re.search(rf"""['"]{re.escape(option)}['"]""", sources):
                unread.append(f"[{section}] {option}")
    assert not unread, (
        "shipped in solar-monitor.ini.dist but read by no code: " + ", ".join(unread))


def test_every_option_the_code_reads_is_documented():
    """The converse of the test above: an option the code honours but the .dist
    never mentions is invisible to anyone configuring the tool.

    `username`, `password`, `port` and `hostname` were read by the MQTT logger
    and appeared nowhere in the shipped example (#47).
    """
    import glob
    import re

    root = os.path.dirname(DIST)
    sources = "\n".join(
        open(f, encoding="utf-8").read()
        for f in glob.glob(os.path.join(root, "*.py"))
    )
    # config.get('mqtt', 'port', ...) / config.getboolean(section, 'trusted', ...)
    read = set(re.findall(
        r"""config\.get(?:int|boolean|float)?\(\s*(?:section|['"][a-z]+['"])\s*,\s*['"]([a-z_]+)['"]""",
        sources))

    documented = set(re.findall(r"^#?\s*([a-z_]+)\s*=", open(DIST).read(), re.M))
    missing = sorted(read - documented)
    assert not missing, (
        "read by the code but absent from solar-monitor.ini.dist: " + ", ".join(missing))
