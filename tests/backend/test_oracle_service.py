"""
test_oracle_service.py â€” Unit tests for Oracle read-only enforcement.
"""

import pytest

from backend.models.schema import ColumnDetail
from backend.services.oracle_service import OracleService


def test_oracle_service_accepts_select_queries() -> None:
    OracleService.ensure_read_only_sql("SELECT * FROM CUSTOMER")
    OracleService.ensure_read_only_sql("WITH cte AS (SELECT 1 AS id FROM dual) SELECT * FROM cte")


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM CUSTOMER",
        "UPDATE CUSTOMER SET name = 'x'",
        "SELECT * FROM CUSTOMER FOR UPDATE",
        "SELECT * FROM CUSTOMER; DELETE FROM CUSTOMER",
    ],
)
def test_oracle_service_rejects_non_read_only_sql(sql: str) -> None:
    with pytest.raises(ValueError):
        OracleService.ensure_read_only_sql(sql)


class _FakeCursor:
    """Answers the all_objects lookup with a fixed set of existing objects."""

    def __init__(self, existing: set[tuple[str, str]]) -> None:
        self._existing = existing
        self._rows: list[tuple[str, str]] = []

    def execute(self, sql: str, params: list[str]) -> None:
        assert "ALL_OBJECTS" in sql.upper()
        self._rows = [(owner, name) for owner, name in self._existing if name in params]

    def fetchall(self) -> list[tuple[str, str]]:
        return self._rows


# ── ORA-00942 names nothing, so a five-table DISCOM union is opaque ────────────

MONTH_UNION_SQL = (
    'SELECT t0."DISCOM" FROM MERCADOS.CM_master_data_jul_2026_DVVNL t0 '
    'UNION ALL SELECT t0."DISCOM" FROM MERCADOS.CM_master_data_jul_2026_KESCO t0'
)


def test_referenced_objects_resolves_names_the_way_oracle_does() -> None:
    found = OracleService._referenced_objects(MONTH_UNION_SQL)

    # Unquoted identifiers fold to upper case, which is how all_objects stores them.
    assert found == [
        ("MERCADOS", "CM_MASTER_DATA_JUL_2026_DVVNL"),
        ("MERCADOS", "CM_MASTER_DATA_JUL_2026_KESCO"),
    ]


def test_a_quoted_identifier_keeps_its_case() -> None:
    found = OracleService._referenced_objects('SELECT 1 FROM "MixedCase"."Tbl"')

    assert found == [("MixedCase", "Tbl")]


def test_missing_objects_are_named_in_the_message() -> None:
    """The whole point: say which month did not load, not just that something failed."""
    cursor = _FakeCursor({("MERCADOS", "CM_MASTER_DATA_JUL_2026_DVVNL")})

    described = OracleService._describe_missing_objects(cursor, MONTH_UNION_SQL)

    assert described is not None
    assert "CM_MASTER_DATA_JUL_2026_KESCO" in described
    assert "CM_MASTER_DATA_JUL_2026_DVVNL" not in described, "the one that exists is noise"
    assert "not been loaded" in described


def test_nothing_is_claimed_missing_when_every_object_exists() -> None:
    cursor = _FakeCursor(
        {
            ("MERCADOS", "CM_MASTER_DATA_JUL_2026_DVVNL"),
            ("MERCADOS", "CM_MASTER_DATA_JUL_2026_KESCO"),
        }
    )

    assert OracleService._describe_missing_objects(cursor, MONTH_UNION_SQL) is None


def test_a_failed_lookup_defers_to_oracles_own_error() -> None:
    """Replacing a real error with a worse guess would be a regression."""

    class Broken:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError("no cursor")

    assert OracleService._describe_missing_objects(Broken(), MONTH_UNION_SQL) is None


def test_a_synonym_in_another_schema_counts_as_existing() -> None:
    """all_objects covers synonyms, so an unqualified name resolved elsewhere is fine."""
    cursor = _FakeCursor({("PUBLIC", "CM_MASTER_DATA_JUL_2026_KESCO"),
                          ("PUBLIC", "CM_MASTER_DATA_JUL_2026_DVVNL")})

    assert OracleService._describe_missing_objects(cursor, MONTH_UNION_SQL) is None


def test_get_columns_accepts_schema_qualified_name_when_list_is_unqualified() -> None:
    service = OracleService()
    service._conn = object()
    service._schema_name = "MERCADOS"

    expected = [ColumnDetail(name="ACCT_ID", dtype="VARCHAR2", nullable=True)]

    def fake_fetch_columns(table_name: str) -> list[ColumnDetail]:
        assert table_name == "MERCADOS.CM_master_data_apr_2026_DVVNL"
        return expected

    service._fetch_columns_unlocked = fake_fetch_columns  # type: ignore[method-assign]

    result = service.get_columns("MERCADOS.CM_master_data_apr_2026_DVVNL")

    assert result == expected


def test_oracle_execute_sanitizes_wrapped_sql_before_execution() -> None:
    service = OracleService()

    class FakeCursor:
        def __init__(self) -> None:
            self.description = [("DISCOM",), ("COUNT",)]

        def execute(self, sql: str, params=None) -> None:
            if "`" in sql or "\u00A0" in sql:
                raise RuntimeError("ORA-00911: invalid character")
            assert "`" not in sql
            assert "\u00A0" not in sql
            assert not sql.rstrip().endswith(";")

        def fetchall(self):
            return [("DVVNL", 1)]

        def close(self) -> None:
            return None

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

    service._conn = FakeConnection()
    service._schema_name = "MERCADOS"

    columns, rows, total = service.execute("\"SELECT * FROM DUAL\\n\u00A0`\"")

    assert columns == ["DISCOM", "COUNT"]
    assert rows == [["DVVNL", 1]]
    assert total == 1


def test_oracle_sanitize_sql_unwraps_quoted_and_escaped_text() -> None:
    sanitized = OracleService._sanitize_sql_for_oracle("\"SELECT * FROM dual\\nWHERE x = \\\"Y\\\";\"")
    assert sanitized == 'SELECT * FROM dual\nWHERE x = "Y"'


def test_oracle_sanitize_sql_normalizes_fullwidth_and_zero_width_chars() -> None:
    raw_sql = "SELECT\u200B * FROM dual\uff1b"
    sanitized = OracleService._sanitize_sql_for_oracle(raw_sql)
    assert sanitized.replace("  ", " ") == "SELECT * FROM dual"


def test_oracle_ascii_retry_sql_removes_non_ascii_chars() -> None:
    retry_sql = OracleService._sanitize_ascii_retry_sql("SELECT * FROM dual\u00A0;")
    assert retry_sql == "SELECT * FROM dual"


def test_oracle_diagnose_invalid_sql_chars_reports_control_codes() -> None:
    diagnostic = OracleService._diagnose_invalid_sql_chars("SELECT\x00 * FROM dual")
    assert "U+0000" in diagnostic
