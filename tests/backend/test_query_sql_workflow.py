"""
test_query_sql_workflow.py - Regression tests for Series 4 SQL preview/editor flows.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import app


TEST_DB_PATH = Path(__file__).resolve().parents[2] / "test_data.duckdb"


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
    assert body["sql"] == 'SELECT "id", "name" FROM "employees" LIMIT 5'


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
