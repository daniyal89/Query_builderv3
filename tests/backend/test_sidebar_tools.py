from pathlib import Path
import gzip

from fastapi.testclient import TestClient
import duckdb

from backend.services.sidebar_tools_service import _drop_existing_duckdb_object
from backend.app import app


def test_sidebar_build_duckdb_creates_object_from_parquet(tmp_path: Path) -> None:
    db_path = tmp_path / "tools.duckdb"
    parquet_path = tmp_path / "input.parquet"
    duckdb.connect().execute("COPY (SELECT 1 AS id, 'Alice' AS name) TO ? (FORMAT PARQUET)", [str(parquet_path)])

    client = TestClient(app)
    response = client.post(
        "/api/sidebar-tools/build-duckdb",
        json={
            "db_path": str(db_path),
            "input_path": str(parquet_path),
            "object_name": "MASTER_FEB_2026",
            "object_type": "TABLE",
            "replace": True,
            "month_label": "FEB_2026",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["message"] == "Created TABLE Master_0226 for FEB_2026. 1 rows."
    assert body["rows_written"] == 1
    assert body["data_quality"] == "ok"


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


def test_sidebar_csv_to_parquet_normalizes_numeric_supply_type_before_lookup_join(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    source.write_text(
        "ACCT_ID,DIV_CODE,SUPPLY_TYPE,LOAD,LOAD_UNIT\n"
        "1001,DIV100,49.0,5,KW\n",
        encoding="utf-8",
    )

    hir_lookup = tmp_path / "hir.csv"
    hir_lookup.write_text(
        "DIV_CODE,DISCOM,CIR_SP_ID,ZON_SP_ID,DIV_NAME,CIRCLE_NAME,ZONE_NAME,SDO_SP_ID,SDO_NAME\n"
        "DIV100,DVVNL,C1,Z1,Div A,Circle A,Zone A,SDO100,Sub Div A\n",
        encoding="utf-8",
    )

    supp_lookup = tmp_path / "supp.csv"
    supp_lookup.write_text(
        "SUPPLY_TYPE,SUPPLY_TYPE_NAME\n"
        "49,LMV\n",
        encoding="utf-8",
    )

    output_path = tmp_path / "enriched.parquet"
    client = TestClient(app)
    response = client.post(
        "/api/sidebar-tools/csv-to-parquet",
        json={
            "input_path": str(source),
            "output_path": str(output_path),
            "compression": "zstd",
            "hir_file": str(hir_lookup),
            "supp_mapper_file": str(supp_lookup),
        },
    )

    assert response.status_code == 200, response.text
    rows = duckdb.connect().execute(
        'SELECT SUPPLY_TYPE, SUPPLY_TYPE_NAME FROM read_parquet(?)',
        [str(output_path)],
    ).fetchall()

    assert rows == [("49", "LMV")]


def test_sidebar_csv_to_parquet_normalizes_other_identifier_keys_before_enrichment_join(tmp_path: Path) -> None:
    source = tmp_path / "input_identifiers.csv"
    source.write_text(
        "ACCT_ID,DIV_CODE,SDO_CODE,SUPPLY_TYPE,LOAD,LOAD_UNIT\n"
        "1001.0,101.0,501.0,49.0,5,KW\n",
        encoding="utf-8",
    )

    hir_lookup = tmp_path / "hir_identifiers.csv"
    hir_lookup.write_text(
        "DIV_CODE,DISCOM,CIR_SP_ID,ZON_SP_ID,DIV_NAME,CIRCLE_NAME,ZONE_NAME,SDO_SP_ID,SDO_NAME\n"
        "101,DVVNL,11,21,Div A,Circle A,Zone A,501,Sub Div A\n",
        encoding="utf-8",
    )

    supp_lookup = tmp_path / "supp_identifiers.csv"
    supp_lookup.write_text(
        "SUPPLY_TYPE,SUPPLY_TYPE_NAME\n"
        "49,LMV\n",
        encoding="utf-8",
    )

    output_path = tmp_path / "normalized_identifiers.parquet"
    client = TestClient(app)
    response = client.post(
        "/api/sidebar-tools/csv-to-parquet",
        json={
            "input_path": str(source),
            "output_path": str(output_path),
            "compression": "zstd",
            "hir_file": str(hir_lookup),
            "supp_mapper_file": str(supp_lookup),
        },
    )

    assert response.status_code == 200, response.text
    rows = duckdb.connect().execute(
        """
        SELECT
            ACCT_ID,
            DIV_CODE,
            SUB_DIV_CODE,
            SUPPLY_TYPE,
            DIV_NAME,
            SDO_NAME,
            SUPPLY_TYPE_NAME
        FROM read_parquet(?)
        """,
        [str(output_path)],
    ).fetchall()

    # ACCT_ID is a 10-digit string, zero-padded on the left, matching the join
    # key that merge_service builds with zfill/LPAD.
    assert rows == [("0000001001", "101", "501", "49", "Div A", "Sub Div A", "LMV")]


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
            "object_name": "PARQUET_IMPORT",
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
            "object_name": "PARQUET_DIR_VIEW",
            "object_type": "VIEW",
            "replace": True,
            "month_label": "",
        },
    )

    assert response.status_code == 200, response.text


def test_sidebar_build_duckdb_supports_trailing_star_pattern_for_nested_parquet(tmp_path: Path) -> None:
    db_path = tmp_path / "tools_parquet_star.duckdb"
    parquet_root = tmp_path / "FEB_parquet_2026"
    nested = parquet_root / "DVVNL"
    nested.mkdir(parents=True, exist_ok=True)
    parquet_path = nested / "part-001.parquet"

    duckdb.connect().execute("COPY (SELECT 1 AS id, 'Alice' AS name) TO ? (FORMAT PARQUET)", [str(parquet_path)])

    client = TestClient(app)
    response = client.post(
        "/api/sidebar-tools/build-duckdb",
        json={
            "db_path": str(db_path),
            "input_path": str(parquet_root / "*"),
            "object_name": "MASTER_FROM_PARQUET_STAR",
            "object_type": "VIEW",
            "replace": True,
            "month_label": "FEB_2026",
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
    assert "Build step could not find parquet outputs" in response.json()["detail"]


def test_sidebar_build_duckdb_replace_can_switch_table_to_view() -> None:
    object_name = "Master_0326"

    with duckdb.connect() as conn:
        conn.execute(f'CREATE TABLE "{object_name}" AS SELECT 1 AS id, \'Alice\' AS name')
        _drop_existing_duckdb_object(conn, object_name)
        conn.execute(f'CREATE VIEW "{object_name}" AS SELECT 1 AS id, \'Alice\' AS name')
        obj_type = conn.execute(
            "SELECT table_type FROM information_schema.tables "
            "WHERE table_schema = 'main' AND lower(table_name) = lower(?)",
            [object_name],
        ).fetchone()

    assert obj_type is not None
    assert obj_type[0] == "VIEW"


def test_sidebar_build_duckdb_replace_is_case_insensitive_for_existing_object_lookup() -> None:
    with duckdb.connect() as conn:
        conn.execute('CREATE TABLE "Master_0326" AS SELECT 1 AS id')
        _drop_existing_duckdb_object(conn, "master_0326")
        existing = conn.execute(
            "SELECT table_type FROM information_schema.tables "
            "WHERE table_schema = 'main' AND lower(table_name) = lower(?)",
            ["Master_0326"],
        ).fetchone()

    assert existing is None
