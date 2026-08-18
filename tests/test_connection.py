import connection

NO_JITTER = lambda a, b: 0.0   # deterministic rand for exact-value assertions


def test_backoff_grows_then_caps():
    b = lambda n: connection.backoff_seconds(n, base=5, maximum=300, rand=NO_JITTER)
    assert b(1) == 5
    assert b(2) == 10
    assert b(3) == 20
    assert b(4) == 40
    assert b(100) == 300   # capped


def test_backoff_clamped_not_a_bigint():
    assert connection.backoff_seconds(10_000, base=5, maximum=300, rand=NO_JITTER) == 300


def test_backoff_attempt_floor():
    assert connection.backoff_seconds(0, base=5, maximum=300, rand=NO_JITTER) == 5


def test_backoff_applies_jitter_to_spread_retries():
    # With jitter, the delay is offset by rand(-jitter, jitter). A rand that
    # returns its upper bound gives delay + jitter; never negative.
    hi = connection.backoff_seconds(1, base=10, jitter=5, rand=lambda a, b: b)
    lo = connection.backoff_seconds(1, base=10, jitter=5, rand=lambda a, b: a)
    assert hi == 15 and lo == 5                         # first retry spread over 5..15
    # jitter never drives the delay below zero
    assert connection.backoff_seconds(1, base=1, jitter=100, rand=lambda a, b: a) == 0.0
