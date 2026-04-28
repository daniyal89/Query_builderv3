from pathlib import Path
import gzip

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


def test_sidebar_csv_to_parquet_supports_gz_when_pattern_is_csv_gz(tmp_path: Path) -> None:
    csv_dir = tmp_path / "master" / "MAR_2026"
    csv_dir.mkdir(parents=True, exist_ok=True)
    gz_path = csv_dir / "part-001.gz"
    output_path = tmp_path / "out_from_gz.parquet"

    with gzip.open(gz_path, "wt", encoding="utf-8") as handle:
        handle.write("id,name\n1,Alice\n")

    client = TestClient(app)
    response = client.post(
        "/api/sidebar-tools/csv-to-parquet",
        json={
            "input_path": str(csv_dir / "*.csv.gz"),
            "output_path": str(output_path),
            "compression": "zstd",
        },
    )

    assert response.status_code == 200, response.text
    assert output_path.exists()


def test_sidebar_csv_to_parquet_rejects_unknown_compression(tmp_path: Path) -> None:
    csv_path = tmp_path / "input.csv"
    output_path = tmp_path / "out.parquet"
    csv_path.write_text("id,name\n1,Alice\n", encoding="utf-8")

    client = TestClient(app)
    response = client.post(
        "/api/sidebar-tools/csv-to-parquet",
        json={
            "input_path": str(csv_path),
            "output_path": str(output_path),
            "compression": "not-a-codec",
        },
    )

    assert response.status_code == 422, response.text


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


def test_sidebar_build_duckdb_accepts_directory_with_nested_parquet_files(tmp_path: Path) -> None:
    db_path = tmp_path / "tools_parquet_dir.duckdb"
    parquet_dir = tmp_path / "parquet_root"
    nested = parquet_dir / "FEB_2026"
    nested.mkdir(parents=True, exist_ok=True)
    parquet_path = nested / "data.parquet"

    duckdb.connect().execute("COPY (SELECT 1 AS id, 'Alice' AS name) TO ? (FORMAT PARQUET)", [str(parquet_path)])

    client = TestClient(app)
    response = client.post(
        "/api/sidebar-tools/build-duckdb",
        json={
            "db_path": str(db_path),
            "input_path": str(parquet_dir),
            "object_name": "MASTER_FROM_PARQUET_DIR",
            "object_type": "VIEW",
            "replace": True,
            "month_label": "",
        },
    )

    assert response.status_code == 200, response.text


def test_sidebar_build_duckdb_detects_gz_csv_from_wildcard_without_extension(tmp_path: Path) -> None:
    db_path = tmp_path / "tools_gz.duckdb"
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    gz_path = csv_dir / "data.gz"

    with gzip.open(gz_path, "wt", encoding="utf-8") as handle:
        handle.write("id,name\n1,Alice\n")

    client = TestClient(app)
    response = client.post(
        "/api/sidebar-tools/build-duckdb",
        json={
            "db_path": str(db_path),
            "input_path": str(csv_dir / "*"),
            "object_name": "MASTER_FROM_GZ",
            "object_type": "VIEW",
            "replace": True,
            "month_label": "",
        },
    )

    assert response.status_code == 200, response.text


def test_sidebar_build_duckdb_rejects_missing_input_pattern(tmp_path: Path) -> None:
    db_path = tmp_path / "tools_missing.duckdb"

    client = TestClient(app)
    response = client.post(
        "/api/sidebar-tools/build-duckdb",
        json={
            "db_path": str(db_path),
            "input_path": str(tmp_path / "does-not-exist" / "*.csv"),
            "object_name": "MISSING_INPUT",
            "object_type": "TABLE",
            "replace": True,
            "month_label": "",
        },
    )

    assert response.status_code == 400, response.text
    assert "No files found that match the pattern" in response.json()["detail"]


def test_sidebar_build_duckdb_replace_can_switch_table_to_view(tmp_path: Path) -> None:
    db_path = tmp_path / "tools_switch_type.duckdb"
    csv_path = tmp_path / "switch.csv"
    csv_path.write_text("id,name\n1,Alice\n", encoding="utf-8")

    client = TestClient(app)
    create_table = client.post(
        "/api/sidebar-tools/build-duckdb",
        json={
            "db_path": str(db_path),
            "input_path": str(csv_path),
            "object_name": "master",
            "object_type": "TABLE",
            "replace": True,
            "month_label": "",
        },
    )
    assert create_table.status_code == 200, create_table.text

    replace_with_view = client.post(
        "/api/sidebar-tools/build-duckdb",
        json={
            "db_path": str(db_path),
            "input_path": str(csv_path),
            "object_name": "master",
            "object_type": "VIEW",
            "replace": True,
            "month_label": "",
        },
    )
    assert replace_with_view.status_code == 200, replace_with_view.text

    with duckdb.connect(str(db_path)) as conn:
        obj_type = conn.execute(
            "SELECT table_type FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_name = 'master'"
        ).fetchone()

    assert obj_type is not None
    assert obj_type[0] == "VIEW"


def test_sidebar_build_duckdb_replace_is_case_insensitive_for_existing_object_lookup(tmp_path: Path) -> None:
    db_path = tmp_path / "tools_switch_case.duckdb"
    csv_path = tmp_path / "switch_case.csv"
    csv_path.write_text("id,name\n1,Alice\n", encoding="utf-8")

    client = TestClient(app)
    create_table = client.post(
        "/api/sidebar-tools/build-duckdb",
        json={
            "db_path": str(db_path),
            "input_path": str(csv_path),
            "object_name": "MASTER",
            "object_type": "TABLE",
            "replace": True,
            "month_label": "",
        },
    )
    assert create_table.status_code == 200, create_table.text

    replace_with_view = client.post(
        "/api/sidebar-tools/build-duckdb",
        json={
            "db_path": str(db_path),
            "input_path": str(csv_path),
            "object_name": "master",
            "object_type": "VIEW",
            "replace": True,
            "month_label": "",
        },
    )
    assert replace_with_view.status_code == 200, replace_with_view.text
