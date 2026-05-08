"""API contracts for the BI Phase 1 workspace endpoints."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.models.bi_entities import (
    Chart,
    ChartType,
    Dashboard,
    DataSource,
    DataSourceType,
    Dataset,
    FieldModel,
    Metric,
    MetricAggregation,
    Table,
    Workspace,
)


class BIPhase1CreateWorkspaceRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = Field(default="")


class BIPhase1RegisterSourceRequest(BaseModel):
    workspace_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    location: str = Field(..., min_length=1)
    source_type: Literal["auto", "duckdb", "parquet", "csv", "tsv", "json", "csv_gz", "json_gz"] = "auto"


class BIPhase1CreateDatasetRequest(BaseModel):
    workspace_id: str = Field(..., min_length=1)
    data_source_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    table_name: str | None = None


class BIPhase1CreateMetricRequest(BaseModel):
    dataset_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    expression: str = Field(..., min_length=1)
    aggregation: MetricAggregation = "SUM"


class BIPhase1CreateChartRequest(BaseModel):
    dataset_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    chart_type: ChartType
    field_ids: list[str] = Field(default_factory=list)
    metric_ids: list[str] = Field(default_factory=list)


class BIPhase1CreateDashboardRequest(BaseModel):
    workspace_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    chart_ids: list[str] = Field(default_factory=list)


class BIPhase1SourceInsightResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_id: str = Field(..., min_length=1)
    detected_type: DataSourceType
    capabilities: dict[str, bool] = Field(default_factory=dict)
    table_names: list[str] = Field(default_factory=list)
    selected_table: str | None = Field(default=None)
    schema_rows: list[dict[str, str]] = Field(default_factory=list, alias="schema")
    preview_rows: list[dict[str, Any]] = Field(default_factory=list)
    status: str = Field(default="active")
    last_sync: str = Field(default="never")
    load_strategy: str = Field(default="")


class BIPhase1AuditEventResponse(BaseModel):
    at: str = Field(..., min_length=1)
    actor: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    target: str = Field(..., min_length=1)


class BIPhase1StateResponse(BaseModel):
    workspaces: list[Workspace] = Field(default_factory=list)
    data_sources: list[DataSource] = Field(default_factory=list)
    datasets: list[Dataset] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    fields: list[FieldModel] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)
    charts: list[Chart] = Field(default_factory=list)
    dashboards: list[Dashboard] = Field(default_factory=list)
    source_insights: list[BIPhase1SourceInsightResponse] = Field(default_factory=list)
    audits: list[BIPhase1AuditEventResponse] = Field(default_factory=list)
