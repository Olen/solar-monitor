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
