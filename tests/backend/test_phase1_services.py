from backend.models.bi_entities import DataSource, Workspace
from backend.services.bi_phase1_service import BIPhase1Service
from backend.services.connectors import CSVConnector, DuckDBFileConnector, ParquetConnector


def test_connector_detection_matrix() -> None:
    assert DuckDBFileConnector().detect("a.duckdb")
    assert ParquetConnector().detect("a.parquet")
    connector = CSVConnector()
    assert connector.detect("a.csv")
    assert connector.detect("a.tsv")
    assert connector.detect("a.csv.gz")
    assert connector.detect("a.json.gz")


def test_phase1_store_tracks_registry_and_audit() -> None:
    service = BIPhase1Service()
    service.create_workspace("agent", "Admin", Workspace(id="ws1", name="Main"))
    service.register_source(
        "agent",
        "Editor",
        DataSource(
            id="src1",
            workspace_id="ws1",
            name="CSV",
            source_type="csv",
            location="/tmp/a.csv",
        ),
    )
    assert service.store.source_registry["src1"]["status"] == "active"
    assert len(service.store.audits) == 2
