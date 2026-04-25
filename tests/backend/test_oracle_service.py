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
