"""
test_query_sql_workflow.py - Regression tests for Series 4 SQL preview/editor flows.
"""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.endpoints.query import _safe_utf8_hex
from backend.app import app
from backend.services.error_log_service import ErrorLogService


TEST_DB_PATH = Path(__file__).resolve().parents[2] / "test_data.duckdb"


def test_safe_utf8_hex_handles_unpaired_surrogates() -> None:
    malformed = "\ud800SELECT 1"
    value = _safe_utf8_hex(malformed)
    assert isinstance(value, str)
    assert value


def _connect_duckdb(client: TestClient) -> None:
    response = client.post("/api/duckdb/connect", json={"db_path": str(TEST_DB_PATH)})
    assert response.status_code == 200, response.text


def test_query_preview_returns_builder_sql_for_duckdb() -> None:
    client = TestClient(app)
    _connect_duckdb(client)

    response = client.post(
        "/api/query/preview",
        json={
            "execution_mode": "builder",
            "engine": "duckdb",
            "table": "employees",
            "select": ["id", "name"],
            "filters": [],
            "sort": [],
            "limit_rows": 5,
            "offset": 0,
            "mode": "LIST",
            "group_by": [],
            "aggregates": [],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source_mode"] == "builder"
    assert body["can_sync_builder"] is True
    assert body["sql"].startswith("/* AI_CONTEXT")
    assert "engine: duckdb" in body["sql"]
    assert "source_mode: builder" in body["sql"]
    assert 'SELECT t0."id", t0."name" FROM "employees" t0 LIMIT 5' in body["sql"]


def test_query_execution_runs_manual_sql_for_duckdb() -> None:
    client = TestClient(app)
    _connect_duckdb(client)

    response = client.post(
        "/api/query",
        json={
            "execution_mode": "sql",
            "engine": "duckdb",
            "table": "",
            "select": [],
            "filters": [],
            "sort": [],
            "limit_rows": 1000,
            "offset": 0,
            "mode": "LIST",
            "group_by": [],
            "aggregates": [],
            "sql": 'SELECT "id", "name" FROM "employees" ORDER BY "id" LIMIT 2',
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source_mode"] == "sql"
    assert body["executed_sql"] == 'SELECT "id", "name" FROM "employees" ORDER BY "id" LIMIT 2'
    assert body["columns"] == ["id", "name"]
    assert len(body["rows"]) == 2
    assert body["truncated"] is False


def test_query_execution_accepts_ai_helper_comment_wrapped_manual_sql_for_duckdb() -> None:
    client = TestClient(app)
    _connect_duckdb(client)

    response = client.post(
        "/api/query",
        json={
            "execution_mode": "sql",
            "engine": "duckdb",
            "table": "",
            "select": [],
            "filters": [],
            "sort": [],
            "limit_rows": 1000,
            "offset": 0,
            "mode": "LIST",
            "group_by": [],
            "aggregates": [],
            "sql": """/* AI_CONTEXT
engine: duckdb
source_mode: manual
limit_semantics: Uses LIMIT/OFFSET for pagination.
*/
SELECT "id", "name" FROM "employees" ORDER BY "id" LIMIT 2""",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["executed_sql"] == 'SELECT "id", "name" FROM "employees" ORDER BY "id" LIMIT 2'
    assert len(body["rows"]) == 2


def test_query_execution_error_includes_attempted_sql_in_response_detail() -> None:
    client = TestClient(app)
    _connect_duckdb(client)

    sql_text = 'SELECT * FROM "table_that_does_not_exist"'
    response = client.post(
        "/api/query",
        json={
            "execution_mode": "sql",
            "engine": "duckdb",
            "table": "",
            "select": [],
            "filters": [],
            "sort": [],
            "limit_rows": 1000,
            "offset": 0,
            "mode": "LIST",
            "group_by": [],
            "aggregates": [],
            "sql": sql_text,
        },
    )

    assert response.status_code == 400, response.text
    body = response.json()
    assert isinstance(body.get("detail"), dict)
    assert body["detail"]["executed_sql"] == sql_text
    assert "table_that_does_not_exist" in body["detail"]["message"]


def test_query_execution_error_is_persisted_to_samples_error_log(tmp_path: Path) -> None:
    client = TestClient(app)
    _connect_duckdb(client)

    original_error_dir = ErrorLogService.ERROR_DIR
    original_error_file = ErrorLogService.ERROR_FILE
    ErrorLogService.ERROR_DIR = tmp_path / "samples" / "error"
    ErrorLogService.ERROR_FILE = ErrorLogService.ERROR_DIR / "errors.log"

    try:
        sql_text = 'SELECT * FROM "table_that_does_not_exist"'
        response = client.post(
            "/api/query",
            json={
                "execution_mode": "sql",
                "engine": "duckdb",
                "table": "",
                "select": [],
                "filters": [],
                "sort": [],
                "limit_rows": 1000,
                "offset": 0,
                "mode": "LIST",
                "group_by": [],
                "aggregates": [],
                "sql": sql_text,
            },
        )

        assert response.status_code == 400, response.text
        assert ErrorLogService.ERROR_FILE.exists()
        lines = ErrorLogService.ERROR_FILE.read_text(encoding="utf-8").strip().splitlines()
        assert lines, "Expected at least one error event to be written."
        payload = json.loads(lines[-1])
        assert payload["endpoint"] == "/api/query"
        assert payload["engine"] == "duckdb"
        assert payload["execution_mode"] == "sql"
        assert payload["attempted_sql"] == sql_text
        assert "table_that_does_not_exist" in payload["error"]
    finally:
        ErrorLogService.ERROR_DIR = original_error_dir
        ErrorLogService.ERROR_FILE = original_error_file


def test_query_preview_rejects_non_read_only_manual_oracle_sql_without_connection() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/query/preview",
        json={
            "execution_mode": "sql",
            "engine": "oracle",
            "table": "",
            "select": [],
            "filters": [],
            "sort": [],
            "limit_rows": 1000,
            "offset": 0,
            "mode": "LIST",
            "group_by": [],
            "aggregates": [],
            "sql": "DELETE FROM CUSTOMER",
        },
    )

    assert response.status_code == 400
    assert "read-only" in response.json()["detail"]


def test_query_report_adds_grand_total_row_for_duckdb_when_requested() -> None:
    client = TestClient(app)
    _connect_duckdb(client)

    response = client.post(
        "/api/query",
        json={
            "execution_mode": "builder",
            "engine": "duckdb",
            "table": "employees",
            "select": [],
            "filters": [],
            "sort": [],
            "joins": [],
            "limit_rows": 1000,
            "offset": 0,
            "mode": "REPORT",
            "pivot": {
                "rows": ["department"],
                "columns": [],
                "values": "id",
                "func": "COUNT",
            },
            "group_by": [],
            "aggregates": [],
            "marcadose_union": {
                "enabled": False,
                "month_tag": "",
                "discoms": [],
                "base_discom": "",
                "add_grand_total": True,
                "schema_name": "MERCADOS",
            },
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source_mode"] == "builder"
    assert body["rows"][-1][0] == "GRAND TOTAL"
