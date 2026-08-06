"""SQL expressions for the CSV→Parquet enrichment stage.

The enrichment used to be a pandas implementation that loaded each whole file
into memory (~900 B/row) and ran alongside a *separate* DuckDB implementation
for the non-enrichment case, so the two produced structurally different parquet.
Everything here is the single SQL definition both paths now share: DuckDB reads,
joins, derives and writes in one streaming statement, and the row counts come
back from ``COPY`` for free.

Column-name handling is deliberately verbose because the source files are not
schema-stable — every derivation checks whether its inputs are present.
"""

from __future__ import annotations

from backend.api.endpoints.mercados_schema import MERCADOS_SCHEMA

ACCT_ID_WIDTH = 10

# Lookup relations registered on the connection by the caller.
HIR_DIV_RELATION = "lu_hir_div"
HIR_SDO_RELATION = "lu_hir_sdo"
SUPP_RELATION = "lu_supp"

HIR_DIV_KEY = "DIV_CODE"
HIR_SDO_KEY = "SUB_DIV_CODE"
SUPP_KEY = "SUPPLY_TYPE"

# pandas' merge suffixes. A source column that collides with a lookup column
# becomes <col>_x (source) and <col>_y (lookup); this port keeps that naming so
# the master table's columns do not change underneath existing queries.
SUFFIX_LEFT = "_x"
SUFFIX_RIGHT = "_y"


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def normalize_expr(col_sql: str) -> str:
    """SQL twin of ``_normalize_identifier_like_series``.

    NULL → '', trim whitespace, and drop a trailing ``.0`` left behind when a
    numeric-looking identifier round-tripped through a float.
    """
    trimmed = f"trim(coalesce(CAST({col_sql} AS VARCHAR), ''))"
    return f"regexp_replace({trimmed}, '^(-?\\d+)\\.0+$', '\\1')"


def acct_id_normalize_expr(col_sql: str) -> str:
    """Normalize an ACCT_ID to bare digits, before validation and padding.

    Account ids are strings, not numbers. Strips whitespace and thousands
    separators, then the ``.0`` a float round-trip leaves behind.
    """
    stripped = f"regexp_replace(trim(coalesce(CAST({col_sql} AS VARCHAR), '')), '[,\\s]', '', 'g')"
    return f"regexp_replace({stripped}, '^(\\d+)\\.0+$', '\\1')"


def acct_id_status_expr(normalized_sql: str) -> str:
    """'OK', or the reason this account id cannot be used."""
    return (
        "CASE "
        f"WHEN {normalized_sql} = '' THEN 'ACCT_ID_BLANK' "
        f"WHEN NOT regexp_full_match({normalized_sql}, '\\d+') THEN 'ACCT_ID_NON_NUMERIC' "
        f"WHEN length({normalized_sql}) > {ACCT_ID_WIDTH} THEN 'ACCT_ID_TOO_LONG' "
        "ELSE 'OK' END"
    )


def acct_id_padded_expr(normalized_sql: str) -> str:
    """Left-pad to the canonical 10-digit width (matches merge_service's LPAD)."""
    return f"lpad({normalized_sql}, {ACCT_ID_WIDTH}, '0')"


def discom_case_expr(div_code_sql: str) -> str:
    """DIV_CODE prefix → owning DISCOM."""
    return (
        "CASE "
        f"WHEN starts_with({div_code_sql}, 'DIV1') THEN 'PVVNL' "
        f"WHEN starts_with({div_code_sql}, 'DIV2') THEN 'DVVNL' "
        f"WHEN starts_with({div_code_sql}, 'DIV3') THEN 'MVVNL' "
        f"WHEN starts_with({div_code_sql}, 'DIV4') THEN 'PuVNL' "
        f"WHEN starts_with({div_code_sql}, 'DIV5') THEN 'KESCO' "
        "ELSE NULL END"
    )


def category_case_expr(supply_type_sql: str) -> str:
    """SUPPLY_TYPE → CATEGORY, mirroring the Oracle-side rules.

    H-prefixed → 'HV-<digit>'; 100-107 → 'LMV-10'; '11'+letters → 'LMV-11';
    other numeric → 'LMV-<first digit>'; anything else → 'UNMAPPED'.
    """
    trimmed = f"trim(CAST({supply_type_sql} AS VARCHAR))"
    leading = f"regexp_extract({trimmed}, '^[0-9]+')"
    return (
        "CASE "
        f"WHEN {trimmed} LIKE 'H%' THEN 'HV-' || regexp_extract({trimmed}, '^H(\\d)', 1) "
        f"WHEN length({leading}) = 3 AND {leading} LIKE '10%' THEN 'LMV-10' "
        f"WHEN {leading} = '11' AND regexp_extract({trimmed}, '[A-Z]+$') != '' THEN 'LMV-11' "
        f"WHEN {leading} != '' THEN 'LMV-' || substr({leading}, 1, 1) "
        "ELSE 'UNMAPPED' END"
    )


