"""
merge_service.py - Business logic for multi-sheet merge and enrichment.
"""

from __future__ import annotations

import gzip
import io
import zipfile
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


class MergeService:
    """Service to handle the data logic for merge workflows."""

    SUPPORTED_FILE_SUFFIXES = (".csv", ".xlsx", ".xls", ".xlsb", ".gz", ".zip")

    @staticmethod
    def process_enrichment(
        merged_df: pd.DataFrame,
        conn: duckdb.DuckDBPyConnection,
        master_table: str,
        fetch_columns: list[str],
        join_keys: list[dict[str, str]],
    ) -> tuple[pd.DataFrame, dict[str, int]]:
        """
        Execute a SQL LEFT JOIN between the incoming dataframe and the DuckDB master table.

        join_keys is a list of {"fileColumn": "...", "tableColumn": "..."} mappings
        that define the ON clause dynamically.
        """
        if not join_keys:
            raise ValueError("At least one join key mapping is required.")

        # Validate that every fileColumn exists in the uploaded dataframe
        for mapping in join_keys:
            file_col = mapping.get("fileColumn", "")
            table_col = mapping.get("tableColumn", "")
            if not file_col or not table_col:
                raise ValueError("Each join key must specify both fileColumn and tableColumn.")
            if file_col not in merged_df.columns:
                raise ValueError(
                    f"File column '{file_col}' not found in uploaded data. "
                    f"Available columns: {list(merged_df.columns)}"
                )

        normalized_master_table = master_table.strip()
        if not normalized_master_table:
            raise ValueError("A DuckDB source table is required for enrichment.")

        # Build dynamic JOIN clause — cast both sides to VARCHAR to handle type mismatches
        join_conditions = []
        for mapping in join_keys:
            join_conditions.append(
                f'CAST(df."{mapping["fileColumn"]}" AS VARCHAR) = CAST(source."{mapping["tableColumn"]}" AS VARCHAR)'
            )
        join_clause = " AND ".join(join_conditions)

        fetch_cols_str = ", ".join([f'source."{column}"' for column in fetch_columns])

        try:
            conn.register("df", merged_df)

            query = f"""
                SELECT df.*, {fetch_cols_str}
                FROM df
                LEFT JOIN "{normalized_master_table}" AS source
                ON {join_clause}
            """
            result_df = conn.execute(query).df()

            matched_query = f"""
                SELECT COUNT(*) FROM df
                INNER JOIN "{normalized_master_table}" AS source
                ON {join_clause}
            """
            matched_rows = int(conn.execute(matched_query).fetchone()[0])
            total_rows = len(result_df)
            unmatched_rows = total_rows - matched_rows

            stats = {
                "matched_rows": matched_rows,
                "unmatched_rows": unmatched_rows,
                "total_rows": total_rows,
            }

            return result_df, stats
        except duckdb.CatalogException as exc:
            if normalized_master_table.lower() in str(exc).lower():
                raise ValueError(
                    f"Target database does not contain the selected table '{normalized_master_table}'."
                ) from exc
            raise
        finally:
            try:
                conn.unregister("df")
            except Exception:
                pass

    @staticmethod
    def merge_folder(
        source_folder: str,
        output_path: str,
        include_subfolders: bool = True,
    ) -> dict[str, Any]:
        """Recursively merge supported files from a local folder and save the result."""
        source_dir = Path(source_folder).expanduser()
        save_path = Path(output_path).expanduser()

        if not source_dir.exists() or not source_dir.is_dir():
            raise ValueError(f"Source folder not found: {source_dir}")

        output_format = save_path.suffix.lower()
        if output_format not in {".csv", ".xlsx"}:
            raise ValueError("Output file must end with .csv or .xlsx")

        source_files = MergeService._discover_supported_files(source_dir, include_subfolders)
        if not source_files:
            raise ValueError(
                "No supported files found. Supported types: .csv, .xlsx, .xls, .xlsb, .gz, .zip"
            )

        merged_parts: list[pd.DataFrame] = []
        merged_items = 0

        for file_path in source_files:
            for dataframe, source_name, sheet_name in MergeService._load_supported_file(file_path):
                prepared = MergeService._prepare_dataframe(dataframe, source_name, sheet_name)
                if prepared is None:
                    continue
                merged_parts.append(prepared)
                merged_items += 1

        if not merged_parts:
            raise ValueError("No readable data was found in the selected folder.")

        merged_df = pd.concat(merged_parts, ignore_index=True, sort=False)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        MergeService._write_output(merged_df, save_path)

        return {
            "output_path": str(save_path),
            "output_format": output_format.lstrip("."),
            "total_files": len(source_files),
            "merged_items": merged_items,
            "total_rows": int(len(merged_df)),
            "total_columns": int(len(merged_df.columns)),
        }

    @staticmethod
    def _discover_supported_files(source_dir: Path, include_subfolders: bool) -> list[Path]:
        iterator = source_dir.rglob("*") if include_subfolders else source_dir.glob("*")
        files = [path for path in iterator if path.is_file() and MergeService._is_supported_file(path.name)]
        return sorted(files)

    @staticmethod
    def _is_supported_file(name: str) -> bool:
        lower_name = name.lower()
        return lower_name.endswith(MergeService.SUPPORTED_FILE_SUFFIXES)

    @staticmethod
    def _load_supported_file(path: Path) -> list[tuple[pd.DataFrame, str, str]]:
        lower_name = path.name.lower()

        if lower_name.endswith(".csv"):
            dataframe = MergeService._read_csv(io.BytesIO(path.read_bytes()), path.name)
            return [(dataframe, path.name, "Sheet1")]

        if lower_name.endswith((".xlsx", ".xls", ".xlsb")):
            return MergeService._read_excel(io.BytesIO(path.read_bytes()), path.name)

        if lower_name.endswith(".gz"):
            raw_bytes = gzip.decompress(path.read_bytes())
            inferred_name = Path(path.stem).name or path.name.replace(".gz", "")
            return MergeService._load_virtual_file(raw_bytes, inferred_name, f"{path.name}::{inferred_name}")

        if lower_name.endswith(".zip"):
            return MergeService._read_zip_bytes(path.read_bytes(), path.name)

        raise ValueError(f"Unsupported file type: {path.name}")

    @staticmethod
    def _load_virtual_file(
        raw_bytes: bytes,
        virtual_name: str,
        source_label: str,
    ) -> list[tuple[pd.DataFrame, str, str]]:
        lower_name = virtual_name.lower()

        if lower_name.endswith(".csv"):
            dataframe = MergeService._read_csv(io.BytesIO(raw_bytes), source_label)
            return [(dataframe, source_label, "Sheet1")]

        if lower_name.endswith((".xlsx", ".xls", ".xlsb")):
            return MergeService._read_excel(io.BytesIO(raw_bytes), source_label)

        if lower_name.endswith(".gz"):
            nested_bytes = gzip.decompress(raw_bytes)
            nested_name = Path(virtual_name).stem or virtual_name.replace(".gz", "")
            nested_label = f"{source_label}::{nested_name}"
            return MergeService._load_virtual_file(nested_bytes, nested_name, nested_label)

        if lower_name.endswith(".zip"):
            return MergeService._read_zip_bytes(raw_bytes, source_label)

        return []

    @staticmethod
    def _read_zip_bytes(raw_bytes: bytes, archive_name: str) -> list[tuple[pd.DataFrame, str, str]]:
        merged_entries: list[tuple[pd.DataFrame, str, str]] = []
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
            for info in archive.infolist():
                if info.is_dir() or not MergeService._is_supported_file(info.filename):
                    continue
                entry_bytes = archive.read(info.filename)
                entry_label = f"{archive_name}::{info.filename}"
                merged_entries.extend(
                    MergeService._load_virtual_file(entry_bytes, info.filename, entry_label)
                )
        return merged_entries

    @staticmethod
    def _read_csv(buffer: io.BytesIO, source_name: str) -> pd.DataFrame:
        buffer.seek(0)
        try:
            return pd.read_csv(
                buffer,
                dtype=str,
                low_memory=False,
                encoding_errors="replace",
            )
        except Exception:
            buffer.seek(0)
            try:
                return pd.read_csv(
                    buffer,
                    dtype=str,
                    low_memory=False,
                    encoding_errors="replace",
                    sep=None,
                    engine="python",
                )
            except Exception as exc:
                raise ValueError(f"Failed to read CSV data from {source_name}: {exc}") from exc

    @staticmethod
    def _read_excel(buffer: io.BytesIO, source_name: str) -> list[tuple[pd.DataFrame, str, str]]:
        engine = None
        lower_name = source_name.lower()

        if lower_name.endswith(".xlsb"):
            engine = "pyxlsb"
        elif lower_name.endswith(".xls"):
            engine = "xlrd"

        try:
            sheets = pd.read_excel(buffer, sheet_name=None, dtype=str, engine=engine)
        except ImportError as exc:
            raise ValueError(
                f"Missing Excel dependency while reading {source_name}: {exc}"
            ) from exc
        except Exception as exc:
            raise ValueError(f"Failed to read Excel file {source_name}: {exc}") from exc

        return [(dataframe, source_name, str(sheet_name)) for sheet_name, dataframe in sheets.items()]

    @staticmethod
    def _prepare_dataframe(
        dataframe: pd.DataFrame,
        source_name: str,
        sheet_name: str,
    ) -> pd.DataFrame | None:
        if dataframe.empty and len(dataframe.columns) == 0:
            return None

        prepared = dataframe.copy()
        prepared.columns = MergeService._make_unique_headers(prepared.columns)
        prepared.insert(0, "SOURCE_SHEET", sheet_name or "Sheet1")
        prepared.insert(0, "SOURCE_FILE", source_name)
        return prepared

    @staticmethod
    def _make_unique_headers(columns: pd.Index) -> list[str]:
        seen: dict[str, int] = {}
        normalized: list[str] = []

        for idx, column in enumerate(columns, start=1):
            base_name = str(column).strip() or f"Column_{idx}"
            if base_name not in seen:
                seen[base_name] = 1
                normalized.append(base_name)
                continue

            seen[base_name] += 1
            normalized.append(f"{base_name}_{seen[base_name]}")

        return normalized

    @staticmethod
    def _write_output(merged_df: pd.DataFrame, save_path: Path) -> None:
        suffix = save_path.suffix.lower()
        if suffix == ".csv":
            merged_df.to_csv(save_path, index=False, encoding="utf-8-sig")
            return

        if suffix == ".xlsx":
            with pd.ExcelWriter(save_path, engine="openpyxl") as writer:
                merged_df.to_excel(writer, index=False, sheet_name="MergedData")
            return

        raise ValueError("Unsupported output format. Use .csv or .xlsx")
