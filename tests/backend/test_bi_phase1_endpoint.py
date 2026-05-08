from fastapi.testclient import TestClient

from backend.api.deps import get_bi_phase1_service
from backend.app import app


def test_bi_phase1_workspace_flow(tmp_path) -> None:
    source_file = tmp_path / "customers.csv"
    source_file.write_text("customer_id,region,total\n1,North,42\n2,South,55\n", encoding="utf-8")

    service = get_bi_phase1_service()
    service.reset()
    client = TestClient(app)

    workspace_response = client.post(
        "/api/bi-phase1/workspaces",
        json={"name": "Revenue Lab", "description": "Phase 1 validation workspace"},
    )
    assert workspace_response.status_code == 201
    workspace_id = workspace_response.json()["id"]

    source_response = client.post(
        "/api/bi-phase1/data-sources",
        json={
            "workspace_id": workspace_id,
            "name": "Customer CSV",
            "location": str(source_file),
            "source_type": "auto",
        },
    )
    assert source_response.status_code == 201
    source_id = source_response.json()["id"]
    assert source_response.json()["source_type"] == "csv"

    dataset_response = client.post(
        "/api/bi-phase1/datasets",
        json={
            "workspace_id": workspace_id,
            "data_source_id": source_id,
            "name": "Customer Revenue",
        },
    )
    assert dataset_response.status_code == 201
    dataset_id = dataset_response.json()["id"]

    metric_response = client.post(
        "/api/bi-phase1/metrics",
        json={
            "dataset_id": dataset_id,
            "name": "Total Revenue",
            "expression": "SUM(total)",
            "aggregation": "SUM",
        },
    )
    assert metric_response.status_code == 201
    metric_id = metric_response.json()["id"]

    state_after_dataset = client.get("/api/bi-phase1/state")
    assert state_after_dataset.status_code == 200
    fields = state_after_dataset.json()["fields"]
    total_field_id = next(field["id"] for field in fields if field["name"] == "total")

    chart_response = client.post(
        "/api/bi-phase1/charts",
        json={
            "dataset_id": dataset_id,
            "title": "Revenue by region",
            "chart_type": "bar",
            "field_ids": [total_field_id],
            "metric_ids": [metric_id],
        },
    )
    assert chart_response.status_code == 201
    chart_id = chart_response.json()["id"]

    dashboard_response = client.post(
        "/api/bi-phase1/dashboards",
        json={
            "workspace_id": workspace_id,
            "name": "Revenue Overview",
            "chart_ids": [chart_id],
        },
    )
    assert dashboard_response.status_code == 201

    publish_response = client.post(f"/api/bi-phase1/datasets/{dataset_id}/publish")
    assert publish_response.status_code == 200
    assert publish_response.json()["published"] is True

    state_response = client.get("/api/bi-phase1/state")
    assert state_response.status_code == 200
    payload = state_response.json()

    assert len(payload["workspaces"]) == 1
    assert len(payload["data_sources"]) == 1
    assert len(payload["datasets"]) == 1
    assert len(payload["metrics"]) == 1
    assert len(payload["charts"]) == 1
    assert len(payload["dashboards"]) == 1
    assert len(payload["source_insights"]) == 1
    assert payload["source_insights"][0]["schema"][0]["name"] == "customer_id"
    assert len(payload["audits"]) >= 6
