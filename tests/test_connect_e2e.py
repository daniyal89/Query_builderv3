"""End-to-end test for the /api/duckdb/connect pipeline."""

import json
import duckdb
import httpx

BASE = "http://127.0.0.1:8741"
DB_PATH = r"d:\PROJECTS\Query_builder\test_data.duckdb"


def setup_test_db():
    """Create a small DuckDB file with two tables and sample rows."""
    conn = duckdb.connect(DB_PATH)
    conn.execute(
        "CREATE OR REPLACE TABLE employees "
        "(id INTEGER, name VARCHAR, department VARCHAR, salary DOUBLE)"
    )
    conn.execute(
        "CREATE OR REPLACE TABLE projects "
        "(id INTEGER, title VARCHAR, budget DOUBLE, start_date DATE)"
    )
    conn.execute(
        "INSERT INTO employees VALUES "
        "(1, 'Alice', 'Engineering', 95000), "
        "(2, 'Bob', 'Marketing', 78000), "
        "(3, 'Carol', 'Engineering', 102000)"
    )
    conn.execute(
        "INSERT INTO projects VALUES "
        "(1, 'Dashboard', 50000, '2026-01-15'), "
        "(2, 'Analytics', 120000, '2026-03-01')"
    )
    conn.close()
    print("=== Test DB created ===\n")


def pp(label, resp):
    """Pretty-print a response."""
    print(f"{label} => {resp.status_code}")
    print(json.dumps(resp.json(), indent=2))
    print()


def run_tests():
    setup_test_db()
    client = httpx.Client(base_url=BASE, timeout=10)

    # 1. Connect to valid DB
    r = client.post("/api/duckdb/connect", json={"db_path": DB_PATH})
    pp("POST /api/duckdb/connect", r)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "connected"
    assert data["tables_count"] == 2

    # 2. List tables
    r = client.get("/api/tables")
    pp("GET /api/tables", r)
    assert r.status_code == 200
    tables = r.json()
    assert len(tables) == 2
    names = {t["table_name"] for t in tables}
    assert names == {"employees", "projects"}
    emp = next(t for t in tables if t["table_name"] == "employees")
    assert emp["row_count"] == 3
    assert len(emp["columns"]) == 4

    # 3. Get columns for employees
    r = client.get("/api/tables/employees/columns")
    pp("GET /api/tables/employees/columns", r)
    assert r.status_code == 200
    cols = r.json()
    col_names = [c["name"] for c in cols]
    assert col_names == ["id", "name", "department", "salary"]

    # 4. Error: empty path
    r = client.post("/api/duckdb/connect", json={"db_path": ""})
    pp("POST /api/duckdb/connect (empty)", r)
    assert r.status_code == 400

    # 5. Error: nonexistent table columns
    r = client.get("/api/tables/nonexistent/columns")
    pp("GET /api/tables/nonexistent/columns", r)
    assert r.status_code == 404

    print("=" * 50)
    print("ALL TESTS PASSED")
    print("=" * 50)


if __name__ == "__main__":
    run_tests()
