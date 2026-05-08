"""Phase 1 BI foundation service.

Implements foundational in-memory workflows for:
- workspace/data source/dataset metadata
- connector registry state
- semantic model entities
- dashboard/chart persistence
- basic role checks and audit logging hooks
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Literal

from backend.models.bi_entities import Chart, Dashboard, DataSource, Dataset, FieldModel, Metric, Table, Workspace

Role = Literal["Admin", "Editor", "Viewer"]


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
    source_registry: dict[str, dict[str, str]] = field(default_factory=dict)
    audits: list[AuditEvent] = field(default_factory=list)


class BIPhase1Service:
    def __init__(self) -> None:
        self.store = BIPhase1Store()

    @staticmethod
    def require_role(role: Role, allowed: set[Role]) -> None:
        if role not in allowed:
            raise PermissionError("Insufficient role for this action.")

    def _audit(self, actor: str, action: str, target: str) -> None:
        self.store.audits.append(
            AuditEvent(at=datetime.now(UTC).isoformat(), actor=actor, action=action, target=target)
        )

    def create_workspace(self, actor: str, role: Role, workspace: Workspace) -> Workspace:
        self.require_role(role, {"Admin", "Editor"})
        self.store.workspaces[workspace.id] = workspace
        self._audit(actor, "workspace.create", workspace.id)
        return workspace

    def register_source(self, actor: str, role: Role, source: DataSource) -> DataSource:
        self.require_role(role, {"Admin", "Editor"})
        self.store.data_sources[source.id] = source
        self.store.source_registry[source.id] = {"status": source.status, "last_sync": "never"}
        self._audit(actor, "source.register", source.id)
        return source

    def publish_dataset(self, actor: str, role: Role, dataset_id: str) -> Dataset:
        self.require_role(role, {"Admin", "Editor"})
        dataset = self.store.datasets[dataset_id]
        dataset.published = True
        self._audit(actor, "dataset.publish", dataset_id)
        return dataset
