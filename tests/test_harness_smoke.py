def test_solardevice_imports_cleanly():
    # solardevice.py is transport-free (no gatt/dbus import) since the bleak
    # migration; SolarDeviceManager was removed with it (see
    # docs/superpowers/plans/2026-07-20-bleak-migration.md Task 2).
    import solardevice
    assert hasattr(solardevice, "SolarDevice")
    assert not hasattr(solardevice, "SolarDeviceManager")
