def test_gatt_stub_lets_solardevice_import():
    import solardevice
    assert hasattr(solardevice, "SolarDevice")
    assert hasattr(solardevice, "SolarDeviceManager")
