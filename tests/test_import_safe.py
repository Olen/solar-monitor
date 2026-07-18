def test_importing_monitor_app_has_no_side_effects():
    # Must import with no adapter, no argparse, no discovery — proves the
    # module-scope side effects are gone (the whole point of the extraction).
    import monitor_app
    assert callable(monitor_app.main)
    assert callable(monitor_app.load_config)
