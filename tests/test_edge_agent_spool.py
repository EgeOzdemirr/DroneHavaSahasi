from pathlib import Path
from unittest.mock import patch

from edge_agent.spool import SQLiteSpool


def test_spool_enqueue_and_counts(tmp_path: Path):
    spool = SQLiteSpool(str(tmp_path / "spool.db"), queue_max=2)
    ok1 = spool.enqueue(headers={"X-Drone-Uid": "D1"}, raw_body=b'{"lat":1}')
    ok2 = spool.enqueue(headers={"X-Drone-Uid": "D1"}, raw_body=b'{"lat":2}')
    ok3 = spool.enqueue(headers={"X-Drone-Uid": "D1"}, raw_body=b'{"lat":3}')
    assert ok1 is True
    assert ok2 is True
    assert ok3 is False
    assert spool.outbox_count() == 2


def test_spool_retry_success_and_dead_letter(tmp_path: Path):
    spool = SQLiteSpool(str(tmp_path / "spool.db"), queue_max=10)
    assert spool.enqueue(headers={"X-Drone-Uid": "D1"}, raw_body=b'{"lat":1}')
    assert spool.enqueue(headers={"X-Drone-Uid": "D1"}, raw_body=b'{"lat":2}')

    events = spool.fetch_ready(limit=10)
    assert len(events) == 2

    first = events[0]
    second = events[1]

    spool.mark_retry(first.id, attempts=1, delay_seconds=0, error_reason="timeout")
    retried = spool.fetch_ready(limit=10)
    first_reloaded = [item for item in retried if item.id == first.id][0]
    assert first_reloaded.attempts == 1
    assert first_reloaded.last_error == "timeout"

    spool.mark_success(second.id)
    assert spool.outbox_count() == 1

    spool.move_to_dead_letter(first_reloaded, error_reason="max_retry", attempts=2)
    assert spool.outbox_count() == 0
    assert spool.dead_letter_count() == 1


def test_spool_enqueue_capacity_check_is_atomic(tmp_path: Path):
    spool = SQLiteSpool(str(tmp_path / "spool.db"), queue_max=1)
    with patch.object(SQLiteSpool, "outbox_count", return_value=0):
        ok1 = spool.enqueue(headers={"X-Drone-Uid": "D1"}, raw_body=b'{"lat":1}')
        ok2 = spool.enqueue(headers={"X-Drone-Uid": "D1"}, raw_body=b'{"lat":2}')
    assert ok1 is True
    assert ok2 is False
    assert spool.outbox_count() == 1
