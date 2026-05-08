import pytest
from pydantic import ValidationError

from backend.models.bi_entities import Chart, DataSource, Dataset, FieldModel, Metric, Workspace


def test_workspace_requires_non_empty_name() -> None:
    with pytest.raises(ValidationError):
        Workspace(id="ws_1", name="")


def test_datasource_defaults_status_active() -> None:
    source = DataSource(
        id="src_1",
        workspace_id="ws_1",
        name="Local parquet",
        source_type="parquet",
        location="/tmp/data",
    )
    assert source.status == "active"


def test_dataset_default_published_false() -> None:
    dataset = Dataset(
        id="ds_1",
        workspace_id="ws_1",
        data_source_id="src_1",
        name="Sales",
    )
    assert dataset.published is False


def test_metric_requires_expression() -> None:
    with pytest.raises(ValidationError):
        Metric(id="m_1", dataset_id="ds_1", name="Revenue", expression="")


def test_chart_type_is_limited() -> None:
    with pytest.raises(ValidationError):
        Chart(id="c_1", dataset_id="ds_1", title="Bad", chart_type="scatter")


def test_field_role_default_attribute() -> None:
    field = FieldModel(id="f_1", table_id="tbl_1", name="region", data_type="VARCHAR")
    assert field.role == "attribute"
