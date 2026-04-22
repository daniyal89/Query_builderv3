"""
oracle_service.py â€” Manages Marcadose Oracle connection lifecycle and read-only querying.
"""

from __future__ import annotations

import importlib
import re
import threading
from typing import Any, Optional

from backend.models.connection import OracleConnectionRequest
from backend.models.schema import ColumnDetail, TableMetadata


READ_ONLY_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|ALTER|DROP|CREATE|TRUNCATE|GRANT|REVOKE|COMMENT|RENAME|"
    r"COMMIT|ROLLBACK|SAVEPOINT|CALL|EXEC|EXECUTE|BEGIN|DECLARE|LOCK\s+TABLE)\b",
    re.IGNORECASE,
)
FOR_UPDATE_PATTERN = re.compile(r"\bFOR\s+UPDATE\b", re.IGNORECASE)
LEADING_COMMENT_PATTERN = re.compile(r"^\s*(--.*?$|/\*.*?\*/\s*)*", re.DOTALL | re.MULTILINE)


class OracleService:
    """Singleton service managing a single Oracle connection in Thin mode."""

    def __init__(self) -> None:
        self._conn: Any | None = None
        self._lock = threading.Lock()
        self._schema_name: str = ""
        self._connection_label: str = ""

    @property
    def is_connected(self) -> bool:
        return self._conn is not None

    @property
    def schema_name(self) -> str:
        return self._schema_name

    def connect(self, payload: OracleConnectionRequest) -> int:
        oracledb = self._load_driver()
        params = oracledb.ConnectParams(host=payload.host.strip(), port=payload.port, sid=payload.sid.strip())

        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
            try:
                self._conn = oracledb.connect(
                    user=payload.username.strip(),
                    password=payload.password,
                    params=params,
                )
            except Exception as exc:
                self._conn = None
                self._schema_name = ""
                self._connection_label = ""
                raise RuntimeError(f"Failed to connect to Oracle: {exc}") from exc

            self._schema_name = payload.username.strip().upper()
            self._connection_label = f"{payload.host.strip()}:{payload.port}/{payload.sid.strip()}"
            return len(self._fetch_object_names_unlocked())

    def disconnect(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
            self._conn = None
            self._schema_name = ""
            self._connection_label = ""

    def list_tables(self) -> list[TableMetadata]:
        self._ensure_connected()
        with self._lock:
            object_names = self._fetch_object_names_unlocked()
            results: list[TableMetadata] = []
            for name in object_names:
                results.append(
                    TableMetadata(
                        table_name=name,
                        columns=self._fetch_columns_unlocked(name),
                        row_count=0,
                    )
                )
            return results

    def get_columns(self, table_name: str) -> list[ColumnDetail]:
        self._ensure_connected()
        normalized = table_name.strip().upper()
        with self._lock:
            existing = self._fetch_object_names_unlocked()
            if normalized not in existing:
                raise ValueError(f"Table or view '{table_name}' does not exist in schema '{self._schema_name}'.")
            return self._fetch_columns_unlocked(normalized)

    def execute(self, sql: str, params: Optional[list[Any]] = None) -> tuple[list[str], list[list[Any]], int]:
        self._ensure_connected()
        self.ensure_read_only_sql(sql)

        with self._lock:
            assert self._conn is not None
            cursor = self._conn.cursor()
            try:
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                columns = [desc[0] for desc in (cursor.description or [])]
                rows = cursor.fetchall()
                return columns, [list(row) for row in rows], len(rows)
            finally:
                cursor.close()

    @staticmethod
    def ensure_read_only_sql(sql: str) -> None:
        stripped = sql.strip()
        if not stripped:
            raise ValueError("SQL cannot be empty.")

        normalized = LEADING_COMMENT_PATTERN.sub("", stripped).strip()
        normalized = normalized[:-1].rstrip() if normalized.endswith(";") else normalized
        if ";" in normalized:
            raise ValueError("Only a single read-only statement can be executed against Marcadose.")

        leading_keyword = normalized.split(None, 1)[0].upper() if normalized else ""
        if leading_keyword not in {"SELECT", "WITH"}:
            raise ValueError("Marcadose is read-only. Only SELECT queries are allowed.")

        if READ_ONLY_KEYWORDS.search(normalized) or FOR_UPDATE_PATTERN.search(normalized):
            raise ValueError("Marcadose is read-only. Write or locking statements are not allowed.")

    def _ensure_connected(self) -> None:
        if self._conn is None:
            raise RuntimeError("No Marcadose database connected. Use POST /api/oracle/connect first.")

    def _load_driver(self) -> Any:
        try:
            return importlib.import_module("oracledb")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "python-oracledb is not installed. Run 'pip install -r requirements.txt' to enable Marcadose support."
            ) from exc

    def _fetch_object_names_unlocked(self) -> list[str]:
        assert self._conn is not None
        cursor = self._conn.cursor()
        try:
            cursor.execute(
                """
                SELECT object_name
                FROM user_objects
                WHERE object_type IN ('TABLE', 'VIEW')
                ORDER BY object_name
                """
            )
            return [row[0] for row in cursor.fetchall()]
        finally:
            cursor.close()

    def _fetch_columns_unlocked(self, table_name: str) -> list[ColumnDetail]:
        assert self._conn is not None
        cursor = self._conn.cursor()
        try:
            cursor.execute(
                """
                SELECT column_name, data_type, nullable
                FROM user_tab_columns
                WHERE table_name = :1
                ORDER BY column_id
                """,
                [table_name],
            )
            return [
                ColumnDetail(name=row[0], dtype=row[1], nullable=(row[2] == "Y"))
                for row in cursor.fetchall()
            ]
        finally:
            cursor.close()
