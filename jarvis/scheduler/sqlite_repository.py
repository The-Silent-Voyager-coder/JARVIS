# ruff: noqa: E501
"""SQLite scheduler repository (roadmap Phase C)."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path

from jarvis.exceptions import SchedulerValidationError
from jarvis.scheduler.models import Schedule
from jarvis.scheduler.repository import SchedulerHealth, SchedulerRepository
from jarvis.storage.recovery import quarantine_corrupt_file

log = logging.getLogger("jarvis.scheduler.sqlite")

SCHEMA_VERSION = 1

MIGRATIONS: dict[int, list[str]] = {
    0: [
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS schedules (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            interval_seconds INTEGER NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}',
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            last_run_at TEXT,
            next_run_at TEXT NOT NULL,
            last_status TEXT NOT NULL DEFAULT 'never',
            last_summary TEXT NOT NULL DEFAULT ''
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_schedules_next_run ON schedules(next_run_at)",
    ],
}


def _encode(val: object) -> str:
    return json.dumps(val, ensure_ascii=True, sort_keys=True)


def _decode(raw: str | None, default: object) -> object:
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _row_to_schedule(row: sqlite3.Row) -> Schedule:
    payload_raw = _decode(str(row["payload"]), {})
    payload = dict(payload_raw) if isinstance(payload_raw, dict) else {}
    return Schedule.from_dict({
        "id": str(row["id"]),
        "name": str(row["name"]),
        "kind": str(row["kind"]),
        "interval_seconds": int(row["interval_seconds"]),
        "payload": payload,
        "enabled": bool(row["enabled"]),
        "created_at": str(row["created_at"]),
        "last_run_at": str(row["last_run_at"]) if row["last_run_at"] else None,
        "next_run_at": str(row["next_run_at"]),
        "last_status": str(row["last_status"]),
        "last_summary": str(row["last_summary"]),
    })


class SqliteSchedulerRepository(SchedulerRepository):
    def __init__(self, database_path: str | Path) -> None:
        self._path = Path(database_path)
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None

    def initialize(self) -> None:
        with self._lock:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(str(self._path), timeout=5.0)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=5000")
                conn.execute("PRAGMA foreign_keys=ON")
                self._conn = conn
                self._migrate(conn)
            except sqlite3.DatabaseError as exc:
                self._close()
                saved = quarantine_corrupt_file(self._path, reason=f"open failed: {exc}")
                hint = f" (quarantined copy: {saved})" if saved else ""
                raise SchedulerValidationError(f"scheduler db corrupted (file kept as-is): {self._path} ({exc}){hint}") from exc
            except OSError as exc:
                self._close()
                raise SchedulerValidationError(f"scheduler db not accessible: {self._path} ({exc})") from exc

    def close(self) -> None:
        with self._lock:
            self._close()

    def _close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.DatabaseError:
                pass
            self._conn = None

    def _migrate(self, conn: sqlite3.Connection) -> None:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_meta'").fetchone()
        current = 0
        if cur is not None:
            row = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
            current = int(row["value"]) if row else 0
        if current > SCHEMA_VERSION:
            raise SchedulerValidationError(f"scheduler db schema {current} > {SCHEMA_VERSION}")
        for version in range(current, SCHEMA_VERSION):
            for stmt in MIGRATIONS.get(version, []):
                conn.execute(stmt)
            conn.execute("INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('schema_version', ?)", (str(version + 1),))
            conn.commit()

    def _conn_or_raise(self) -> sqlite3.Connection:
        if self._conn is None:
            raise SchedulerValidationError("scheduler repository not initialized")
        return self._conn

    def save(self, schedule: Schedule) -> None:
        schedule.validate()
        with self._lock:
            conn = self._conn_or_raise()
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO schedules
                    (id, name, kind, interval_seconds, payload, enabled,
                     created_at, last_run_at, next_run_at, last_status, last_summary)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        schedule.id,
                        schedule.name,
                        schedule.kind.value,
                        schedule.interval_seconds,
                        _encode(schedule.payload),
                        1 if schedule.enabled else 0,
                        schedule.created_at.isoformat(),
                        schedule.last_run_at.isoformat() if schedule.last_run_at else None,
                        schedule.next_run_at.isoformat(),
                        schedule.last_status,
                        schedule.last_summary,
                    ),
                )

    def get(self, schedule_id: str) -> Schedule | None:
        with self._lock:
            row = self._conn_or_raise().execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
        return _row_to_schedule(row) if row else None

    def remove(self, schedule_id: str) -> bool:
        with self._lock:
            conn = self._conn_or_raise()
            with conn:
                cur = conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
                return cur.rowcount > 0

    def list(self) -> list[Schedule]:
        with self._lock:
            rows = self._conn_or_raise().execute("SELECT * FROM schedules ORDER BY next_run_at ASC").fetchall()
        return [_row_to_schedule(r) for r in rows]

    def count(self) -> int:
        with self._lock:
            row = self._conn_or_raise().execute("SELECT COUNT(*) AS n FROM schedules").fetchone()
        return int(row["n"]) if row else 0

    def health(self) -> SchedulerHealth:
        try:
            with self._lock:
                conn = self._conn_or_raise()
                accessible = True
                cur = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
                version = int(cur["value"]) if cur else 0
                schema_valid = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schedules'").fetchone() is not None
                migrations_current = version == SCHEMA_VERSION
                writable = True
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute("ROLLBACK")
                except sqlite3.DatabaseError:
                    writable = False
                return SchedulerHealth(accessible, schema_valid, migrations_current, writable, version, "", str(self._path))
        except Exception as exc:  # pragma: no cover
            return SchedulerHealth(False, False, False, False, 0, str(exc)[:200], str(self._path))
