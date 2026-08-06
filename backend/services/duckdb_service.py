"""
duckdb_service.py — Manages DuckDB connection lifecycle.

Provides connect, disconnect, execute, and schema-introspection methods.
Thread safety is handled via a threading.Lock since DuckDB connections
are not safe to share across threads.
"""

import os
import re
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

import duckdb

from backend.models.local_object import FileObjectRequest, FilePreviewRequest, FilePreviewResponse
from backend.models.schema import TableMetadata, ColumnDetail
from backend.services.duckdb_session import apply_session_settings
from backend.services.sample_snapshot_service import SampleSnapshotService


VALID_OBJECT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SUPPORTED_SOURCE_EXTENSIONS = {".csv", ".tsv", ".xlsx"}


class DatabaseLockedError(RuntimeError):
    """Raised when DuckDB cannot open a file because another process holds an exclusive lock."""


class SourceUnavailableError(RuntimeError):
    """A view's underlying files could not be read.

    Distinct from "the object does not exist": the object is right there in the
    catalog with its columns intact, and only reading through it fails — a renamed
    folder, an unmapped drive, a deleted parquet. Worth its own type because the
    remedy is completely different, and because an unhandled DuckDB IOException
    would otherwise surface as a 500 with its message discarded.
    """



class DuckDBService:
    """Singleton service managing a single DuckDB connection."""

    _conn: Optional[duckdb.DuckDBPyConnection]
    _db_path: Optional[Path]
    _lock: threading.Lock
    _read_only: bool

    def __init__(self) -> None:
        self._conn = None
        self._db_path = None
        self._lock = threading.Lock()
        self._read_only = False
        # Cursors borrowed by long-running statements that no longer hold _lock.
        # connect/disconnect wait for these to drain before closing the parent.
        self._idle = threading.Condition(self._lock)
        self._in_flight = 0

    @property
    def is_connected(self) -> bool:
        return self._conn is not None

    @property
    def is_read_only(self) -> bool:
        return self._read_only

    def _normalize_user_path(self, raw_path: str) -> Path:
        value = (raw_path or "").strip()
        if not value:
            raise ValueError("Path cannot be empty.")
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1].strip()
        value = os.path.expandvars(os.path.expanduser(value))
        return Path(value)

    def connect(self, db_path: str) -> int:
        if not db_path or not db_path.strip():
            raise ValueError("Database path cannot be empty.")

        path_obj = self._normalize_user_path(db_path)
        resolved = path_obj.resolve() if path_obj.is_absolute() else (Path.cwd() / path_obj).resolve()

        if not resolved.parent.exists():
            raise FileNotFoundError(f"Parent directory does not exist: {resolved.parent}")

        with self._lock:
            self._drain_and_close_unlocked()

            try:
                self._conn = duckdb.connect(str(resolved), read_only=False)
            except duckdb.IOException as exc:
                self._conn = None
                self._db_path = None
                self._read_only = False
                err_msg = str(exc)
                # Windows OS-level exclusive lock: no connection mode can recover from this.
                if "being used by another process" in err_msg or "already open" in err_msg.lower():
                    raise DatabaseLockedError(
                        f"The file '{resolved}' is locked by another process and cannot be opened. "
                        "Close the other application using this .duckdb file, then try again."
                    ) from exc
                raise RuntimeError(f"Failed to open DuckDB database: {exc}") from exc
            except duckdb.Error as exc:
                self._conn = None
                self._db_path = None
                self._read_only = False
                raise RuntimeError(f"Failed to open DuckDB database: {exc}") from exc

            self._db_path = resolved
            self._read_only = False
            # Before any query runs: caches the parquet footers a view re-reads on
            # every bind, and pins the spill directory off the working directory.
            apply_session_settings(self._conn)
            tables = self._fetch_table_entries_unlocked()
            try:
                SampleSnapshotService.capture_duckdb_once(self._conn, resolved)
            except Exception:
                # Snapshot capture is non-blocking and must never fail connection flow.
                pass
            return len(tables)

    def disconnect(self) -> None:
        with self._lock:
            was_connected = self._conn is not None
            self._drain_and_close_unlocked()
            if was_connected:
                self._db_path = None
                self._read_only = False

    def list_tables(self) -> list[TableMetadata]:
        """Metadata for every user table and view, in three catalog queries.

        This used to run ``SELECT COUNT(*)`` plus an ``information_schema.columns``
        query *per table* while holding the service-wide lock — so the Home page
        full-scanned every 46M-row month on every load, and the cost grew by one
        table each month. ``duckdb_tables.estimated_size`` is the cardinality
        DuckDB already keeps in the catalog: free, and exact for tables that are
        bulk-loaded and never deleted from (which is all of them here). It does go
        stale after a ``DELETE``, so callers needing a guaranteed count use
        :meth:`count_rows` — the UI has always rendered this figure as "~N".
        """
        self._ensure_connected()

        with self._lock:
            assert self._conn is not None
            table_rows = self._conn.execute(
                "SELECT table_name, estimated_size FROM duckdb_tables() "
                "WHERE database_name = current_database() AND schema_name = 'main' "
                "AND NOT internal"
            ).fetchall()
            view_rows = self._conn.execute(
                "SELECT view_name FROM duckdb_views() "
                "WHERE database_name = current_database() AND schema_name = 'main' "
                "AND NOT internal"
            ).fetchall()
            column_rows = self._conn.execute(
                "SELECT table_name, column_name, data_type, is_nullable FROM duckdb_columns() "
                "WHERE database_name = current_database() AND schema_name = 'main' "
                "AND NOT internal "
                "ORDER BY table_name, column_index"
            ).fetchall()

        columns_by_object: dict[str, list[ColumnDetail]] = {}
        for object_name, column_name, data_type, is_nullable in column_rows:
            columns_by_object.setdefault(object_name, []).append(
                ColumnDetail(name=column_name, dtype=data_type, nullable=bool(is_nullable))
            )

        # A NULL/negative estimate would trip TableMetadata's ge=0; clamp rather
        # than 500 the whole Home page over a catalog oddity.
        row_counts: dict[str, int] = {
            name: max(int(size or 0), 0) for name, size in table_rows
        }
        # The two catalog queries already say which is which — no extra query needed.
        kinds: dict[str, str] = {name: "TABLE" for name, _ in table_rows}
        # Views report 0, as they always have — counting one means running it. The
        # object_type below is what stops that 0 reading as "this month is empty".
        for (view_name,) in view_rows:
            row_counts.setdefault(view_name, 0)
            kinds[view_name] = "VIEW"

        return [
            TableMetadata(
                table_name=name,
                columns=columns_by_object.get(name, []),
                row_count=row_counts[name],
                object_type=kinds.get(name, "TABLE"),
            )
            for name in sorted(row_counts)
        ]

    def count_rows(self, table_name: str) -> int:
        """Exact ``COUNT(*)`` for one object, for when the estimate is not enough.

        Deliberately per-object and opt-in: this is the scan that made
        :meth:`list_tables` O(tables x rows).

        The count runs on a borrowed cursor, not under ``_lock``. For a view this
        binds a whole month's parquet glob, and holding the service-wide lock for
        that would block every other endpoint for its duration — the exact problem
        :meth:`_borrowed_cursor` exists to solve.

        Raises:
            ValueError: the object does not exist.
            SourceUnavailableError: it is a view whose parquet could not be read.
        """
        self._ensure_connected()

        with self._lock:
            if table_name not in self._fetch_table_names():
                raise ValueError(f"Table '{table_name}' does not exist.")

        with self._borrowed_cursor() as cursor:
            try:
                result = cursor.execute(
                    f"SELECT COUNT(*) FROM {self._quote_identifier(table_name)}"
                ).fetchone()
            except duckdb.Error as exc:
                # A view whose folder moved or drive re-lettered fails here and only
                # here — the catalog still answers, so the object looks healthy.
                raise SourceUnavailableError(str(exc)) from exc
        return int(result[0]) if result else 0

    def get_columns(self, table_name: str) -> list[ColumnDetail]:
        self._ensure_connected()

        with self._lock:
            existing = self._fetch_table_names()
            if table_name not in existing:
                raise ValueError(f"Table '{table_name}' does not exist.")
            return self._fetch_columns_unlocked(table_name)

    def drop_object(self, object_name: str) -> str:
        self._ensure_connected()

        cleaned = (object_name or "").strip()
        if not cleaned:
            raise ValueError("object_name cannot be empty.")

        with self._lock:
            assert self._conn is not None
            existing = self._conn.execute(
                "SELECT table_name, table_type FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND lower(table_name) = lower(?) LIMIT 1",
                [cleaned],
            ).fetchone()
            if not existing:
                raise ValueError(f"Local object '{cleaned}' does not exist.")

            actual_name, object_type = existing[0], existing[1]
            object_sql = self._quote_identifier(actual_name)
            if object_type == "VIEW":
                self._conn.execute(f"DROP VIEW {object_sql}")
            else:
                self._conn.execute(f"DROP TABLE {object_sql}")

            return object_type

    def execute(self, sql: str, params: Optional[list[Any]] = None) -> tuple[list[str], list[list[Any]], int]:
        self._ensure_connected()

        with self._borrowed_cursor() as cursor:
            result = cursor.execute(sql, params) if params else cursor.execute(sql)
            columns = [desc[0] for desc in result.description] if result.description else []
            rows = result.fetchall()
            return columns, [list(row) for row in rows], len(rows)

    def export_to_csv(
        self,
        sql: str,
        output_path: str,
        params: Optional[list[Any]] = None,
    ) -> int:
        """Execute *sql* and write the result directly to *output_path* as CSV.

        Uses DuckDB's native ``COPY … TO`` command which streams rows from the
        C++ execution engine directly to disk.  This avoids loading all rows into
        Python memory and avoids JSON serialisation, making it suitable for result
        sets with tens of millions of rows.

        Args:
            sql:         A ``SELECT`` statement (no LIMIT required — caller controls that).
            output_path: Absolute path for the output ``.csv`` file.
            params:      Optional positional parameters for the query.

        Returns:
            Number of rows written (from DuckDB's COPY result).

        Raises:
            RuntimeError:  If the database is not connected.
            ValueError:    If *output_path* resolves outside expected bounds.
        """
        self._ensure_connected()

        from pathlib import Path as _Path  # local import to avoid circular at module level
        import os as _os

        resolved_out = _Path(output_path).expanduser().resolve()
        resolved_out.parent.mkdir(parents=True, exist_ok=True)

        # Escape the output path for embedding in SQL string literal
        path_str = str(resolved_out).replace("\\", "/")
        path_sql_lit = "'" + path_str.replace("'", "''") + "'"

        copy_sql = (
            f"COPY ({sql}) TO {path_sql_lit} "
            f"(HEADER true, DELIMITER ',', QUOTE '\"', FORCE_QUOTE *)"
        )
        # A multi-million-row COPY runs on its own cursor, so it no longer blocks
        # every other endpoint for its duration. (The parameterised branch used to
        # execute *sql* in full first and throw the result away before the COPY.)
        with self._borrowed_cursor() as cursor:
            result_row = (
                cursor.execute(copy_sql, params) if params else cursor.execute(copy_sql)
            ).fetchone()

        rows_written = int(result_row[0]) if result_row else 0
        return rows_written

    def create_object_from_file(self, payload: FileObjectRequest) -> TableMetadata:
        self._ensure_connected()
        object_name = payload.object_name.strip()
        if not VALID_OBJECT_NAME.fullmatch(object_name):
            raise ValueError(
                "Object name must start with a letter/underscore and contain only letters, numbers, and underscores."
            )

        path_obj = self._normalize_user_path(payload.file_path)
        source_path = path_obj.resolve() if path_obj.is_absolute() else (Path.cwd() / path_obj).resolve()
        if not source_path.exists() or not source_path.is_file():
            raise ValueError(f"Source file does not exist: {source_path}")

        extension = source_path.suffix.lower()
        if extension == ".xls":
            raise ValueError("DuckDB supports .xlsx files, but not legacy .xls files. Save as .xlsx or CSV first.")
        if extension not in SUPPORTED_SOURCE_EXTENSIONS:
            raise ValueError("Supported file types are .csv, .tsv, and .xlsx.")

        object_type = payload.object_type.upper()
        with self._lock:
            assert self._conn is not None
            existing = set(self._fetch_table_names())
            if object_name in existing and not payload.replace:
                raise ValueError(f"Local object '{object_name}' already exists. Enable Replace to overwrite it.")

            relation_sql = self._build_file_relation_sql(
                source_path=source_path,
                header=payload.header,
                sheet_name=payload.sheet_name,
            )
            if payload.header_names:
                relation_sql = self._build_projected_relation_sql(relation_sql, payload.header_names)
            object_sql = self._quote_identifier(object_name)
            if payload.replace:
                self._drop_existing_object_unlocked(object_name)
            self._conn.execute(f"CREATE {object_type} {object_sql} AS SELECT * FROM {relation_sql}")

            columns = self._fetch_columns_unlocked(object_name)
            row_count = self._fetch_row_count_unlocked(object_name) if object_type == "TABLE" else 0
            return TableMetadata(
                table_name=object_name,
                columns=columns,
                row_count=row_count,
                object_type=object_type,
            )

    def preview_file_source(self, payload: FilePreviewRequest) -> FilePreviewResponse:
        self._ensure_connected()
        path_obj = self._normalize_user_path(payload.file_path)
        source_path = path_obj.resolve() if path_obj.is_absolute() else (Path.cwd() / path_obj).resolve()
        if not source_path.exists() or not source_path.is_file():
            raise ValueError(f"Source file does not exist: {source_path}")

        extension = source_path.suffix.lower()
        if extension == ".xls":
            raise ValueError("DuckDB supports .xlsx files, but not legacy .xls files. Save as .xlsx or CSV first.")
        if extension not in SUPPORTED_SOURCE_EXTENSIONS:
            raise ValueError("Supported file types are .csv, .tsv, and .xlsx.")

        relation_sql = self._build_file_relation_sql(
            source_path=source_path,
            header=payload.header,
            sheet_name=payload.sheet_name,
        )

        with self._lock:
            assert self._conn is not None
            result = self._conn.execute(f"SELECT * FROM {relation_sql} LIMIT {payload.limit_rows}")
            columns = [desc[0] for desc in (result.description or [])]
            rows = [list(row) for row in result.fetchall()]
            return FilePreviewResponse(columns=columns, rows=rows)

    def _ensure_connected(self) -> None:
        if self._conn is None:
            raise RuntimeError("No database connected. Call connect() first.")

    @contextmanager
    def _borrowed_cursor(self) -> Iterator[duckdb.DuckDBPyConnection]:
        """Lend a cursor for one statement, holding ``_lock`` only to take it.

        ``execute`` and ``export_to_csv`` used to hold the service-wide lock for
        the whole statement, so a Home page load queued behind a 10-minute
        export. A DuckDB cursor is an independent connection onto the same
        database, so the statement can run unlocked — and the in-flight count
        stops :meth:`disconnect` closing the parent connection underneath it.
        """
        with self._lock:
            if self._conn is None:
                raise RuntimeError("No database connected. Call connect() first.")
            cursor = self._conn.cursor()
            self._in_flight += 1
        try:
            yield cursor
        finally:
            with self._lock:
                try:
                    cursor.close()
                except Exception:
                    pass
                self._in_flight -= 1
                if self._in_flight == 0:
                    self._idle.notify_all()

    def _drain_and_close_unlocked(self) -> None:
        """Wait for borrowed cursors to finish, then close *that* connection.

        Caller must hold ``_lock``. ``Condition.wait`` releases it while waiting.

        The connection is captured before the wait and only closed if it is still
        the live one. ``wait()`` hands the lock to whoever else wants it, so a
        materialise — which disconnects once per demote plus once for the promote —
        can have a queued disconnect wake up after a later ``connect()`` has already
        installed a fresh connection and reported success. Closing whatever happens
        to be there at wake-up would take the app offline behind its own back.
        """
        target = self._conn
        while self._in_flight:
            self._idle.wait()
        if target is None or self._conn is not target:
            # Someone else replaced or already closed it while we waited; it is
            # theirs to manage now.
            return
        try:
            target.close()
        except Exception:
            pass
        self._conn = None

    def _quote_identifier(self, identifier: str) -> str:
        return f'"{identifier.replace(chr(34), chr(34) * 2)}"'

    def _sql_string_literal(self, value: str) -> str:
        return f"'{value.replace(chr(39), chr(39) * 2)}'"

    def _fetch_table_entries_unlocked(self) -> list[tuple[str, str]]:
        assert self._conn is not None
        result = self._conn.execute(
            "SELECT table_name, table_type FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_type IN ('BASE TABLE', 'VIEW') "
            "ORDER BY table_name"
        )
        return [(row[0], row[1]) for row in result.fetchall()]

    def _fetch_table_names(self) -> list[str]:
        return [name for name, _ in self._fetch_table_entries_unlocked()]

    def _drop_existing_object_unlocked(self, object_name: str) -> None:
        assert self._conn is not None
        existing = self._conn.execute(
            "SELECT table_type FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND lower(table_name) = lower(?) LIMIT 1",
            [object_name.strip()],
        ).fetchone()
        if not existing:
            return

        object_sql = self._quote_identifier(object_name)
        if existing[0] == "VIEW":
            self._conn.execute(f"DROP VIEW {object_sql}")
        else:
            self._conn.execute(f"DROP TABLE {object_sql}")

    def _load_excel_extension_unlocked(self) -> None:
        assert self._conn is not None
        try:
            self._conn.execute("LOAD excel")
        except duckdb.Error:
            try:
                self._conn.execute("INSTALL excel")
                self._conn.execute("LOAD excel")
            except duckdb.Error as exc:
                raise RuntimeError(
                    "DuckDB could not load the excel extension required for .xlsx files. "
                    "Check internet access for extension install, or use CSV."
                ) from exc

    def _build_file_relation_sql(self, source_path: Path, header: bool, sheet_name: str | None) -> str:
        extension = source_path.suffix.lower()
        path_sql = self._sql_string_literal(str(source_path))
        header_sql = "true" if header else "false"

        if extension == ".csv":
            return f"read_csv_auto({path_sql}, header = {header_sql})"
        if extension == ".tsv":
            return f"read_csv_auto({path_sql}, delim = '\t', header = {header_sql})"
        if extension == ".xlsx":
            self._load_excel_extension_unlocked()
            options = [f"header = {header_sql}"]
            if sheet_name and sheet_name.strip():
                options.append(f"sheet = {self._sql_string_literal(sheet_name.strip())}")
            return f"read_xlsx({path_sql}, {', '.join(options)})"

        raise ValueError("Supported file types are .csv, .tsv, and .xlsx.")

    def _build_projected_relation_sql(self, relation_sql: str, header_names: list[str]) -> str:
        assert self._conn is not None
        preview = self._conn.execute(f"SELECT * FROM {relation_sql} LIMIT 0")
        source_columns = [desc[0] for desc in (preview.description or [])]
        normalized_headers = [name.strip() for name in header_names if name.strip()]
        if len(normalized_headers) != len(source_columns):
            raise ValueError(
                f"Custom header count ({len(normalized_headers)}) must match source columns ({len(source_columns)})."
            )

        aliases = [
            f'src.{self._quote_identifier(source_name)} AS {self._quote_identifier(target_name)}'
            for source_name, target_name in zip(source_columns, normalized_headers)
        ]
        return f"SELECT {', '.join(aliases)} FROM ({relation_sql}) src"

    def _fetch_columns_unlocked(self, table_name: str) -> list[ColumnDetail]:
        assert self._conn is not None
        result = self._conn.execute(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema = 'main' AND table_name = ? "
            "ORDER BY ordinal_position",
            [table_name],
        )
        return [ColumnDetail(name=row[0], dtype=row[1], nullable=(row[2] == "YES")) for row in result.fetchall()]

    def _fetch_row_count_unlocked(self, table_name: str) -> int:
        assert self._conn is not None
        result = self._conn.execute(f"SELECT COUNT(*) FROM {self._quote_identifier(table_name)}")
        count = result.fetchone()
        return count[0] if count else 0
