"""SQLite travel plans with immutable revisions and optimistic concurrency."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class ConflictError(ValueError):
    """The caller edited a version that is no longer current."""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _serialize(plan):
    if hasattr(plan, "model_dump"):
        plan = plan.model_dump(mode="json")
    return json.dumps(plan, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


class Storage:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS trips (
                    id TEXT PRIMARY KEY,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    plan_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trip_versions (
                    trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    PRIMARY KEY (trip_id, version)
                );
            """)

    @contextmanager
    def _connection(self, write=False):
        conn = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            if write:
                conn.commit()
        except BaseException:
            if write:
                conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _trip(row):
        if row is None:
            raise KeyError("行程不存在")
        return {
            "id": row["id"],
            "version": row["version"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "plan": json.loads(row["plan_json"]),
        }

    def create(self, plan):
        payload, trip_id, now = _serialize(plan), str(uuid4()), _now()
        with self._connection(write=True) as conn:
            conn.execute(
                "INSERT INTO trips VALUES (?,1,?,?,?)", (trip_id, now, now, payload)
            )
            conn.execute(
                "INSERT INTO trip_versions VALUES (?,1,?,?,?)",
                (trip_id, now, "创建行程", payload),
            )
            return self._trip(
                conn.execute("SELECT * FROM trips WHERE id=?", (trip_id,)).fetchone()
            )

    def list(self):
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM trips ORDER BY updated_at DESC, id"
            ).fetchall()
        summaries = []
        for row in rows:
            trip = self._trip(row)
            plan = trip.pop("plan")
            preferences, budget = plan.get("preferences", {}), plan.get("budget", {})
            trip.update(
                {
                    "title": plan.get("title", "旅行计划"),
                    "destination": preferences.get("destination", ""),
                    "start_date": preferences.get("start_date", ""),
                    "days": preferences.get("days", len(plan.get("days", []))),
                    "travelers": preferences.get("travelers", 1),
                    "budget": preferences.get("budget", budget.get("limit", 0)),
                    "total": budget.get("total", 0),
                }
            )
            summaries.append(trip)
        return summaries

    def get(self, trip_id):
        with self._connection() as conn:
            return self._trip(
                conn.execute("SELECT * FROM trips WHERE id=?", (trip_id,)).fetchone()
            )

    @staticmethod
    def _write_revision(conn, row, payload, base_version, reason):
        if row is None:
            raise KeyError("行程不存在")
        if row["version"] != base_version:
            raise ConflictError("行程已更新，请刷新后再修改。")
        version, now, trip_id = row["version"] + 1, _now(), row["id"]
        conn.execute(
            "INSERT INTO trip_versions VALUES (?,?,?,?,?)",
            (trip_id, version, now, reason, payload),
        )
        conn.execute(
            "UPDATE trips SET version=?,updated_at=?,plan_json=? WHERE id=?",
            (version, now, payload, trip_id),
        )
        return Storage._trip(
            conn.execute("SELECT * FROM trips WHERE id=?", (trip_id,)).fetchone()
        )

    def revise(self, trip_id, plan, base_version, reason):
        payload = _serialize(plan)
        with self._connection(write=True) as conn:
            row = conn.execute("SELECT * FROM trips WHERE id=?", (trip_id,)).fetchone()
            return self._write_revision(conn, row, payload, base_version, reason)

    def versions(self, trip_id):
        with self._connection() as conn:
            if not conn.execute(
                "SELECT 1 FROM trips WHERE id=?", (trip_id,)
            ).fetchone():
                raise KeyError("行程不存在")
            rows = conn.execute(
                "SELECT version,created_at,reason,plan_json FROM trip_versions WHERE trip_id=? ORDER BY version DESC",
                (trip_id,),
            ).fetchall()
        return [
            {
                "version": row["version"],
                "created_at": row["created_at"],
                "reason": row["reason"],
                "title": json.loads(row["plan_json"]).get("title", "旅行计划"),
            }
            for row in rows
        ]

    def restore(self, trip_id, version, base_version):
        with self._connection(write=True) as conn:
            current = conn.execute(
                "SELECT * FROM trips WHERE id=?", (trip_id,)
            ).fetchone()
            if current is None:
                raise KeyError("行程不存在")
            old = conn.execute(
                "SELECT plan_json FROM trip_versions WHERE trip_id=? AND version=?",
                (trip_id, version),
            ).fetchone()
            if old is None:
                raise KeyError("历史版本不存在")
            return self._write_revision(
                conn, current, old["plan_json"], base_version, f"恢复至版本 {version}"
            )

    def delete(self, trip_id):
        with self._connection(write=True) as conn:
            if conn.execute("DELETE FROM trips WHERE id=?", (trip_id,)).rowcount == 0:
                raise KeyError("行程不存在")
