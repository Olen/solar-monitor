import monitor_app


def test_not_complete_before_window_filled():
    # Fewer than window+1 samples: cannot yet conclude "no new devices".
    assert monitor_app.discovery_complete([1, 1, 1, 1, 1], window=5) is False


def test_not_complete_when_count_changed_within_window():
    # A device appeared 5s ago -> count differs from window ago -> keep scanning.
    assert monitor_app.discovery_complete([1, 2, 3, 4, 5, 6], window=5) is False


def test_complete_when_stable_across_full_window():
    # 6 samples, count unchanged across the last 5 seconds -> done.
    assert monitor_app.discovery_complete([3, 3, 3, 3, 3, 3], window=5) is True


def test_window_is_five_seconds_not_four():
    # This list is stable over the last 4 samples but changed 5s ago;
    # a 4-second window would wrongly stop, a correct 5-second one keeps going.
    assert monitor_app.discovery_complete([1, 2, 2, 2, 2, 2], window=5) is False
