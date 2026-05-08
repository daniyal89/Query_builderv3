"""Connector framework + initial file connectors for Phase 1."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import duckdb

from backend.services.duckdb_service import DuckDBService


class Connector(ABC):
    @abstractmethod
    def detect(self, source: str) -> bool: ...

    @abstractmethod
    def preview(self, source: str, limit: int = 20, table_name: str | None = None) -> list[dict]: ...

    @abstractmethod
    def infer_schema(self, source: str, table_name: str | None = None) -> list[dict]: ...

    @abstractmethod
    def list_tables(self, source: str) -> list[str]: ...

    @abstractmethod
    def load_to_engine(self, source: str, mode: str = "view", table_name: str | None = None) -> str: ...

    @abstractmethod
    def refresh(self, source: str, strategy: str = "full", table_name: str | None = None) -> str: ...

    @abstractmethod
    def capabilities(self) -> dict: ...


class DuckDBFileConnector(Connector):
    def __init__(self, duckdb_service: DuckDBService | None = None) -> None:
        self._duckdb_service = duckdb_service

    def detect(self, source: str) -> bool:
        return source.lower().endswith(".duckdb")

    def _fetch_tables(self, source: str) -> list[str]:
        if self._duckdb_service and self._duckdb_service.is_connected and self._duckdb_service.current_db_path == source:
            return [row[0] for row in self._duckdb_service.execute_on_connection("show tables")]
        with duckdb.connect(source, read_only=True) as con:
            return [row[0] for row in con.execute("show tables").fetchall()]

    def _choose_table(self, source: str, table_name: str | None = None) -> str:
        tables = self._fetch_tables(source)
        if not tables:
            raise RuntimeError("No tables found in DuckDB source.")
        if table_name is None:
            return tables[0]
        if table_name not in tables:
            raise ValueError(f"Table '{table_name}' was not found in DuckDB source.")
        return table_name

    def preview(self, source: str, limit: int = 20, table_name: str | None = None) -> list[dict]:
        table = self._choose_table(source, table_name)
        if self._duckdb_service and self._duckdb_service.is_connected and self._duckdb_service.current_db_path == source:
            cols = [row[1] for row in self._duckdb_service.execute_on_connection(f"pragma table_info('{table}')")]
            rows = self._duckdb_service.execute_on_connection(f"select * from \"{table}\" limit ?", (limit,))
        else:
            with duckdb.connect(source, read_only=True) as con:
                cols = [row[1] for row in con.execute(f"pragma table_info('{table}')").fetchall()]
                rows = con.execute(f"select * from \"{table}\" limit ?", [limit]).fetchall()
        return [dict(zip(cols, row, strict=False)) for row in rows]

    def infer_schema(self, source: str, table_name: str | None = None) -> list[dict]:
        table = self._choose_table(source, table_name)
        if self._duckdb_service and self._duckdb_service.is_connected and self._duckdb_service.current_db_path == source:
            info = self._duckdb_service.execute_on_connection(f"pragma table_info('{table}')")
        else:
            with duckdb.connect(source, read_only=True) as con:
                info = con.execute(f"pragma table_info('{table}')").fetchall()
        return [{"name": c[1], "type": c[2]} for c in info]

    def list_tables(self, source: str) -> list[str]:
        return self._fetch_tables(source)

    def load_to_engine(self, source: str, mode: str = "view", table_name: str | None = None) -> str:
        return f"attach '{source}' as source_db;"

    def refresh(self, source: str, strategy: str = "full", table_name: str | None = None) -> str:
        return f"refreshed:{Path(source).name}:{strategy}"

    def capabilities(self) -> dict:
        return {"preview": True, "schema_inference": True, "incremental": False}


class ParquetConnector(Connector):
    def detect(self, source: str) -> bool:
        return source.lower().endswith(".parquet")

    def preview(self, source: str, limit: int = 20, table_name: str | None = None) -> list[dict]:
        with duckdb.connect() as con:
            rows = con.execute("select * from read_parquet(?) limit ?", [source, limit]).fetchdf()
        return rows.to_dict(orient="records")

    def infer_schema(self, source: str, table_name: str | None = None) -> list[dict]:
        with duckdb.connect() as con:
            info = con.execute("describe select * from read_parquet(?)", [source]).fetchall()
        return [{"name": r[0], "type": r[1]} for r in info]

    def list_tables(self, source: str) -> list[str]:
        return [Path(source).name]

    def load_to_engine(self, source: str, mode: str = "view", table_name: str | None = None) -> str:
        return f"create or replace view phase1_source as select * from read_parquet('{source}')"

    def refresh(self, source: str, strategy: str = "full", table_name: str | None = None) -> str:
        return f"refreshed:{Path(source).name}:{strategy}"

    def capabilities(self) -> dict:
        return {"preview": True, "schema_inference": True, "incremental": True}


class CSVConnector(Connector):
    def detect(self, source: str) -> bool:
        lowered = source.lower()
        return (
            lowered.endswith(".csv")
            or lowered.endswith(".tsv")
            or lowered.endswith(".json")
            or lowered.endswith(".csv.gz")
            or lowered.endswith(".json.gz")
        )

    def preview(self, source: str, limit: int = 20, table_name: str | None = None) -> list[dict]:
        with duckdb.connect() as con:
            if source.lower().endswith(".json") or source.lower().endswith(".json.gz"):
                df = con.execute("select * from read_json_auto(?) limit ?", [source, limit]).fetchdf()
            else:
                delim = "\t" if source.lower().endswith(".tsv") else ","
                df = con.execute("select * from read_csv_auto(?, delim=?) limit ?", [source, delim, limit]).fetchdf()
        return df.to_dict(orient="records")

    def infer_schema(self, source: str, table_name: str | None = None) -> list[dict]:
        with duckdb.connect() as con:
            if source.lower().endswith(".json") or source.lower().endswith(".json.gz"):
                info = con.execute("describe select * from read_json_auto(?)", [source]).fetchall()
            else:
                delim = "\t" if source.lower().endswith(".tsv") else ","
                info = con.execute("describe select * from read_csv_auto(?, delim=?)", [source, delim]).fetchall()
        return [{"name": r[0], "type": r[1]} for r in info]

    def list_tables(self, source: str) -> list[str]:
        return [Path(source).name]

    def load_to_engine(self, source: str, mode: str = "view", table_name: str | None = None) -> str:
        if source.lower().endswith(".json") or source.lower().endswith(".json.gz"):
            return f"create or replace view phase1_source as select * from read_json_auto('{source}')"
        delim = "\t" if source.lower().endswith(".tsv") else ","
        return f"create or replace view phase1_source as select * from read_csv_auto('{source}', delim='{delim}')"

    def refresh(self, source: str, strategy: str = "full", table_name: str | None = None) -> str:
        return f"refreshed:{Path(source).name}:{strategy}"

    def capabilities(self) -> dict:
        return {"preview": True, "schema_inference": True, "incremental": True}
