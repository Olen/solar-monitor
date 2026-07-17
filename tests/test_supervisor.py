import queue
import supervisor


def test_try_put_returns_true_when_space():
    q = queue.Queue(maxsize=2)
    assert supervisor.try_put(q, ("a", "b", 1)) is True
    assert q.qsize() == 1


def test_try_put_returns_false_when_full_and_does_not_block():
    q = queue.Queue(maxsize=1)
    assert supervisor.try_put(q, ("a", "b", 1)) is True
    # Second put would block a blocking put() forever; try_put must return False.
    assert supervisor.try_put(q, ("c", "d", 2)) is False
    assert q.qsize() == 1
