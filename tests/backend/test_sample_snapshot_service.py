from backend.services.sample_snapshot_service import SampleSnapshotService


def test_select_oracle_source_object_prefers_discom_master() -> None:
    objects = [
        "MERCADOS.CM_MASTER_DATA_MAR_2026_PVVNL",
        "MERCADOS.CM_MASTER_DATA_MAR_2026_DVVNL",
        "MERCADOS.OTHER_VIEW",
    ]
    selected = SampleSnapshotService._select_oracle_source_object(objects)
    assert selected == "MERCADOS.CM_MASTER_DATA_MAR_2026_DVVNL"


def test_select_oracle_source_object_falls_back_to_any_master() -> None:
    objects = ["SCHEMA.VIEW_A", "SCHEMA.MASTER_TABLE_ARCHIVE", "SCHEMA.VIEW_B"]
    selected = SampleSnapshotService._select_oracle_source_object(objects)
    assert selected == "SCHEMA.MASTER_TABLE_ARCHIVE"


def test_select_oracle_source_object_uses_first_when_no_master() -> None:
    objects = ["SCHEMA.VIEW_A", "SCHEMA.VIEW_B"]
    selected = SampleSnapshotService._select_oracle_source_object(objects)
    assert selected == "SCHEMA.VIEW_A"