def load_kw_expr(load_sql: str, unit_sql: str) -> str:
    """Normalize a connected load to kW from its stated unit."""
    load_num = f"round(TRY_CAST({load_sql} AS DOUBLE), 0)"
    unit = f"upper(trim(CAST({unit_sql} AS VARCHAR)))"
    return (
        "CASE "
        f"WHEN {unit} = 'KW' THEN {load_num} "
        f"WHEN {unit} = 'KVA' THEN {load_num} * 0.9 "
        f"WHEN {unit} IN ('HP', 'BHP') THEN {load_num} * 0.746 "
        "ELSE NULL END"
    )


def schema_cast_expr(col: str, source_sql: str) -> str:
    """Apply the MERCADOS_SCHEMA type for *col* to *source_sql*."""
    dtype = str(MERCADOS_SCHEMA.get(col, "")).upper()
    if dtype == "NUMBER":
        # TRY_CAST so one bad cell nulls a value instead of failing the file.
        return f"TRY_CAST({source_sql} AS DOUBLE)"
    if dtype == "DATE":
        return source_sql
    return normalize_expr(source_sql)


def build_enrichment_sql(
    relation_sql: str,
    col_names: list[str],
    *,
    month_label: str,
    enriched: bool,
    hir_div_columns: tuple[str, ...] = (),
    hir_sdo_columns: tuple[str, ...] = (),
    supp_columns: tuple[str, ...] = (),
    row_status_filter: str | None = "OK",
) -> str:
    """Build the full enrichment SELECT for one CSV source.

    Mirrors three sequential pandas ``merge(how="left")`` calls, including their
    ``_x``/``_y`` suffixing when a source column collides with a lookup column.
    That naming is load-bearing: it is what the existing master table columns are
    called, so queries against them keep working.

    Args:
        relation_sql:      A ``read_csv(...)`` relation.
        col_names:         Columns present in the source, in file order.
        month_label:       Value for the derived MONTH column.
        enriched:          Whether the lookup relations are registered and joined.
        hir_div_columns:   Actual columns of the HIR division lookup.
        hir_sdo_columns:   Actual columns of the HIR sub-division lookup.
        supp_columns:      Actual columns of the supply-type lookup.
        row_status_filter: Keep only rows whose ACCT_ID status equals this; pass
                           ``None`` to keep everything.

    Returns:
        A SELECT statement whose column order matches the pandas implementation.
    """
    present = set(col_names)
    has = present.__contains__

    # ── Stage 1: normalise the join/identity keys ────────────────────────────
    src_cols = [f"s.{quote_ident(col)} AS {quote_ident(col)}" for col in col_names]

    def src(col: str) -> str:
        return f"s.{quote_ident(col)}"

    derived_pre: list[str] = []
    if has("BILLED_AMOUNT") and not has("TOTAL_AMT"):
        derived_pre.append(f'TRY_CAST({src("BILLED_AMOUNT")} AS DOUBLE) AS "TOTAL_AMT"')
    if has("SDO_CODE") and not has("SUB_DIV_CODE"):
        derived_pre.append(f'{normalize_expr(src("SDO_CODE"))} AS "SUB_DIV_CODE"')

    acct_norm = acct_id_normalize_expr(src("ACCT_ID")) if has("ACCT_ID") else "''"
    normalized = [
        f"{acct_norm} AS __acct_norm",
        f"{acct_id_status_expr(acct_norm)} AS __row_status",
    ]
    if has("DIV_CODE"):
        normalized.append(f'{normalize_expr(src("DIV_CODE"))} AS __div_code')
    if has("SUPPLY_TYPE"):
        normalized.append(f'{normalize_expr(src("SUPPLY_TYPE"))} AS __supply_type')

    base_select = ", ".join(src_cols + derived_pre + normalized)
    base = f"SELECT {base_select} FROM {relation_sql} s"

    # SUB_DIV_CODE may come from the source or from the SDO_CODE derivation above.
    has_sub_div = has("SUB_DIV_CODE") or (has("SDO_CODE") and not has("SUB_DIV_CODE"))

    # ── Stage 2: project, join and derive ────────────────────────────────────
    out_cols = list(col_names)
    if has("BILLED_AMOUNT") and not has("TOTAL_AMT"):
        out_cols.append("TOTAL_AMT")
    if has("SDO_CODE") and not has("SUB_DIV_CODE"):
        out_cols.append("SUB_DIV_CODE")

    # `frame` tracks (output name -> SQL source) in pandas column order, so the
    # merges below can rename in place exactly the way pandas does.
    frame: list[tuple[str, str]] = []
    for col in col_names:
        if col == "ACCT_ID":
            frame.append((col, acct_id_padded_expr("b.__acct_norm")))
        elif col == "DIV_CODE":
            frame.append((col, "b.__div_code"))
        elif col == "SUPPLY_TYPE":
            frame.append((col, "b.__supply_type"))
        else:
            frame.append((col, f"b.{quote_ident(col)}"))
    if has("BILLED_AMOUNT") and not has("TOTAL_AMT"):
        frame.append(("TOTAL_AMT", 'b."TOTAL_AMT"'))
    if has("SDO_CODE") and not has("SUB_DIV_CODE"):
        frame.append(("SUB_DIV_CODE", 'b."SUB_DIV_CODE"'))

    joins: list[str] = []

    def _merge(alias: str, key: str, lookup_columns: tuple[str, ...]) -> None:
        """Apply one LEFT JOIN, replicating pandas' _x/_y suffix collision rule."""
        incoming = [col for col in lookup_columns if col != key]
        existing = {name for name, _ in frame}
        overlapping = {col for col in incoming if col in existing}
        if overlapping:
            for index, (name, source) in enumerate(frame):
                if name in overlapping:
                    frame[index] = (f"{name}{SUFFIX_LEFT}", source)
        for col in incoming:
            out_name = f"{col}{SUFFIX_RIGHT}" if col in overlapping else col
            frame.append((out_name, f"{alias}.{quote_ident(col)}"))

    if enriched and has("DIV_CODE") and hir_div_columns:
        joins.append(f"LEFT JOIN {HIR_DIV_RELATION} hd ON hd.{HIR_DIV_KEY} = b.__div_code")
        _merge("hd", HIR_DIV_KEY, hir_div_columns)
    if enriched and has_sub_div and hir_sdo_columns:
        joins.append(
            f"LEFT JOIN {HIR_SDO_RELATION} hs ON hs.{HIR_SDO_KEY} = b.{quote_ident('SUB_DIV_CODE')}"
        )
        _merge("hs", HIR_SDO_KEY, hir_sdo_columns)
    if enriched and has("SUPPLY_TYPE") and supp_columns:
        joins.append(f"LEFT JOIN {SUPP_RELATION} sp ON sp.{SUPP_KEY} = b.__supply_type")
        _merge("sp", SUPP_KEY, supp_columns)

    def _assign(name: str, source: str) -> None:
        """``df[name] = ...`` — replace in place if present, else append."""
        for index, (existing, _) in enumerate(frame):
            if existing == name:
                frame[index] = (name, source)
                return
        frame.append((name, source))

    # DISCOM is always re-derived from DIV_CODE, overriding whatever the source or
    # the lookup supplied (the pandas path did the same with np.select).
    if has("DIV_CODE"):
        _assign("DISCOM", discom_case_expr("b.__div_code"))
    if has("SUPPLY_TYPE"):
        _assign("CATEGORY", category_case_expr("b.__supply_type"))

    load = 'b."LOAD"' if has("LOAD") else "NULL"
    unit = 'b."LOAD_UNIT"' if has("LOAD_UNIT") else "NULL"
    _assign("LOAD_KW", load_kw_expr(load, unit))
    _assign("MONTH", sql_literal(month_label))

    # Every column goes through the MERCADOS_SCHEMA cast, including the derived
    # ones. LOAD_KW and TOTAL_AMT are absent from that schema, so they land as
    # normalised strings — which is what the pandas implementation produced, and
    # this port is deliberately behaviour-preserving. Typing them properly is a
    # separate decision because it changes the master table's column types.
    projected = [
        f"{schema_cast_expr(name, source)} AS {quote_ident(name)}" for name, source in frame
    ]

    where = ""
    if row_status_filter is not None:
        where = f" WHERE b.__row_status = {sql_literal(row_status_filter)}"

    join_sql = (" " + " ".join(joins)) if joins else ""
    return f"SELECT {', '.join(projected)} FROM ({base}) b{join_sql}{where}"


def build_row_status_count_sql(relation_sql: str, col_names: list[str]) -> str:
    """Count source rows per ACCT_ID status — the basis of the row accounting."""
    acct_norm = acct_id_normalize_expr('s."ACCT_ID"') if "ACCT_ID" in col_names else "''"
    return (
        f"SELECT {acct_id_status_expr(acct_norm)} AS status, count(*) AS n "
        f"FROM {relation_sql} s GROUP BY 1"
    )


def build_rejects_sql(relation_sql: str, col_names: list[str]) -> str:
    """Select the rejected rows verbatim, plus the reason, for quarantine."""
    acct_norm = acct_id_normalize_expr('s."ACCT_ID"') if "ACCT_ID" in col_names else "''"
    cols = ", ".join(f"CAST(s.{quote_ident(col)} AS VARCHAR) AS {quote_ident(col)}" for col in col_names)
    status = acct_id_status_expr(acct_norm)
    return (
        f"SELECT {cols}, {status} AS __reject_reason "
        f"FROM {relation_sql} s WHERE {status} <> 'OK'"
    )
