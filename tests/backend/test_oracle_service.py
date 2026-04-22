"""
test_oracle_service.py â€” Unit tests for Oracle read-only enforcement.
"""

import pytest

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
