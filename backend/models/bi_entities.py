"""bi_entities.py — Core BI domain entities for Phase 1 architecture baseline.

These models define the initial semantic contract for the entities listed in
Phase 1.1 of the BI roadmap: Workspace, DataSource, Dataset, Table, Field,
Metric, Dashboard, and Chart.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


DataSourceType = Literal["duckdb", "parquet", "csv", "tsv", "json", "csv_gz", "json_gz"]
DataSourceStatus = Literal["active", "syncing", "error", "disabled"]
FieldRole = Literal["dimension", "measure", "attribute"]
MetricAggregation = Literal["SUM", "COUNT", "AVG", "MIN", "MAX", "COUNT_DISTINCT"]
ChartType = Literal["table", "bar", "line", "pie", "kpi"]


class Workspace(BaseModel):
    """Top-level collaboration boundary that groups BI artifacts."""

    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str = Field(default="")


class DataSource(BaseModel):
    """Physical data source definition and sync status."""

    id: str = Field(..., min_length=1)
    workspace_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    source_type: DataSourceType
    location: str = Field(..., min_length=1, description="URI/path to the source.")
    status: DataSourceStatus = Field(default="active")


class Dataset(BaseModel):
    """Logical dataset created from one data source."""

    id: str = Field(..., min_length=1)
    workspace_id: str = Field(..., min_length=1)
    data_source_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    published: bool = Field(default=False)


class Table(BaseModel):
    """Tabular object contained inside a dataset."""

    id: str = Field(..., min_length=1)
    dataset_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)


class FieldModel(BaseModel):
    """Column/field definition used by semantic modeling and visuals."""

    id: str = Field(..., min_length=1)
    table_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    data_type: str = Field(..., min_length=1)
    role: FieldRole = Field(default="attribute")


class Metric(BaseModel):
    """Reusable semantic metric built from a field or expression."""

    id: str = Field(..., min_length=1)
    dataset_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    expression: str = Field(..., min_length=1)
    aggregation: MetricAggregation = Field(default="SUM")


class Chart(BaseModel):
    """Single visual element that can be placed on dashboards."""

    id: str = Field(..., min_length=1)
    dataset_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    chart_type: ChartType
    field_ids: list[str] = Field(default_factory=list)
    metric_ids: list[str] = Field(default_factory=list)


class Dashboard(BaseModel):
    """Dashboard canvas containing one or more charts."""

    id: str = Field(..., min_length=1)
    workspace_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    chart_ids: list[str] = Field(default_factory=list)
