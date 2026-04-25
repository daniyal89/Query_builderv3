from pathlib import Path

from fastapi.testclient import TestClient
import duckdb

from backend.app import app


def test_sidebar_build_duckdb_creates_object_from_csv(tmp_path: Path) -> None:
    db_path = tmp_path / "tools.duckdb"
    csv_path = tmp_path / "input.csv"
    csv_path.write_text("id,name\n1,Alice\n2,Bob\n", encoding="utf-8")

    client = TestClient(app)
    response = client.post(
        "/api/sidebar-tools/build-duckdb",
        json={
            "db_path": str(db_path),
            "input_path": str(csv_path),
            "object_name": "MASTER_FEB_2026",
            "object_type": "TABLE",
            "replace": True,
            "month_label": "FEB_2026",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert "Created TABLE MASTER_FEB_2026" in body["message"]


def test_sidebar_csv_to_parquet_creates_output_file(tmp_path: Path) -> None:
    csv_path = tmp_path / "input.csv"
    output_path = tmp_path / "out.parquet"
    csv_path.write_text("id,name\n1,Alice\n", encoding="utf-8")

    client = TestClient(app)
    response = client.post(
        "/api/sidebar-tools/csv-to-parquet",
        json={
            "input_path": str(csv_path),
            "output_path": str(output_path),
            "compression": "zstd",
        },
    )

    assert response.status_code == 200, response.text
    assert output_path.exists()


def test_sidebar_build_duckdb_detects_parquet_from_wildcard_without_extension(tmp_path: Path) -> None:
    db_path = tmp_path / "tools_parquet.duckdb"
    parquet_dir = tmp_path / "parquet"
    parquet_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = parquet_dir / "data.parquet"

    duckdb.connect().execute("COPY (SELECT 1 AS id, 'Alice' AS name) TO ? (FORMAT PARQUET)", [str(parquet_path)])

    client = TestClient(app)
    response = client.post(
        "/api/sidebar-tools/build-duckdb",
        json={
            "db_path": str(db_path),
            "input_path": str(parquet_dir / "*"),
            "object_name": "MASTER_FROM_PARQUET",
            "object_type": "TABLE",
            "replace": True,
            "month_label": "",
        },
    )

    assert response.status_code == 200, response.text
