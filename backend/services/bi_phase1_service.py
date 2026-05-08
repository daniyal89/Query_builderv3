"""Phase 1 BI foundation service."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import re
from typing import Any, Literal
from uuid import uuid4

from backend.models.bi_entities import Chart, Dashboard, DataSource, DataSourceType, Dataset, FieldModel, Metric, Table, Workspace
from backend.models.bi_phase1_api import (
    BIPhase1AuditEventResponse,
    BIPhase1SourceInsightResponse,
    BIPhase1StateResponse,
)
from backend.services.connectors import CSVConnector, Connector, DuckDBFileConnector, ParquetConnector
from backend.services.duckdb_service import DuckDBService

Role = Literal["Admin", "Editor", "Viewer"]

NUMERIC_TYPE_KEYWORDS = ("int", "decimal", "double", "float", "real", "numeric", "bigint", "smallint", "tinyint")
DATE_TYPE_KEYWORDS = ("date", "time", "timestamp")


@dataclass
class AuditEvent:
    at: str
    actor: str
    action: str
    target: str


@dataclass
class BIPhase1Store:
    workspaces: dict[str, Workspace] = field(default_factory=dict)
    data_sources: dict[str, DataSource] = field(default_factory=dict)
    datasets: dict[str, Dataset] = field(default_factory=dict)
    tables: dict[str, Table] = field(default_factory=dict)
    fields: dict[str, FieldModel] = field(default_factory=dict)
    metrics: dict[str, Metric] = field(default_factory=dict)
    charts: dict[str, Chart] = field(default_factory=dict)
    dashboards: dict[str, Dashboard] = field(default_factory=dict)
    source_registry: dict[str, dict[str, Any]] = field(default_factory=dict)
    audits: list[AuditEvent] = field(default_factory=list)


class BIPhase1Service:
    def __init__(self, duckdb_service: DuckDBService | None = None) -> None:
        self.store = BIPhase1Store()
        self._duckdb_service = duckdb_service
        self._connectors: dict[str, Connector] = {
            "duckdb": DuckDBFileConnector(duckdb_service),
            "parquet": ParquetConnector(),
            "csv_family": CSVConnector(),
        }

    def reset(self) -> None:
        self.store = BIPhase1Store()

    @staticmethod
    def require_role(role: Role, allowed: set[Role]) -> None:
        if role not in allowed:
            raise PermissionError("Insufficient role for this action.")

    @staticmethod
    def _make_id(prefix: str) -> str:
        return f"{prefix}_{uuid4().hex[:10]}"

    @staticmethod
    def _normalize_table_name(value: str) -> str:
        collapsed = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_")
        return (collapsed or "dataset").lower()

    @staticmethod
    def _infer_field_role(dtype: str) -> Literal["dimension", "measure", "attribute"]:
        lowered = dtype.lower()
        if any(keyword in lowered for keyword in NUMERIC_TYPE_KEYWORDS):
            return "measure"
        if any(keyword in lowered for keyword in DATE_TYPE_KEYWORDS):
            return "dimension"
        return "attribute"

    def _audit(self, actor: str, action: str, target: str) -> None:
        self.store.audits.append(
            AuditEvent(at=datetime.now(UTC).isoformat(), actor=actor, action=action, target=target)
        )

    @staticmethod
    def _normalize_preview_value(value: Any) -> Any:
        if hasattr(value, "item"):
            try:
                return value.item()
            except Exception:
                return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    def _resolve_connector(self, location: str, requested_type: str = "auto") -> tuple[DataSourceType, Connector]:
        lowered = location.lower().strip()
        if not lowered:
            raise ValueError("Source location is required.")

        if requested_type != "auto":
            connector_key = "csv_family" if requested_type in {"csv", "tsv", "json", "csv_gz", "json_gz"} else requested_type
            connector = self._connectors.get(connector_key)
            if connector is None:
                raise ValueError(f"Unsupported source type '{requested_type}'.")
            return requested_type, connector

        if self._connectors["duckdb"].detect(location):
            return "duckdb", self._connectors["duckdb"]
        if self._connectors["parquet"].detect(location):
            return "parquet", self._connectors["parquet"]
        if lowered.endswith(".json"):
            return "json", self._connectors["csv_family"]
        if lowered.endswith(".json.gz"):
            return "json_gz", self._connectors["csv_family"]
        if lowered.endswith(".tsv"):
            return "tsv", self._connectors["csv_family"]
        if lowered.endswith(".csv.gz"):
            return "csv_gz", self._connectors["csv_family"]
        if self._connectors["csv_family"].detect(location):
            return "csv", self._connectors["csv_family"]

        raise ValueError("Could not detect a supported source type from the selected file.")

    def _build_source_insight(self, source_id: str, source_type: DataSourceType, connector: Connector, location: str, status: str) -> dict[str, Any]:
        schema_rows = connector.infer_schema(location)
        preview_rows = [
            {
                key: self._normalize_preview_value(value)
                for key, value in row.items()
            }
            for row in connector.preview(location, limit=5)
        ]
        load_strategy = connector.load_to_engine(location)
        return {
            "source_id": source_id,
            "detected_type": source_type,
            "capabilities": connector.capabilities(),
            "schema": [{"name": str(item["name"]), "type": str(item["type"])} for item in schema_rows],
            "preview_rows": preview_rows,
            "status": status,
            "last_sync": datetime.now(UTC).isoformat(),
            "load_strategy": load_strategy,
        }

    def create_workspace(self, actor: str, role: Role, workspace: Workspace) -> Workspace:
        self.require_role(role, {"Admin", "Editor"})
        self.store.workspaces[workspace.id] = workspace
        self._audit(actor, "workspace.create", workspace.id)
        return workspace

    def register_source(self, actor: str, role: Role, source: DataSource) -> DataSource:
        self.require_role(role, {"Admin", "Editor"})
        if source.workspace_id not in self.store.workspaces:
            raise KeyError(f"Workspace '{source.workspace_id}' was not found.")

        detected_type, connector = self._resolve_connector(source.location, source.source_type)
        source.source_type = detected_type
        self.store.data_sources[source.id] = source
        self.store.source_registry[source.id] = self._build_source_insight(
            source.id,
            detected_type,
            connector,
            source.location,
            source.status,
        )
        self._audit(actor, "source.register", source.id)
        return source

    def create_dataset(self, actor: str, role: Role, dataset: Dataset) -> Dataset:
        self.require_role(role, {"Admin", "Editor"})
        if dataset.workspace_id not in self.store.workspaces:
            raise KeyError(f"Workspace '{dataset.workspace_id}' was not found.")
        if dataset.data_source_id not in self.store.data_sources:
            raise KeyError(f"Source '{dataset.data_source_id}' was not found.")

        source = self.store.data_sources[dataset.data_source_id]
        insight = self.store.source_registry.get(source.id)
        if insight is None:
            detected_type, connector = self._resolve_connector(source.location, source.source_type)
            insight = self._build_source_insight(source.id, detected_type, connector, source.location, source.status)
            self.store.source_registry[source.id] = insight

        self.store.datasets[dataset.id] = dataset
        table = Table(
            id=self._make_id("tbl"),
            dataset_id=dataset.id,
            name=self._normalize_table_name(dataset.name),
        )
        self.store.tables[table.id] = table

        for field in list(self.store.fields.values()):
            if field.table_id == table.id:
                self.store.fields.pop(field.id, None)

        for column in insight["schema"]:
            field = FieldModel(
                id=self._make_id("fld"),
                table_id=table.id,
                name=column["name"],
                data_type=column["type"],
                role=self._infer_field_role(column["type"]),
            )
            self.store.fields[field.id] = field

        self._audit(actor, "dataset.create", dataset.id)
        return dataset

    def publish_dataset(self, actor: str, role: Role, dataset_id: str) -> Dataset:
        self.require_role(role, {"Admin", "Editor"})
        dataset = self.store.datasets[dataset_id]
        dataset.published = True
        self._audit(actor, "dataset.publish", dataset_id)
        return dataset

    def create_metric(self, actor: str, role: Role, metric: Metric) -> Metric:
        self.require_role(role, {"Admin", "Editor"})
        if metric.dataset_id not in self.store.datasets:
            raise KeyError(f"Dataset '{metric.dataset_id}' was not found.")
        self.store.metrics[metric.id] = metric
        self._audit(actor, "metric.create", metric.id)
        return metric

    def create_chart(self, actor: str, role: Role, chart: Chart) -> Chart:
        self.require_role(role, {"Admin", "Editor"})
        if chart.dataset_id not in self.store.datasets:
            raise KeyError(f"Dataset '{chart.dataset_id}' was not found.")
        self.store.charts[chart.id] = chart
        self._audit(actor, "chart.create", chart.id)
        return chart

    def create_dashboard(self, actor: str, role: Role, dashboard: Dashboard) -> Dashboard:
        self.require_role(role, {"Admin", "Editor"})
        if dashboard.workspace_id not in self.store.workspaces:
            raise KeyError(f"Workspace '{dashboard.workspace_id}' was not found.")
        for chart_id in dashboard.chart_ids:
            if chart_id not in self.store.charts:
                raise KeyError(f"Chart '{chart_id}' was not found.")
        self.store.dashboards[dashboard.id] = dashboard
        self._audit(actor, "dashboard.create", dashboard.id)
        return dashboard

    def get_state(self) -> BIPhase1StateResponse:
        source_insights = [
            BIPhase1SourceInsightResponse(**insight)
            for insight in self.store.source_registry.values()
        ]
        audits = [
            BIPhase1AuditEventResponse(at=item.at, actor=item.actor, action=item.action, target=item.target)
            for item in self.store.audits
        ]
        return BIPhase1StateResponse(
            workspaces=list(self.store.workspaces.values()),
            data_sources=list(self.store.data_sources.values()),
            datasets=list(self.store.datasets.values()),
            tables=list(self.store.tables.values()),
            fields=list(self.store.fields.values()),
            metrics=list(self.store.metrics.values()),
            charts=list(self.store.charts.values()),
            dashboards=list(self.store.dashboards.values()),
            source_insights=source_insights,
            audits=audits,
        )
