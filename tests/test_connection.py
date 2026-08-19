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


# --- write_with_retry ------------------------------------------------------

import asyncio

from connection import write_with_retry


class _WriteClient:
    """Fails the first `fail_times` writes, then succeeds."""

    def __init__(self, fail_times=0):
        self.fail_times = fail_times
        self.attempts = 0
        self.written = []
        self.concurrent = 0
        self.max_concurrent = 0

    async def write_gatt_char(self, char, value):
        self.attempts += 1
        self.concurrent += 1
        self.max_concurrent = max(self.max_concurrent, self.concurrent)
        await asyncio.sleep(0)
        self.concurrent -= 1
        if self.attempts <= self.fail_times:
            raise RuntimeError("transient")
        self.written.append((char, bytes(value)))


async def _no_sleep(_):
    return None


def test_a_command_write_that_succeeds_is_not_repeated():
    client = _WriteClient()
    ok = asyncio.run(write_with_retry(client, "c", b"\x01", sleep=_no_sleep))
    assert ok is True
    assert client.attempts == 1


def test_a_command_write_is_retried_once():
    """A user action is not repeated by anything else, so it gets one more go."""
    client = _WriteClient(fail_times=1)
    ok = asyncio.run(write_with_retry(client, "c", b"\x01", sleep=_no_sleep))
    assert ok is True
    assert client.attempts == 2
    assert client.written == [("c", b"\x01")]


def test_it_gives_up_after_the_retry_without_raising():
    client = _WriteClient(fail_times=5)
    ok = asyncio.run(write_with_retry(client, "c", b"\x01", sleep=_no_sleep))
    assert ok is False
    assert client.attempts == 2
    assert client.written == []


def test_the_lock_is_held_for_every_attempt():
    client = _WriteClient(fail_times=1)
    lock = asyncio.Lock()

    async def run():
        await asyncio.gather(
            write_with_retry(client, "c", b"\x01", lock=lock, sleep=_no_sleep),
            write_with_retry(client, "c", b"\x02", lock=lock, sleep=_no_sleep),
        )

    asyncio.run(run())
    assert client.max_concurrent == 1


def test_polls_do_not_retry():
    """ble._hold writes once and drops the payload -- the next poll re-asks."""
    import ble

    class _Dev:
        logger_name = "d"
        need_polling = True
        device_write_characteristic_polling = "poll"

        def get_poll_data(self):
            return [1]

    client = _WriteClient(fail_times=1)
    client.is_connected = True

    async def run():
        await ble._hold(_Dev(), client, asyncio.Event(), 0.001, asyncio.sleep)

    asyncio.run(run())
    assert client.attempts == 1          # not retried
    assert client.written == []
