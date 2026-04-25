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
from backend.services.sample_snapshot_service import SampleSnapshotService


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
            try:
                object_names = self._fetch_object_names_unlocked()
                SampleSnapshotService.capture_oracle_once(
                    self._conn,
                    self._schema_name,
                    self._connection_label,
                    object_names,
                )
            except Exception:
                # Snapshot capture is non-blocking and must not block Oracle connect.
                pass
            return 0

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
            return [
                TableMetadata(
                    table_name=name,
                    columns=[],
                    row_count=0,
                )
                for name in object_names
            ]

    def get_columns(self, table_name: str) -> list[ColumnDetail]:
        self._ensure_connected()
        with self._lock:
            return self._fetch_columns_unlocked(table_name)

    def execute(self, sql: str, params: Optional[list[Any]] = None) -> tuple[list[str], list[list[Any]], int]:
        self._ensure_connected()
        self.ensure_read_only_sql(sql)

        with self._lock:
            assert self._conn is not None
            cursor = self._conn.cursor()
            try:
                try:
                    if params:
                        cursor.execute(sql, params)
                    else:
                        cursor.execute(sql)
                except Exception as exc:
                    if not self._is_invalid_character_error(exc):
                        raise

                    cleaned_sql = self._sanitize_sql_for_oracle(sql)
                    if cleaned_sql == sql:
                        raise

                    if params:
                        cursor.execute(cleaned_sql, params)
                    else:
                        cursor.execute(cleaned_sql)
                columns = [desc[0] for desc in (cursor.description or [])]
                rows = cursor.fetchall()
                return columns, [list(row) for row in rows], len(rows)
            finally:
                cursor.close()

    @staticmethod
    def _is_invalid_character_error(exc: Exception) -> bool:
        return "ORA-00911" in str(exc).upper()

    @staticmethod
    def _sanitize_sql_for_oracle(sql: str) -> str:
        sanitized = sql.replace("\u00A0", " ").replace("`", "").strip()
        if sanitized.endswith(";"):
            sanitized = sanitized[:-1].rstrip()
        return sanitized

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
                SELECT object_label
                FROM (
                    SELECT object_name AS object_label, 0 AS sort_group
                    FROM user_objects
                    WHERE object_type IN ('TABLE', 'VIEW')

                    UNION

                    SELECT owner || '.' || object_name AS object_label, 1 AS sort_group
                    FROM all_objects
                    WHERE object_type IN ('TABLE', 'VIEW')
                      AND owner <> :1
                      AND owner NOT IN (
                          'SYS', 'SYSTEM', 'XDB', 'CTXSYS', 'MDSYS', 'ORDSYS', 'WMSYS', 'OUTLN',
                          'DBSNMP', 'OLAPSYS', 'LBACSYS', 'DVSYS', 'AUDSYS', 'GSMADMIN_INTERNAL'
                      )
                      AND owner NOT LIKE 'APEX_%'
                      AND owner NOT LIKE 'FLOWS_%'

                    UNION

                    SELECT synonym_name AS object_label, 2 AS sort_group
                    FROM user_synonyms syn
                    WHERE EXISTS (
                        SELECT 1
                        FROM all_objects obj
                        WHERE obj.owner = syn.table_owner
                          AND obj.object_name = syn.table_name
                          AND obj.object_type IN ('TABLE', 'VIEW')
                    )

                    UNION

                    SELECT synonym_name AS object_label, 3 AS sort_group
                    FROM all_synonyms syn
                    WHERE syn.owner = 'PUBLIC'
                      AND syn.table_owner NOT IN (
                          'SYS', 'SYSTEM', 'XDB', 'CTXSYS', 'MDSYS', 'ORDSYS', 'WMSYS', 'OUTLN',
                          'DBSNMP', 'OLAPSYS', 'LBACSYS', 'DVSYS', 'AUDSYS', 'GSMADMIN_INTERNAL'
                      )
                      AND syn.table_owner NOT LIKE 'APEX_%'
                      AND syn.table_owner NOT LIKE 'FLOWS_%'
                      AND EXISTS (
                        SELECT 1
                        FROM all_objects obj
                        WHERE obj.owner = syn.table_owner
                          AND obj.object_name = syn.table_name
                          AND obj.object_type IN ('TABLE', 'VIEW')
                      )
                )
                GROUP BY object_label
                ORDER BY MIN(sort_group), object_label
                """,
                [self._schema_name],
            )
            return [row[0] for row in cursor.fetchall()]
        finally:
            cursor.close()

    def _resolve_object_unlocked(self, table_name: str) -> tuple[str, str]:
        assert self._conn is not None
        normalized = table_name.strip().upper()
        cursor = self._conn.cursor()
        try:
            if "." in normalized:
                owner, object_name = normalized.split(".", 1)
                cursor.execute(
                    """
                    SELECT owner, object_name
                    FROM all_objects
                    WHERE owner = :1
                      AND object_name = :2
                      AND object_type IN ('TABLE', 'VIEW')
                    """,
                    [owner, object_name],
                )
                row = cursor.fetchone()
                if row:
                    return row[0], row[1]

            cursor.execute(
                """
                SELECT owner, object_name
                FROM all_objects
                WHERE owner = :1
                  AND object_name = :2
                  AND object_type IN ('TABLE', 'VIEW')
                """,
                [self._schema_name, normalized],
            )
            row = cursor.fetchone()
            if row:
                return row[0], row[1]

            cursor.execute(
                """
                SELECT table_owner, table_name
                FROM user_synonyms
                WHERE synonym_name = :1
                """,
                [normalized],
            )
            row = cursor.fetchone()
            if row:
                return row[0], row[1]

            cursor.execute(
                """
                SELECT table_owner, table_name
                FROM all_synonyms
                WHERE owner = 'PUBLIC'
                  AND synonym_name = :1
                """,
                [normalized],
            )
            row = cursor.fetchone()
            if row:
                return row[0], row[1]
        finally:
            cursor.close()

        raise ValueError(f"Table, view, or synonym '{table_name}' does not exist in schema '{self._schema_name}'.")

    def _fetch_columns_unlocked(self, table_name: str) -> list[ColumnDetail]:
        assert self._conn is not None
        owner, object_name = self._resolve_object_unlocked(table_name)
        cursor = self._conn.cursor()
        try:
            cursor.execute(
                """
                SELECT column_name, data_type, nullable
                FROM all_tab_columns
                WHERE owner = :1
                  AND table_name = :2
                ORDER BY column_id
                """,
                [owner, object_name],
            )
            return [
                ColumnDetail(name=row[0], dtype=row[1], nullable=(row[2] == "Y"))
                for row in cursor.fetchall()
            ]
        finally:
            cursor.close()
