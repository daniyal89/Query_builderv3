"""Connector framework + initial file connectors for Phase 1."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import duckdb


class Connector(ABC):
    @abstractmethod
    def detect(self, source: str) -> bool: ...

    @abstractmethod
    def preview(self, source: str, limit: int = 20) -> list[dict]: ...

    @abstractmethod
    def infer_schema(self, source: str) -> list[dict]: ...

    @abstractmethod
    def load_to_engine(self, source: str, mode: str = "view") -> str: ...

    @abstractmethod
    def refresh(self, source: str, strategy: str = "full") -> str: ...

    @abstractmethod
    def capabilities(self) -> dict: ...


class DuckDBFileConnector(Connector):
    def detect(self, source: str) -> bool:
        return source.lower().endswith(".duckdb")

    def preview(self, source: str, limit: int = 20) -> list[dict]:
        with duckdb.connect(source, read_only=True) as con:
            table = con.execute("show tables").fetchone()[0]
            cols = [row[1] for row in con.execute(f"pragma table_info('{table}')").fetchall()]
            rows = con.execute(f"select * from \"{table}\" limit ?", [limit]).fetchall()
        return [dict(zip(cols, row, strict=False)) for row in rows]

    def infer_schema(self, source: str) -> list[dict]:
        with duckdb.connect(source, read_only=True) as con:
            table = con.execute("show tables").fetchone()[0]
            info = con.execute(f"pragma table_info('{table}')").fetchall()
        return [{"name": c[1], "type": c[2]} for c in info]

    def load_to_engine(self, source: str, mode: str = "view") -> str:
        return f"attach '{source}' as source_db;"

    def refresh(self, source: str, strategy: str = "full") -> str:
        return f"refreshed:{Path(source).name}:{strategy}"

    def capabilities(self) -> dict:
        return {"preview": True, "schema_inference": True, "incremental": False}


class ParquetConnector(Connector):
    def detect(self, source: str) -> bool:
        return source.lower().endswith(".parquet")

    def preview(self, source: str, limit: int = 20) -> list[dict]:
        with duckdb.connect() as con:
            rows = con.execute("select * from read_parquet(?) limit ?", [source, limit]).fetchdf()
        return rows.to_dict(orient="records")

    def infer_schema(self, source: str) -> list[dict]:
        with duckdb.connect() as con:
            info = con.execute("describe select * from read_parquet(?)", [source]).fetchall()
        return [{"name": r[0], "type": r[1]} for r in info]

    def load_to_engine(self, source: str, mode: str = "view") -> str:
        return f"create or replace view phase1_source as select * from read_parquet('{source}')"

    def refresh(self, source: str, strategy: str = "full") -> str:
        return f"refreshed:{Path(source).name}:{strategy}"

    def capabilities(self) -> dict:
        return {"preview": True, "schema_inference": True, "incremental": True}


class CSVConnector(Connector):
    def detect(self, source: str) -> bool:
        lowered = source.lower()
        return lowered.endswith(".csv") or lowered.endswith(".tsv") or lowered.endswith(".csv.gz") or lowered.endswith(".json.gz")

    def preview(self, source: str, limit: int = 20) -> list[dict]:
        with duckdb.connect() as con:
            if source.lower().endswith(".json.gz"):
                df = con.execute("select * from read_json_auto(?) limit ?", [source, limit]).fetchdf()
            else:
                delim = "\t" if source.lower().endswith(".tsv") else ","
                df = con.execute("select * from read_csv_auto(?, delim=?) limit ?", [source, delim, limit]).fetchdf()
        return df.to_dict(orient="records")

    def infer_schema(self, source: str) -> list[dict]:
        with duckdb.connect() as con:
            if source.lower().endswith(".json.gz"):
                info = con.execute("describe select * from read_json_auto(?)", [source]).fetchall()
            else:
                delim = "\t" if source.lower().endswith(".tsv") else ","
                info = con.execute("describe select * from read_csv_auto(?, delim=?)", [source, delim]).fetchall()
        return [{"name": r[0], "type": r[1]} for r in info]

    def load_to_engine(self, source: str, mode: str = "view") -> str:
        if source.lower().endswith(".json.gz"):
            return f"create or replace view phase1_source as select * from read_json_auto('{source}')"
        delim = "\t" if source.lower().endswith(".tsv") else ","
        return f"create or replace view phase1_source as select * from read_csv_auto('{source}', delim='{delim}')"

    def refresh(self, source: str, strategy: str = "full") -> str:
        return f"refreshed:{Path(source).name}:{strategy}"

    def capabilities(self) -> dict:
        return {"preview": True, "schema_inference": True, "incremental": True}
