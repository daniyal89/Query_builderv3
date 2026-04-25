"""
marcadose_union_service.py - Builds safe UNION ALL SQL for Marcadose monthly master tables.
"""

from __future__ import annotations

import re
from numbers import Number
from typing import Any

from backend.models.query import MarcadoseUnionConfig


class MarcadoseUnionService:
    """Expands a one-DISCOM Marcadose query across selected monthly master tables."""

    ALLOWED_DISCOMS = ["DVVNL", "PVVNL", "PUVNL", "MVVNL", "KESCO"]

    MASTER_TABLE_PATTERN = re.compile(
        r'(?:"?MERCADOS"?\s*\.\s*)?"?CM_MASTER_DATA_[A-Z]{3}_\d{4}_(?:DVVNL|PVVNL|PUVNL|MVVNL|KESCO)"?',
        re.IGNORECASE,
    )

    COUNT_SELECT_PATTERN = re.compile(
        r"^\s*SELECT\s+COUNT\s*\(\s*\*\s*\)\s+FROM\s+",
        re.IGNORECASE | re.DOTALL,
    )
    FETCH_FIRST_PATTERN = re.compile(
        r"\s+FETCH\s+FIRST\s+(\d+)\s+ROWS\s+ONLY\s*$",
        re.IGNORECASE,
    )

    @classmethod
    def is_active(cls, config: MarcadoseUnionConfig | None) -> bool:
        return bool(config and config.month_tag and config.discoms)

    @classmethod
    def selected_discoms(cls, config: MarcadoseUnionConfig) -> list[str]:
        selected = [
            d.strip().upper()
            for d in config.discoms
            if d.strip().upper() in cls.ALLOWED_DISCOMS
        ]
        return selected or [config.base_discom.strip().upper()]

    @classmethod
    def should_union(cls, config: MarcadoseUnionConfig | None) -> bool:
        return bool(config and config.enabled and len(cls.selected_discoms(config)) > 1)

    @classmethod
    def table_name(cls, config: MarcadoseUnionConfig, discom: str) -> str:
        schema = (config.schema_name or "MERCADOS").strip().upper()
        month_tag = config.month_tag.strip().lower()
        return f"{schema}.CM_master_data_{month_tag}_{discom.strip().upper()}"

    @classmethod
    def _replace_for_discom(
        cls,
        sql: str,
        config: MarcadoseUnionConfig,
        discom: str,
    ) -> str:
        table_name = cls.table_name(config, discom)

        next_sql = sql.replace("{{MASTER_TABLE}}", table_name)
        next_sql = next_sql.replace("{{DISCOM}}", discom.strip().upper())

        # Also support user writing one real master table manually.
        # Example:
        # FROM MERCADOS.CM_master_data_mar_2026_DVVNL m
        # will be replaced per selected DISCOM when union mode is active.
        next_sql = cls.MASTER_TABLE_PATTERN.sub(table_name, next_sql)

        return next_sql

    @classmethod
    def apply(cls, sql: str, config: MarcadoseUnionConfig | None) -> str:
        """Apply monthly master placeholder/table replacement and optional UNION ALL expansion."""

        normalized = sql.strip()
        if normalized.endswith(";"):
            normalized = normalized[:-1].rstrip()

        if not cls.is_active(config):
            return normalized

        assert config is not None

        selected = cls.selected_discoms(config)

        if not cls.should_union(config):
            base_discom = (config.base_discom or selected[0]).strip().upper()
            if base_discom not in selected:
                base_discom = selected[0]

            return cls._replace_for_discom(normalized, config, base_discom)

        fetch_match = cls.FETCH_FIRST_PATTERN.search(normalized)
        branch_limit: int | None = None
        base_sql = normalized
        if fetch_match:
            branch_limit = int(fetch_match.group(1))
            base_sql = normalized[: fetch_match.start()].rstrip()

        branches = [
            f"SELECT * FROM (\n{cls._replace_for_discom(base_sql, config, discom)}\n)"
            for discom in selected
        ]

        if branch_limit is not None:
            branches = [f"{branch} WHERE ROWNUM <= {branch_limit}" for branch in branches]

        return "\nUNION ALL\n".join(branches)

    @classmethod
    def build_total_count_sql(
        cls,
        count_sql: str,
        config: MarcadoseUnionConfig | None,
    ) -> str:
        """Build total row count SQL for unioned Fetch List queries."""

        normalized = count_sql.strip()
        if normalized.endswith(";"):
            normalized = normalized[:-1].rstrip()

        if not cls.should_union(config):
            return cls.apply(normalized, config)

        aliased_count_sql = cls.COUNT_SELECT_PATTERN.sub(
            "SELECT COUNT(*) AS __CNT__ FROM ",
            normalized,
            count=1,
        )

        union_count_sql = cls.apply(aliased_count_sql, config)

        return f"SELECT COALESCE(SUM(__CNT__), 0) AS TOTAL_COUNT FROM (\n{union_count_sql}\n)"

    @staticmethod
    def append_grand_total(columns: list[str], rows: list[list[Any]]) -> list[list[Any]]:
        """Append a simple grand-total row for Generate Report outputs with numeric columns."""

        if not columns or not rows:
            return rows

        numeric_indexes: list[int] = []

        for index in range(len(columns)):
            if any(
                isinstance(row[index], Number) and not isinstance(row[index], bool)
                for row in rows
                if index < len(row)
            ):
                numeric_indexes.append(index)

        if not numeric_indexes:
            return rows

        discom_index = next(
            (i for i, col in enumerate(columns) if col.upper() == "DISCOM"),
            0,
        )

        total_row: list[Any] = []

        for index, column in enumerate(columns):
            if index in numeric_indexes:
                total_row.append(
                    sum(
                        row[index]
                        for row in rows
                        if index < len(row)
                        and isinstance(row[index], Number)
                        and not isinstance(row[index], bool)
                    )
                )
                continue

            if index == discom_index:
                total_row.append("GRAND TOTAL")
                continue

            values = [
                row[index]
                for row in rows
                if index < len(row) and row[index] not in (None, "")
            ]
            unique_values = {str(value) for value in values}

            total_row.append(values[0] if len(unique_values) == 1 and values else "")

        return [*rows, total_row]
