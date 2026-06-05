from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SpoolEvent:
    id: int
    created_at_ms: int
    headers: dict[str, str]
    body: bytes
    attempts: int
    next_retry_at_ms: int
    last_error: str | None


def _now_ms() -> int:
    return int(time.time() * 1000)


class SQLiteSpool:
    def __init__(self, db_path: str, *, queue_max: int) -> None:
        self._db_path = Path(db_path)
        self._queue_max = queue_max
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at_ms INTEGER NOT NULL,
                    headers_json TEXT NOT NULL,
                    body_json TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_retry_at_ms INTEGER NOT NULL,
                    last_error TEXT
                );
                CREATE INDEX IF NOT EXISTS ix_outbox_next_retry ON outbox (next_retry_at_ms, id);

                CREATE TABLE IF NOT EXISTS dead_letter (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_event_id INTEGER,
                    created_at_ms INTEGER NOT NULL,
                    failed_at_ms INTEGER NOT NULL,
                    headers_json TEXT NOT NULL,
                    body_json TEXT NOT NULL,
                    attempts INTEGER NOT NULL,
                    error_reason TEXT
                );
                """
            )

    def outbox_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM outbox").fetchone()
            return int(row["count"]) if row else 0

    def dead_letter_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM dead_letter").fetchone()
            return int(row["count"]) if row else 0

    def enqueue(self, *, headers: dict[str, str], raw_body: bytes) -> bool:
        created_at_ms = _now_ms()
        with self._connect() as conn:
            # Make queue capacity check + insert atomic to avoid race between concurrent writers.
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT COUNT(*) AS count FROM outbox").fetchone()
            current_count = int(row["count"]) if row else 0
            if current_count >= self._queue_max:
                conn.rollback()
                return False

            conn.execute(
                """
                INSERT INTO outbox(created_at_ms, headers_json, body_json, attempts, next_retry_at_ms, last_error)
                VALUES(?, ?, ?, 0, ?, NULL)
                """,
                (created_at_ms, json.dumps(headers), raw_body.decode("utf-8"), created_at_ms),
            )
            conn.commit()
            return True

    def fetch_ready(self, *, limit: int) -> list[SpoolEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, created_at_ms, headers_json, body_json, attempts, next_retry_at_ms, last_error
                FROM outbox
                WHERE next_retry_at_ms <= ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (_now_ms(), limit),
            ).fetchall()

        return [
            SpoolEvent(
                id=int(row["id"]),
                created_at_ms=int(row["created_at_ms"]),
                headers=dict(json.loads(row["headers_json"])),
                body=str(row["body_json"]).encode("utf-8"),
                attempts=int(row["attempts"]),
                next_retry_at_ms=int(row["next_retry_at_ms"]),
                last_error=row["last_error"],
            )
            for row in rows
        ]

    def mark_success(self, event_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM outbox WHERE id = ?", (event_id,))

    def mark_retry(self, event_id: int, *, attempts: int, delay_seconds: float, error_reason: str) -> None:
        next_retry_at_ms = _now_ms() + int(max(0.0, delay_seconds) * 1000)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE outbox
                SET attempts = ?, next_retry_at_ms = ?, last_error = ?
                WHERE id = ?
                """,
                (attempts, next_retry_at_ms, error_reason, event_id),
            )

    def move_to_dead_letter(self, event: SpoolEvent, *, error_reason: str, attempts: int) -> None:
        now = _now_ms()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO dead_letter(
                    original_event_id, created_at_ms, failed_at_ms, headers_json, body_json, attempts, error_reason
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.created_at_ms,
                    now,
                    json.dumps(event.headers),
                    event.body.decode("utf-8"),
                    attempts,
                    error_reason,
                ),
            )
            conn.execute("DELETE FROM outbox WHERE id = ?", (event.id,))
