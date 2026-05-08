from backend.models.bi_entities import Chart, Dashboard, DataSource, Dataset, Metric, Workspace
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


def test_phase1_store_tracks_registry_and_audit(tmp_path) -> None:
    source_file = tmp_path / "source.csv"
    source_file.write_text("name,value\nNorth,1\n", encoding="utf-8")

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
            location=str(source_file),
        ),
    )
    assert service.store.source_registry["src1"]["status"] == "active"
    assert len(service.store.audits) == 2


def test_dataset_creation_populates_schema_fields(tmp_path) -> None:
    source_file = tmp_path / "sales.csv"
    source_file.write_text("region,amount,bill_date\nNorth,10,2026-05-01\n", encoding="utf-8")

    service = BIPhase1Service()
    service.create_workspace("agent", "Admin", Workspace(id="ws1", name="Main"))
    service.register_source(
        "agent",
        "Editor",
        DataSource(
            id="src1",
            workspace_id="ws1",
            name="Sales CSV",
            source_type="csv",
            location=str(source_file),
        ),
    )

    dataset = service.create_dataset(
        "agent",
        "Editor",
        Dataset(id="ds1", workspace_id="ws1", data_source_id="src1", name="Sales Dataset"),
    )

    assert dataset.id == "ds1"
    assert len(service.store.tables) == 1
    assert {field.name for field in service.store.fields.values()} == {"region", "amount", "bill_date"}
    assert any(field.role == "measure" for field in service.store.fields.values())


def test_chart_and_dashboard_are_persisted() -> None:
    service = BIPhase1Service()
    service.create_workspace("agent", "Admin", Workspace(id="ws1", name="Main"))
    service.store.datasets["ds1"] = Dataset(id="ds1", workspace_id="ws1", data_source_id="src1", name="Sales")
    service.store.metrics["met1"] = Metric(
        id="met1",
        dataset_id="ds1",
        name="Revenue",
        expression="SUM(amount)",
        aggregation="SUM",
    )

    chart = service.create_chart(
        "agent",
        "Editor",
        Chart(id="chart1", dataset_id="ds1", title="Revenue by region", chart_type="bar", metric_ids=["met1"]),
    )
    dashboard = service.create_dashboard(
        "agent",
        "Editor",
        Dashboard(id="dash1", workspace_id="ws1", name="Executive View", chart_ids=["chart1"]),
    )

    assert service.store.charts[chart.id].metric_ids == ["met1"]
    assert service.store.dashboards[dashboard.id].chart_ids == ["chart1"]
