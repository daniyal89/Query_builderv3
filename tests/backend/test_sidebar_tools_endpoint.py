from pathlib import Path
import gzip

import pytest
from fastapi.testclient import TestClient

from backend.api.endpoints.sidebar_tools import (
    _infer_input_root,
    _parquet_target_for_input,
    _resolve_existing_input_glob,
)
from backend.app import app


def test_resolve_existing_input_glob_accepts_wrapped_quotes(tmp_path: Path) -> None:
    sample = tmp_path / "sample.csv.gz"
    sample.write_text("a,b\n1,2\n", encoding="utf-8")

    resolved = _resolve_existing_input_glob(f'"{tmp_path.as_posix()}/*.csv.gz"')

    assert resolved.endswith("/*.csv.gz")


def test_resolve_existing_input_glob_falls_back_to_gz(tmp_path: Path) -> None:
    sample = tmp_path / "sample.gz"
    sample.write_text("a,b\n1,2\n", encoding="utf-8")

    resolved = _resolve_existing_input_glob(f"{tmp_path.as_posix()}/*.csv.gz")

    assert resolved.endswith("/*.gz")


def test_resolve_existing_input_glob_falls_back_to_csv(tmp_path: Path) -> None:
    sample = tmp_path / "sample.csv"
    sample.write_text("a,b\n1,2\n", encoding="utf-8")

    resolved = _resolve_existing_input_glob(f"{tmp_path.as_posix()}/*.csv.gz")

    assert resolved.endswith("/*.csv")


def test_resolve_existing_input_glob_accepts_directory_path(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir(parents=True, exist_ok=True)
    sample = nested / "inside.csv.gz"
    sample.write_text("a,b\n1,2\n", encoding="utf-8")

    resolved = _resolve_existing_input_glob(tmp_path.as_posix())

    assert resolved.endswith("/**/*.csv.gz")


def test_resolve_existing_input_glob_supports_recursive_from_non_recursive_pattern(tmp_path: Path) -> None:
    nested = tmp_path / "deep"
    nested.mkdir(parents=True, exist_ok=True)
    sample = nested / "inside.csv"
    sample.write_text("a,b\n1,2\n", encoding="utf-8")

    resolved = _resolve_existing_input_glob(f"{tmp_path.as_posix()}/*.csv.gz")

    assert resolved.endswith("/**/*.csv")


def test_resolve_existing_input_glob_raises_when_no_match(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No files found"):
        _resolve_existing_input_glob(f"{tmp_path.as_posix()}/*.csv.gz")


def test_infer_input_root_uses_pattern_prefix(tmp_path: Path) -> None:
    nested = tmp_path / "m" / "d"
    nested.mkdir(parents=True, exist_ok=True)
    sample = nested / "a.csv.gz"
    sample.write_text("a,b\n1,2\n", encoding="utf-8")

    root = _infer_input_root(f"{tmp_path.as_posix()}/**/*.csv.gz", [sample])

    assert root == tmp_path.resolve()


def test_parquet_target_preserves_relative_structure(tmp_path: Path) -> None:
    output_root = tmp_path / "out"
    input_root = tmp_path / "in"
    source_file = input_root / "DIV1" / "sample.csv.gz"

    target = _parquet_target_for_input(output_root, input_root, source_file)

    assert target.as_posix().endswith("/out/DIV1/sample.parquet")


def test_csv_to_parquet_endpoint_handles_mixed_numeric_text_columns(tmp_path: Path) -> None:
    source = tmp_path / "mixed.csv.gz"
    with gzip.open(source, "wt", encoding="utf-8") as handle:
        handle.write("KNO,VALUE\n123,1\nDV_111368,2\n")

    output_file = tmp_path / "out.parquet"
    client = TestClient(app)
    response = client.post(
        "/api/sidebar-tools/csv-to-parquet",
        json={
            "input_path": str(source),
            "output_path": str(output_file),
            "compression": "zstd",
        },
    )

    assert response.status_code == 200, response.text
    assert output_file.exists()


def test_csv_to_parquet_job_start_status_and_stop(tmp_path: Path) -> None:
    source = tmp_path / "many.csv.gz"
    with gzip.open(source, "wt", encoding="utf-8") as handle:
        handle.write("KNO,VALUE\n123,1\nDV_111368,2\n")

    output_folder = tmp_path / "parquet_out"
    client = TestClient(app)
    start = client.post(
        "/api/sidebar-tools/csv-to-parquet/start",
        json={
            "input_path": str(source),
            "output_path": str(output_folder),
            "compression": "zstd",
        },
    )
    assert start.status_code == 200, start.text
    job_id = start.json()["job_id"]

    status_response = client.get(f"/api/sidebar-tools/csv-to-parquet/status/{job_id}")
    assert status_response.status_code == 200, status_response.text
    assert status_response.json()["status"] in {"queued", "running", "completed"}
    assert "skipped_files" in status_response.json()

    stop_response = client.post(f"/api/sidebar-tools/csv-to-parquet/stop/{job_id}")
    assert stop_response.status_code == 200, stop_response.text


def test_csv_to_parquet_endpoint_skips_existing_output_file(tmp_path: Path) -> None:
    source = tmp_path / "already.csv.gz"
    with gzip.open(source, "wt", encoding="utf-8") as handle:
        handle.write("KNO,VALUE\n123,1\n")

    output_file = tmp_path / "already.parquet"
    output_file.write_bytes(b"existing")
    original_size = output_file.stat().st_size

    client = TestClient(app)
    response = client.post(
        "/api/sidebar-tools/csv-to-parquet",
        json={
            "input_path": str(source),
            "output_path": str(output_file),
            "compression": "zstd",
        },
    )

    assert response.status_code == 200, response.text
    assert "Skipped conversion" in response.json()["message"]
    assert output_file.stat().st_size == original_size


def test_build_duckdb_job_start_status_and_stop(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    source.write_text("id,name\n1,Alice\n", encoding="utf-8")
    db_path = tmp_path / "job_build.duckdb"
    client = TestClient(app)

    start = client.post(
        "/api/sidebar-tools/build-duckdb/start",
        json={
            "db_path": str(db_path),
            "input_path": str(source),
            "object_name": "MASTER_TEST",
            "object_type": "TABLE",
            "replace": True,
            "month_label": "MAR_2026",
        },
    )
    assert start.status_code == 200, start.text
    job_id = start.json()["job_id"]

    status_response = client.get(f"/api/sidebar-tools/build-duckdb/status/{job_id}")
    assert status_response.status_code == 200, status_response.text
    assert status_response.json()["status"] in {"queued", "running", "completed"}
    assert "progress_percent" in status_response.json()

    stop_response = client.post(f"/api/sidebar-tools/build-duckdb/stop/{job_id}")
    assert stop_response.status_code == 200, stop_response.text
