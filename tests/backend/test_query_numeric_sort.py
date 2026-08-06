"""Two defects in the builder's hot path, both invisible in the response shape.

1. TOTAL_AMT and LOAD_KW are stored VARCHAR (they are absent from MERCADOS_SCHEMA,
   and pipeline_sql keeps them as normalised strings deliberately). ORDER BY passed
   the column through uncast, so "top N by amount" sorted '900' above '10000' and
   returned the wrong rows with no error.
2. /api/query ran an unbounded COUNT alongside every data query, so each
   interaction scanned the month twice even when the first page was the whole
   answer.
"""

from pathlib import Path
from uuid import uuid4

import duckdb
import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.services.duckdb_service import DuckDBService


def _make_db(tmp_path: Path) -> Path:
    """A master-shaped table with TOTAL_AMT as VARCHAR, as the pipeline writes it.

    A unique filename per call: pytest truncates long parametrised test ids, so two
    cases of the same test can land in one tmp_path — and the service singleton
    still holds the previous case's file open.
    """
    db_path = tmp_path / f"sort_{uuid4().hex[:8]}.duckdb"
    with duckdb.connect(str(db_path)) as conn:
        conn.execute(
            "CREATE TABLE consumers AS SELECT * FROM (VALUES "
            "('0000000001', '900',   '5'),"
            "('0000000002', '10000', '40'),"
            "('0000000003', '2500',  '100')"
            ") t(ACCT_ID, TOTAL_AMT, LOAD_KW)"
        )
    return db_path


def _connect(client: TestClient, db_path: Path) -> None:
    response = client.post("/api/duckdb/connect", json={"db_path": str(db_path)})
    assert response.status_code == 200, response.text


def _builder_payload(**overrides) -> dict:
    payload = {
        "execution_mode": "builder",
        "engine": "duckdb",
        "table": "consumers",
        "select": ["ACCT_ID", "TOTAL_AMT"],
        "filters": [],
        "sort": [],
        "limit_rows": 100,
        "offset": 0,
        "mode": "LIST",
        "group_by": [],
        "aggregates": [],
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    ("column", "direction", "expected"),
    [
        ("TOTAL_AMT", "DESC", ["10000", "2500", "900"]),
        ("TOTAL_AMT", "ASC", ["900", "2500", "10000"]),
    ],
)
def test_sorting_by_amount_returns_numeric_order(
    tmp_path: Path, column: str, direction: str, expected: list[str]
) -> None:
    client = TestClient(app)
    _connect(client, _make_db(tmp_path))

    response = client.post(
        "/api/query",
        json=_builder_payload(
            select=["ACCT_ID", column],
            sort=[{"column": column, "direction": direction}],
        ),
    )

    assert response.status_code == 200, response.text
    assert [row[1] for row in response.json()["rows"]] == expected


def test_sorting_by_load_kw_returns_numeric_order(tmp_path: Path) -> None:
    client = TestClient(app)
    _connect(client, _make_db(tmp_path))

    response = client.post(
        "/api/query",
        json=_builder_payload(
            select=["ACCT_ID", "LOAD_KW"],
            sort=[{"column": "LOAD_KW", "direction": "DESC"}],
        ),
    )

    assert response.status_code == 200, response.text
    # Lexicographically '5' sorts above '40' and '100'.
    assert [row[1] for row in response.json()["rows"]] == ["100", "40", "5"]


def test_sorting_by_a_text_column_stays_lexicographic(tmp_path: Path) -> None:
    client = TestClient(app)
    _connect(client, _make_db(tmp_path))

    response = client.post(
        "/api/query",
        json=_builder_payload(sort=[{"column": "ACCT_ID", "direction": "ASC"}]),
    )

    assert response.status_code == 200, response.text
    assert [row[0] for row in response.json()["rows"]] == [
        "0000000001",
        "0000000002",
        "0000000003",
    ]


# ── The redundant second scan ─────────────────────────────────────────────────


@pytest.fixture
def executed_sql(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every statement the service runs for one request."""
    seen: list[str] = []
    original = DuckDBService.execute

    def spy(self, sql, params=None):  # type: ignore[no-untyped-def]
        seen.append(sql)
        return original(self, sql, params)

    monkeypatch.setattr(DuckDBService, "execute", spy)
    return seen


def test_a_short_page_is_counted_without_a_second_query(
    tmp_path: Path, executed_sql: list[str]
) -> None:
    client = TestClient(app)
    _connect(client, _make_db(tmp_path))
    executed_sql.clear()

    response = client.post("/api/query", json=_builder_payload(limit_rows=100))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 3, "a short page is already the whole answer"
    assert body["truncated"] is False
    assert len(executed_sql) == 1, f"expected one scan, got {len(executed_sql)}: {executed_sql}"
    assert not any("count(" in sql.lower() for sql in executed_sql)


def test_a_full_page_still_gets_an_exact_total(
    tmp_path: Path, executed_sql: list[str]
) -> None:
    """A full page can be hiding more rows, so the COUNT is still required."""
    client = TestClient(app)
    _connect(client, _make_db(tmp_path))
    executed_sql.clear()

    response = client.post("/api/query", json=_builder_payload(limit_rows=2))

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["rows"]) == 2
    assert body["total"] == 3, "the total must count beyond the page"
    assert body["truncated"] is True
    assert len(executed_sql) == 2


def test_total_accounts_for_the_offset_on_a_short_page(
    tmp_path: Path, executed_sql: list[str]
) -> None:
    """`total` means rows before LIMIT/OFFSET, so the skipped rows still count."""
    client = TestClient(app)
    _connect(client, _make_db(tmp_path))
    executed_sql.clear()

    response = client.post("/api/query", json=_builder_payload(limit_rows=100, offset=2))

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["rows"]) == 1
    assert body["total"] == 3
    assert len(executed_sql) == 1
