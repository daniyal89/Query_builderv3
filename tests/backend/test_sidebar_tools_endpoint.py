from pathlib import Path

import pytest

from backend.api.endpoints.sidebar_tools import _resolve_existing_input_glob


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
