from backend.models.query import MarcadoseUnionConfig
from backend.services.marcadose_union_service import MarcadoseUnionService


def _config() -> MarcadoseUnionConfig:
    return MarcadoseUnionConfig(
        enabled=True,
        month_tag="jan_2026",
        discoms=["DVVNL", "PVVNL"],
        base_discom="DVVNL",
        add_grand_total=False,
        schema_name="MERCADOS",
    )


def test_apply_rewrites_fetch_first_for_each_union_branch() -> None:
    sql = (
        "SELECT t0.\"DISCOM\" FROM MERCADOS.CM_master_data_jan_2026_DVVNL t0 "
        "WHERE t0.\"OPR_FLG\" = 'Y' FETCH FIRST 1000 ROWS ONLY"
    )
    transformed = MarcadoseUnionService.apply(sql, _config())

    assert "UNION ALL" in transformed
    assert "FETCH FIRST" not in transformed.upper()
    assert transformed.upper().count("ROWNUM <= 1000") == 2
    assert "SELECT * FROM (" not in transformed


def test_apply_keeps_non_union_queries_unchanged_except_placeholder_replacement() -> None:
    config = _config()
    config.enabled = False
    sql = "SELECT * FROM {{MASTER_TABLE}} FETCH FIRST 1000 ROWS ONLY"
    transformed = MarcadoseUnionService.apply(sql, config)

    assert "CM_master_data_jan_2026_DVVNL" in transformed
    assert "FETCH FIRST 1000 ROWS ONLY" in transformed


def test_apply_rownum_limit_wraps_branch_when_order_by_present() -> None:
    sql = "SELECT m.DISCOM FROM {{MASTER_TABLE}} m ORDER BY m.DISCOM FETCH FIRST 10 ROWS ONLY"
    transformed = MarcadoseUnionService.apply(sql, _config())

    assert "qb_branch_1" in transformed
    assert "ORDER BY m.DISCOM" in transformed
    assert transformed.upper().count("ROWNUM <= 10") == 2
