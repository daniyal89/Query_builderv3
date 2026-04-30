"""Persistent background job runtime backed by a local SQLite store."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from backend.config import settings


FINAL_JOB_STATUSES = frozenset({"completed", "failed", "cancelled"})
RECOVERABLE_JOB_STATUSES = frozenset({"queued", "running", "cancelling"})
_UNSET = object()

SnapshotMutator = Callable[[dict[str, Any]], dict[str, Any] | None]
Worker = Callable[[str], None]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class BackgroundJobCancelled(Exception):
    """Raised when a persisted background job is cancelled."""


@dataclass(frozen=True)
class BackgroundJobPolicy:
    max_attempts: int = 1
    retry_backoff_seconds: int = 0


class PersistentJobStore:
    """SQLite-backed store for background job snapshots and dead letters."""

    def __init__(self, path_provider: Callable[[], Path] | Path) -> None:
        if callable(path_provider):
            self._path_provider = path_provider
        else:
            fixed_path = Path(path_provider)
            self._path_provider = lambda: fixed_path
        self._lock = threading.RLock()
        self._initialized_path: Path | None = None

    def set_path_for_tests(self, path: Path) -> None:
        test_path = Path(path)
        with self._lock:
            self._path_provider = lambda: test_path
            self._initialized_path = None

    def ensure_schema(self) -> Path:
        with self._lock:
            db_path = self._resolve_path()
            if self._initialized_path == db_path:
                return db_path

            with self._connect_locked(db_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS jobs (
                        job_id TEXT PRIMARY KEY,
                        job_type TEXT NOT NULL,
                        status TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        snapshot_json TEXT NOT NULL,
                        cancel_requested INTEGER NOT NULL DEFAULT 0,
                        attempt_count INTEGER NOT NULL DEFAULT 0,
                        max_attempts INTEGER NOT NULL DEFAULT 1,
                        retry_backoff_seconds INTEGER NOT NULL DEFAULT 0,
                        last_error TEXT,
                        dead_lettered_at TEXT,
                        dead_letter_reason TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
                    CREATE INDEX IF NOT EXISTS idx_jobs_type ON jobs(job_type);
                    CREATE TABLE IF NOT EXISTS job_dead_letters (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        job_id TEXT NOT NULL,
                        job_type TEXT NOT NULL,
                        attempt_count INTEGER NOT NULL,
                        recorded_at TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        last_error TEXT,
                        snapshot_json TEXT NOT NULL,
                        payload_json TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_job_dead_letters_job_id ON job_dead_letters(job_id);
                    """
                )
                conn.commit()

            self._initialized_path = db_path
            return db_path

    def create_job(
        self,
        *,
        job_id: str,
        job_type: str,
        snapshot: dict[str, Any],
        payload: dict[str, Any] | None = None,
        policy: BackgroundJobPolicy = BackgroundJobPolicy(),
    ) -> dict[str, Any]:
        self.ensure_schema()
        now = _utc_now_iso()
        normalized_snapshot = dict(snapshot)
        normalized_snapshot["job_id"] = job_id
        normalized_snapshot["status"] = normalized_snapshot.get("status", "queued")

        with self._lock:
            db_path = self._resolve_path()
            record = {
                "job_id": job_id,
                "job_type": job_type,
                "status": normalized_snapshot["status"],
                "payload": payload or {},
                "snapshot": normalized_snapshot,
                "cancel_requested": False,
                "attempt_count": 0,
                "max_attempts": max(1, int(policy.max_attempts)),
                "retry_backoff_seconds": max(0, int(policy.retry_backoff_seconds)),
                "last_error": None,
                "dead_lettered_at": None,
                "dead_letter_reason": None,
                "created_at": now,
                "updated_at": now,
            }
            with self._connect_locked(db_path) as conn:
                self._save_record_locked(conn, record)
                conn.commit()
            return self._combine_record(record)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        self.ensure_schema()
        with self._lock:
            db_path = self._resolve_path()
            with self._connect_locked(db_path) as conn:
                record = self._fetch_record_locked(conn, job_id)
            return self._combine_record(record) if record else None

    def mutate_job(
        self,
        job_id: str,
        *,
        mutator: SnapshotMutator | None = None,
        merge_updates: dict[str, Any] | None = None,
        counter_increments: dict[str, int] | None = None,
        status: Any = _UNSET,
        cancel_requested: Any = _UNSET,
        last_error: Any = _UNSET,
        dead_lettered_at: Any = _UNSET,
        dead_letter_reason: Any = _UNSET,
        attempt_increment: int = 0,
    ) -> dict[str, Any] | None:
        self.ensure_schema()
        with self._lock:
            db_path = self._resolve_path()
            with self._connect_locked(db_path) as conn:
                record = self._fetch_record_locked(conn, job_id)
                if record is None:
                    return None

                snapshot = dict(record["snapshot"])
                if mutator is not None:
                    maybe_snapshot = mutator(snapshot)
                    if maybe_snapshot is not None:
                        snapshot = maybe_snapshot

                if merge_updates:
                    snapshot.update(merge_updates)

                if counter_increments:
                    for field, amount in counter_increments.items():
                        snapshot[field] = int(snapshot.get(field, 0)) + int(amount)

                if status is not _UNSET:
                    record["status"] = status
                    snapshot["status"] = status

                if cancel_requested is not _UNSET:
                    record["cancel_requested"] = bool(cancel_requested)

                if last_error is not _UNSET:
                    record["last_error"] = last_error

                if dead_lettered_at is not _UNSET:
                    record["dead_lettered_at"] = dead_lettered_at

                if dead_letter_reason is not _UNSET:
                    record["dead_letter_reason"] = dead_letter_reason

                if attempt_increment:
                    record["attempt_count"] = max(0, int(record["attempt_count"]) + int(attempt_increment))

                record["snapshot"] = snapshot
                record["updated_at"] = _utc_now_iso()
                self._save_record_locked(conn, record)
                conn.commit()
                return self._combine_record(record)

    def mark_attempt_started(self, job_id: str) -> dict[str, Any] | None:
        started_at = _utc_now_iso()

        def mutate(snapshot: dict[str, Any]) -> None:
            snapshot.setdefault("started_at", started_at)
            snapshot["finished_at"] = None
            snapshot.pop("next_retry_at", None)

        return self.mutate_job(
            job_id,
            mutator=mutate,
            status="running",
            last_error=None,
            dead_lettered_at=None,
            dead_letter_reason=None,
            attempt_increment=1,
        )

    def request_cancel(self, job_id: str, message: str) -> dict[str, Any] | None:
        return self.mutate_job(
            job_id,
            merge_updates={"message": message},
            status="cancelling",
            cancel_requested=True,
        )

    def record_dead_letter(self, job_id: str, reason: str, last_error: str | None) -> dict[str, Any] | None:
        self.ensure_schema()
        recorded_at = _utc_now_iso()
        with self._lock:
            db_path = self._resolve_path()
            with self._connect_locked(db_path) as conn:
                record = self._fetch_record_locked(conn, job_id)
                if record is None:
                    return None

                conn.execute(
                    """
                    INSERT INTO job_dead_letters (
                        job_id,
                        job_type,
                        attempt_count,
                        recorded_at,
                        reason,
                        last_error,
                        snapshot_json,
                        payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record["job_id"],
                        record["job_type"],
                        int(record["attempt_count"]),
                        recorded_at,
                        reason,
                        last_error,
                        self._json_dumps(record["snapshot"]),
                        self._json_dumps(record["payload"]),
                    ),
                )
                record["dead_lettered_at"] = recorded_at
                record["dead_letter_reason"] = reason
                record["last_error"] = last_error
                record["updated_at"] = recorded_at
                self._save_record_locked(conn, record)
                conn.commit()
                return self._combine_record(record)

    def list_dead_letters(self, limit: int = 50) -> list[dict[str, Any]]:
        self.ensure_schema()
        safe_limit = max(1, int(limit))
        with self._lock:
            db_path = self._resolve_path()
            with self._connect_locked(db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT
                        id,
                        job_id,
                        job_type,
                        attempt_count,
                        recorded_at,
                        reason,
                        last_error,
                        snapshot_json,
                        payload_json
                    FROM job_dead_letters
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()

        return [
            {
                "id": int(row["id"]),
                "job_id": row["job_id"],
                "job_type": row["job_type"],
                "attempt_count": int(row["attempt_count"]),
                "recorded_at": row["recorded_at"],
                "reason": row["reason"],
                "last_error": row["last_error"],
                "snapshot": self._json_loads(row["snapshot_json"]),
                "payload": self._json_loads(row["payload_json"]),
            }
            for row in rows
        ]

    def recover_interrupted_jobs(self) -> int:
        self.ensure_schema()
        recovery_message = "Application restarted before the background job finished. Re-run the job manually."
        recovered = 0

        with self._lock:
            db_path = self._resolve_path()
            with self._connect_locked(db_path) as conn:
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE status IN (?, ?, ?)",
                    tuple(RECOVERABLE_JOB_STATUSES),
                ).fetchall()

                for row in rows:
                    record = self._row_to_record(row)
                    snapshot = dict(record["snapshot"])
                    snapshot["status"] = "failed"
                    snapshot["message"] = recovery_message
                    snapshot["finished_at"] = _utc_now_iso()
                    record["status"] = "failed"
                    record["cancel_requested"] = False
                    record["last_error"] = recovery_message
                    record["snapshot"] = snapshot
                    record["updated_at"] = _utc_now_iso()
                    self._save_record_locked(conn, record)
                    recovered += 1

                conn.commit()

        return recovered

    def _resolve_path(self) -> Path:
        return Path(self._path_provider()).expanduser().resolve()

    @staticmethod
    def _json_dumps(value: Any) -> str:
        return json.dumps(value, default=str, sort_keys=True)

    @staticmethod
    def _json_loads(value: str) -> dict[str, Any]:
        return json.loads(value) if value else {}

    def _connect_locked(self, db_path: Path) -> sqlite3.Connection:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    def _fetch_record_locked(self, conn: sqlite3.Connection, job_id: str) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return self._row_to_record(row) if row else None

    def _row_to_record(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "job_id": row["job_id"],
            "job_type": row["job_type"],
            "status": row["status"],
            "payload": self._json_loads(row["payload_json"]),
            "snapshot": self._json_loads(row["snapshot_json"]),
            "cancel_requested": bool(row["cancel_requested"]),
            "attempt_count": int(row["attempt_count"]),
            "max_attempts": int(row["max_attempts"]),
            "retry_backoff_seconds": int(row["retry_backoff_seconds"]),
            "last_error": row["last_error"],
            "dead_lettered_at": row["dead_lettered_at"],
            "dead_letter_reason": row["dead_letter_reason"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _combine_record(self, record: dict[str, Any]) -> dict[str, Any]:
        snapshot = dict(record["snapshot"])
        snapshot["job_id"] = record["job_id"]
        snapshot["status"] = record["status"]
        snapshot["attempt_count"] = int(record["attempt_count"])
        snapshot["max_attempts"] = int(record["max_attempts"])
        snapshot["retry_backoff_seconds"] = int(record["retry_backoff_seconds"])
        snapshot["cancel_requested"] = bool(record["cancel_requested"])
        snapshot["job_type"] = snapshot.get("job_type", record["job_type"])
        snapshot["created_at"] = record["created_at"]
        snapshot["updated_at"] = record["updated_at"]

        if record["last_error"] is not None:
            snapshot["last_error"] = record["last_error"]
        if record["dead_lettered_at"] is not None:
            snapshot["dead_lettered_at"] = record["dead_lettered_at"]
        if record["dead_letter_reason"] is not None:
            snapshot["dead_letter_reason"] = record["dead_letter_reason"]
        return snapshot

    def _save_record_locked(self, conn: sqlite3.Connection, record: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT OR REPLACE INTO jobs (
                job_id,
                job_type,
                status,
                payload_json,
                snapshot_json,
                cancel_requested,
                attempt_count,
                max_attempts,
                retry_backoff_seconds,
                last_error,
                dead_lettered_at,
                dead_letter_reason,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["job_id"],
                record["job_type"],
                record["status"],
                self._json_dumps(record["payload"]),
                self._json_dumps(record["snapshot"]),
                1 if record["cancel_requested"] else 0,
                int(record["attempt_count"]),
                int(record["max_attempts"]),
                int(record["retry_backoff_seconds"]),
                record["last_error"],
                record["dead_lettered_at"],
                record["dead_letter_reason"],
                record["created_at"],
                record["updated_at"],
            ),
        )


class PersistentJobRuntime:
    """Background job runtime with persistent snapshots and retry/dead-letter support."""

    def __init__(
        self,
        store: PersistentJobStore,
        recover_interrupted_provider: Callable[[], bool] | bool = True,
    ) -> None:
        self._store = store
        if callable(recover_interrupted_provider):
            self._recover_interrupted_provider = recover_interrupted_provider
        else:
            self._recover_interrupted_provider = lambda: bool(recover_interrupted_provider)
        self._events_lock = threading.Lock()
        self._cancel_events: dict[str, threading.Event] = {}
        self._initialized_path: Path | None = None

    def reset_for_tests(self, path: Path) -> None:
        with self._events_lock:
            for event in self._cancel_events.values():
                event.set()
            self._cancel_events.clear()
            self._initialized_path = None
        self._store.set_path_for_tests(path)

    def initialize(self) -> None:
        db_path = self._store.ensure_schema()
        if self._initialized_path == db_path:
            return
        if self._recover_interrupted_provider():
            self._store.recover_interrupted_jobs()
        self._initialized_path = db_path

    def start_job(
        self,
        *,
        job_type: str,
        initial_snapshot: dict[str, Any],
        worker: Worker,
        payload: dict[str, Any] | None = None,
        policy: BackgroundJobPolicy = BackgroundJobPolicy(),
        job_id: str | None = None,
    ) -> dict[str, Any]:
        self.initialize()
        resolved_job_id = job_id or uuid.uuid4().hex
        snapshot = dict(initial_snapshot)
        snapshot["job_id"] = resolved_job_id
        snapshot["status"] = snapshot.get("status", "queued")
        created_job = self._store.create_job(
            job_id=resolved_job_id,
            job_type=job_type,
            snapshot=snapshot,
            payload=payload,
            policy=policy,
        )
        with self._events_lock:
            self._cancel_events[resolved_job_id] = threading.Event()
        threading.Thread(
            target=self._run_job,
            args=(resolved_job_id, worker, policy),
            daemon=True,
        ).start()
        return created_job

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        self.initialize()
        return self._store.get_job(job_id)

    def stop_job(self, job_id: str, message: str) -> dict[str, Any] | None:
        self.initialize()
        current = self._store.get_job(job_id)
        if current is None:
            return None
        if current.get("status") in FINAL_JOB_STATUSES:
            return current

        with self._events_lock:
            event = self._cancel_events.setdefault(job_id, threading.Event())
            event.set()
        return self._store.request_cancel(job_id, message)

    def is_cancelled(self, job_id: str) -> bool:
        with self._events_lock:
            event = self._cancel_events.get(job_id)
        if event is not None:
            return event.is_set()
        current = self._store.get_job(job_id)
        return bool(current and current.get("cancel_requested"))

    def raise_if_cancelled(self, job_id: str) -> None:
        if self.is_cancelled(job_id):
            raise BackgroundJobCancelled()

    def update_job(self, job_id: str, **updates: Any) -> dict[str, Any] | None:
        status = updates.pop("status", _UNSET)
        last_error = updates.pop("last_error", _UNSET)
        cancel_requested = updates.pop("cancel_requested", _UNSET)
        dead_lettered_at = updates.pop("dead_lettered_at", _UNSET)
        dead_letter_reason = updates.pop("dead_letter_reason", _UNSET)
        return self._store.mutate_job(
            job_id,
            merge_updates=updates or None,
            status=status,
            cancel_requested=cancel_requested,
            last_error=last_error,
            dead_lettered_at=dead_lettered_at,
            dead_letter_reason=dead_letter_reason,
        )

    def increment_job(self, job_id: str, **increments: int) -> dict[str, Any] | None:
        return self._store.mutate_job(job_id, counter_increments=increments)

    def mutate_job(
        self,
        job_id: str,
        mutator: SnapshotMutator,
        *,
        status: Any = _UNSET,
        last_error: Any = _UNSET,
        cancel_requested: Any = _UNSET,
        dead_lettered_at: Any = _UNSET,
        dead_letter_reason: Any = _UNSET,
    ) -> dict[str, Any] | None:
        return self._store.mutate_job(
            job_id,
            mutator=mutator,
            status=status,
            last_error=last_error,
            cancel_requested=cancel_requested,
            dead_lettered_at=dead_lettered_at,
            dead_letter_reason=dead_letter_reason,
        )

    def list_dead_letters(self, limit: int = 50) -> list[dict[str, Any]]:
        self.initialize()
        return self._store.list_dead_letters(limit=limit)

    def _run_job(self, job_id: str, worker: Worker, policy: BackgroundJobPolicy) -> None:
        try:
            while True:
                if self.is_cancelled(job_id):
                    self._mark_cancelled(job_id)
                    return

                self._store.mark_attempt_started(job_id)
                try:
                    worker(job_id)
                except BackgroundJobCancelled:
                    self._mark_cancelled(job_id)
                    return
                except Exception as exc:
                    if self.is_cancelled(job_id):
                        self._mark_cancelled(job_id)
                        return

                    current = self.get_job(job_id) or {}
                    error_text = str(exc)
                    attempt_count = int(current.get("attempt_count", 0))
                    if attempt_count < max(1, int(policy.max_attempts)):
                        retry_at = datetime.now(timezone.utc) + timedelta(seconds=max(0, int(policy.retry_backoff_seconds)))
                        self.update_job(
                            job_id,
                            status="queued",
                            message=f"Attempt {attempt_count} failed: {error_text}. Retrying...",
                            next_retry_at=retry_at.isoformat(timespec="seconds"),
                            finished_at=None,
                            last_error=error_text,
                        )
                        if self._wait_for_retry(job_id, max(0, int(policy.retry_backoff_seconds))):
                            self._mark_cancelled(job_id)
                            return
                        continue

                    dead_letter = self._store.record_dead_letter(
                        job_id,
                        reason="max_attempts_exhausted",
                        last_error=error_text,
                    )
                    dead_lettered_at = dead_letter.get("dead_lettered_at") if dead_letter else _utc_now_iso()
                    self.update_job(
                        job_id,
                        status="failed",
                        message=error_text,
                        finished_at=_utc_now_iso(),
                        next_retry_at=None,
                        last_error=error_text,
                        dead_lettered_at=dead_lettered_at,
                        dead_letter_reason="max_attempts_exhausted",
                    )
                    return
                else:
                    current = self.get_job(job_id) or {}
                    if current.get("status") in FINAL_JOB_STATUSES:
                        return
                    if self.is_cancelled(job_id):
                        self._mark_cancelled(job_id, current.get("message") or "Stopped by user.")
                        return
                    self.update_job(
                        job_id,
                        status="completed",
                        message=current.get("message") or "Completed successfully.",
                        finished_at=_utc_now_iso(),
                        next_retry_at=None,
                        last_error=None,
                    )
                    return
        finally:
            with self._events_lock:
                self._cancel_events.pop(job_id, None)

    def _wait_for_retry(self, job_id: str, delay_seconds: int) -> bool:
        if delay_seconds <= 0:
            return self.is_cancelled(job_id)

        with self._events_lock:
            event = self._cancel_events.get(job_id)
        if event is not None and event.wait(delay_seconds):
            return True
        return self.is_cancelled(job_id)

    def _mark_cancelled(self, job_id: str, message: str = "Stopped by user.") -> dict[str, Any] | None:
        return self.update_job(
            job_id,
            status="cancelled",
            message=message,
            finished_at=_utc_now_iso(),
            next_retry_at=None,
            cancel_requested=True,
        )


job_runtime = PersistentJobRuntime(
    PersistentJobStore(lambda: settings.JOB_STORE_PATH),
    recover_interrupted_provider=lambda: settings.JOB_RECOVER_INTERRUPTED,
)
