# ruff: noqa: E501
"""SQLite workspace repository (Phase 6)."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from jarvis.exceptions import WorkspaceValidationError
from jarvis.workspace.models import EntryPoint, ProjectType, StructureSummary, WorkspaceInfo
from jarvis.workspace.repository import WorkspaceHealth, WorkspaceRepository

log = logging.getLogger("jarvis.workspace.sqlite")

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
        CREATE TABLE IF NOT EXISTS workspaces (
            id TEXT PRIMARY KEY,
            root TEXT NOT NULL,
            name TEXT NOT NULL,
            project_type TEXT NOT NULL,
            entry_points TEXT NOT NULL DEFAULT '[]',
            structure TEXT NOT NULL DEFAULT '{}',
            scanned_at TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}'
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_workspaces_root ON workspaces(root)",
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


def _row_to_info(row: sqlite3.Row) -> WorkspaceInfo:
    eps_raw = _decode(str(row["entry_points"]), [])
    eps = []
    for item in eps_raw if isinstance(eps_raw, list) else []:
        if isinstance(item, dict) and "path" in item:
            eps.append(EntryPoint(path=Path(str(item["path"])), kind=str(item.get("kind", "generic")), description=item.get("description")))
    struct_raw = _decode(str(row["structure"]), {})
    struct = None
    if isinstance(struct_raw, dict) and "root" in struct_raw:
        struct = StructureSummary(
            root=Path(str(struct_raw["root"])),
            depth=int(struct_raw.get("depth", 0)),
            total_files=int(struct_raw.get("total_files", 0)),
            total_dirs=int(struct_raw.get("total_dirs", 0)),
            entries=list(struct_raw.get("entries", [])),
        )
    raw_meta = _decode(str(row["metadata"]), {})
    meta_dict = dict(raw_meta) if isinstance(raw_meta, dict) else {}
    return WorkspaceInfo(
        id=str(row["id"]),
        root=Path(str(row["root"])),
        name=str(row["name"]),
        project_type=ProjectType(str(row["project_type"])),
        entry_points=tuple(eps),
        structure=struct,
        scanned_at=datetime.fromisoformat(str(row["scanned_at"])),
        metadata=meta_dict,
    )


class SqliteWorkspaceRepository(WorkspaceRepository):
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
                raise WorkspaceValidationError(f"workspace db corrupted: {self._path} ({exc})") from exc
            except OSError as exc:
                self._close()
                raise WorkspaceValidationError(f"workspace db not accessible: {self._path} ({exc})") from exc

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
            raise WorkspaceValidationError(f"workspace db schema {current} > {SCHEMA_VERSION}")
        for version in range(current, SCHEMA_VERSION):
            for stmt in MIGRATIONS.get(version, []):
                conn.execute(stmt)
            conn.execute("INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('schema_version', ?)", (str(version + 1),))
            conn.commit()

    def _conn_or_raise(self) -> sqlite3.Connection:
        if self._conn is None:
            raise WorkspaceValidationError("workspace repository not initialized")
        return self._conn

    def save(self, info: WorkspaceInfo) -> None:
        info.validate()
        with self._lock:
            conn = self._conn_or_raise()
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO workspaces
                    (id, root, name, project_type, entry_points, structure, scanned_at, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        info.id,
                        str(info.root),
                        info.name,
                        info.project_type.value,
                        _encode([ep.to_dict() for ep in info.entry_points]),
                        _encode(info.structure.to_dict() if info.structure else {}),
                        info.scanned_at.isoformat(),
                        _encode(info.metadata),
                    ),
                )

    def get(self, workspace_id: str) -> WorkspaceInfo | None:
        with self._lock:
            row = self._conn_or_raise().execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
        return _row_to_info(row) if row else None

    def get_by_root(self, root: Path) -> WorkspaceInfo | None:
        with self._lock:
            row = self._conn_or_raise().execute("SELECT * FROM workspaces WHERE root = ?", (str(root),)).fetchone()
        return _row_to_info(row) if row else None

    def list(self) -> list[WorkspaceInfo]:
        with self._lock:
            rows = self._conn_or_raise().execute("SELECT * FROM workspaces ORDER BY scanned_at DESC").fetchall()
        return [_row_to_info(r) for r in rows]

    def health(self) -> WorkspaceHealth:
        try:
            with self._lock:
                conn = self._conn_or_raise()
                accessible = True
                cur = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
                version = int(cur["value"]) if cur else 0
                schema_valid = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='workspaces'").fetchone() is not None
                migrations_current = version == SCHEMA_VERSION
                writable = True
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute("ROLLBACK")
                except sqlite3.DatabaseError:
                    writable = False
                return WorkspaceHealth(accessible, schema_valid, migrations_current, writable, version, "", str(self._path))
        except Exception as exc:  # pragma: no cover
            return WorkspaceHealth(False, False, False, False, 0, str(exc)[:200], str(self._path))
