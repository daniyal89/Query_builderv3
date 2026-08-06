"""Session settings applied to every DuckDB connection this app opens.

There was no preamble at all before this: no ``SET``, no ``PRAGMA`` outside the
build's thread count. Two of these matter once a month can be a VIEW over parquet
rather than a materialised table, because every query then re-reads footers.

``SET GLOBAL``, not plain ``SET``, throughout. A ``DuckDBPyConnection.cursor()`` is
an independent connection with its own session config, and a plain ``SET`` does not
reach it — which is precisely where every real query runs, via
``DuckDBService._borrowed_cursor``. Verified against DuckDB 1.5.3: with plain
``SET`` a borrowed cursor still read ``parquet_metadata_cache = false``.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from backend.config import settings
from backend.services.error_log_service import ErrorLogService


def resolve_temp_directory() -> Path | None:
    """A spill directory that does not depend on the process working directory.

    DuckDB's default ``temp_directory`` is the relative path ``.tmp``. In the frozen
    exe the working directory is wherever the shortcut was launched from — possibly
    read-only — and materialising ~46M rows spills gigabytes. ``settings.RUNTIME_DIR``
    is already the app's writable-state location (it holds ``job_store.sqlite3``) and
    resolves from ``sys.executable`` when frozen.

    Returns ``None`` if the directory cannot be created, so a bad path leaves
    DuckDB's default in place rather than blocking the connection.
    """
    try:
        target = settings.RUNTIME_DIR / "duckdb_tmp"
        # DuckDB does not create this itself, and a missing path only fails later,
        # mid-query, when something actually spills.
        target.mkdir(parents=True, exist_ok=True)
        return target
    except OSError:
        return None


def _sql_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def apply_session_settings(
    conn: duckdb.DuckDBPyConnection,
    *,
    threads: int | None = None,
    preserve_insertion_order: bool | None = None,
) -> list[str]:
    """Apply the standard preamble to *conn*, returning the statements that failed.

    One ``try``/``except`` per statement: an option a future or older DuckDB does
    not recognise must never stop the app from connecting.
    """
    statements: list[str] = [
        # Default is false. A parquet-backed view re-binds its glob on every query,
        # so caching the footers is what keeps repeat queries cheap.
        "SET GLOBAL parquet_metadata_cache = true",
        # Already the default; set explicitly so a future default change cannot
        # silently regress view performance.
        "SET GLOBAL enable_external_file_cache = true",
    ]

    temp_dir = resolve_temp_directory()
    if temp_dir is not None:
        statements.append(
            f"SET GLOBAL temp_directory = {_sql_string_literal(temp_dir.as_posix())}"
        )
    if threads is not None:
        statements.append(f"SET GLOBAL threads = {int(threads)}")
    if preserve_insertion_order is not None:
        statements.append(
            "SET GLOBAL preserve_insertion_order = "
            f"{'true' if preserve_insertion_order else 'false'}"
        )

    failed: list[str] = []
    for statement in statements:
        try:
            conn.execute(statement)
        except Exception as exc:
            failed.append(statement)
            ErrorLogService.append(
                {
                    "endpoint": "duckdb_session",
                    "method": "INTERNAL",
                    "status_code": 200,
                    "error": str(exc),
                    "exception_type": type(exc).__name__,
                    "stage": "session_preamble",
                    "statement": statement,
                }
            )
    return failed
