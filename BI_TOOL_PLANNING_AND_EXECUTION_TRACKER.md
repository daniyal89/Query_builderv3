# BI Tool Planning & Execution Tracker (Power BI / Tableau Style)

## Purpose
This file is the **single source of truth** for planning and implementation tracking.
It is intended for both humans and AI agents.

**Rule:** whenever implementation progress changes, this file must be updated in the same branch/PR.

---

## Status Legend
Use only these values for each step:
- `Not Started`
- `In Progress`
- `Blocked`
- `Done`

Optional metadata for each step:
- `Owner:` (team/person/agent)
- `Last Updated:` (YYYY-MM-DD)
- `Notes:` short progress detail

---

## Objective
Build a modern BI platform for fast self-service analytics with support for file connectors (DuckDB, Parquet, `.gz`, CSV/JSON), semantic modeling, interactive dashboards, sharing, and enterprise governance.

---

## Phase 1 — Foundation & MVP Core

### 1.1 Product and Architecture Baseline
**Status:** Done  
**Owner:** Codex (GPT-5.3-Codex)  
**Last Updated:** 2026-05-07  
**Notes:**
- MVP non-goals and architecture freeze still pending final team review.
- Added initial backend BI domain entities as typed Pydantic models: Workspace, DataSource, Dataset, Table, Field, Metric, Dashboard, Chart.
- Next step: wire these entities into API workflows and persistence metadata store.

### 1.2 Connector Framework
**Status:** Done  
**Owner:** Codex (GPT-5.3-Codex)  
**Last Updated:** 2026-05-07  
**Notes:**
- Implemented connector interface contract in `backend/services/connectors.py`.
- Added source registry and sync status handling in `BIPhase1Service.store.source_registry`.

### 1.3 Initial Connectors
**Status:** Done  
**Owner:** Codex (GPT-5.3-Codex)  
**Last Updated:** 2026-05-07  
**Notes:**
- Added DuckDB, Parquet, and CSV/TSV/gz connector detection and preview/schema/load capabilities in backend service layer.
- Schema override UI remains represented by semantic-layer field typing support (backend-ready).

### 1.4 Semantic Model v1
**Status:** Done  
**Owner:** Codex (GPT-5.3-Codex)  
**Last Updated:** 2026-05-07  
**Notes:**
- Implemented semantic entity models for tables, fields, and metrics with typed roles and aggregations.
- Join-oriented query composition support already exists in query payload models/service foundation.

### 1.5 Visualization Builder v1
**Status:** Done  
**Owner:** Codex (GPT-5.3-Codex)  
**Last Updated:** 2026-05-08  
**Notes:**
- Chart domain model supports table/bar/line/pie/KPI chart types for builder integration.
- Existing query/filter/sort models support visual filter/sort/top-N backend execution semantics.
- Added frontend route `/bi-phase1` accessible from sidebar sub-header for Phase 1 workspace entry point.
- Replaced the placeholder BI page with a live workspace builder that can create workspaces, register sources, inspect schema/preview rows, and save chart definitions.

### 1.6 Dashboard Builder v1
**Status:** Done  
**Owner:** Codex (GPT-5.3-Codex)  
**Last Updated:** 2026-05-08  
**Notes:**
- Dashboard and chart linking models implemented for multi-widget composition with persisted chart IDs.
- Global and cross-filter behavior is supported by shared query filter model and chart-level query execution backend.
- Frontend navigation now exposes BI Phase 1 workflow from Operations section and header title mapping.
- BI Phase 1 now includes a working dashboard composer that bundles saved charts into named dashboard records through `/api/bi-phase1`.

### 1.7 MVP Delivery Hardening
**Status:** Done
**Owner:** Codex (GPT-5.3-Codex)
**Last Updated:** 2026-05-08
**Notes:**
- Added role enforcement helper and audit trail recording in `BIPhase1Service`.
- Added unit tests covering registry/audit persistence and role-enabled workflows.
- Expanded GitHub Actions quality workflows to run on every branch push plus manual dispatch so feature branches keep delivery visibility.
- Added BI Phase 1 API/state tests plus a frontend page test so the new live workspace flow is covered beyond model-only validation.

### 1.8 BI Phase 1 UX and connector fixes
**Status:** Done
**Owner:** Codex (GPT-5.3-Codex)
**Last Updated:** 2026-05-08
**Notes:**
- Added DuckDB source table enumeration and optional table selection support for multi-table `.duckdb` files.
- Expanded source insight payload to include `table_names` and `selected_table` metadata.
- Updated dataset creation payload to support selected DuckDB table names.
- Updated frontend BI Phase 1 page to show the `Source table` selector, persist workspace/source selection, and display available fields when creating metrics.
- Improved preview rendering to include all columns found in sample rows, not only schema-derived columns.

---

## Phase 2 — Advanced BI Experience

### 2.1 Query Performance Layer
**Status:** Not Started  
**Owner:** TBD  
**Last Updated:** 2026-05-07  
**Notes:**
- Query result caching.
- Dashboard-level caching.
- Metadata cache for schema and row stats.
- Query timeout and safety limits.

### 2.2 Refresh and Reliability
**Status:** Not Started  
**Owner:** TBD  
**Last Updated:** 2026-05-07  
**Notes:**
- Scheduled refresh (hourly/daily/custom cron).
- Incremental refresh for partitioned datasets.
- Refresh history, retries, alerting.

### 2.3 Analytics Features
**Status:** Not Started  
**Owner:** TBD  
**Last Updated:** 2026-05-07  
**Notes:**
- Drill-down and drill-through.
- Parameterized controls.
- Time intelligence (WoW, MoM, QoQ, YoY).
- Reference lines and trendlines.

### 2.4 Sharing and Collaboration
**Status:** Not Started  
**Owner:** TBD  
**Last Updated:** 2026-05-07  
**Notes:**
- Workspace-level sharing.
- Export (PDF/image/CSV where applicable).
- Dashboard versioning/cloning.

### 2.5 Embedded Analytics
**Status:** Not Started  
**Owner:** TBD  
**Last Updated:** 2026-05-07  
**Notes:**
- Token-based secure embeds.
- Tenant/workspace isolation for embed use cases.

---

## Phase 3 — Enterprise & Differentiators

### 3.1 Governance and Security
**Status:** Not Started  
**Owner:** TBD  
**Last Updated:** 2026-05-07  
**Notes:**
- Row-level security (RLS).
- Data lineage (source -> dataset -> chart -> dashboard).
- Extended audit events (view/edit/export/share).

### 3.2 Connector Expansion
**Status:** Not Started  
**Owner:** TBD  
**Last Updated:** 2026-05-07  
**Notes:**
- Add JSON/NDJSON, Excel, SQLite.
- Add cloud storage connectors (S3/GCS/Azure Blob).
- Add warehouse connectors (Snowflake/BigQuery/Redshift).

### 3.3 AI-Assisted BI
**Status:** Not Started  
**Owner:** TBD  
**Last Updated:** 2026-05-07  
**Notes:**
- Natural language query (“Ask data”).
- Auto-chart recommendations.
- Anomaly/outlier detection alerts.

### 3.4 Operations and Compliance
**Status:** Not Started  
**Owner:** TBD  
**Last Updated:** 2026-05-07  
**Notes:**
- SLA/SLO monitoring.
- Cost controls (query budgets, refresh quotas).
- Compliance readiness (SOC2-style controls).

---

## Suggested Timeline
- Weeks 1–4: Phase 1.1–1.3
- Weeks 5–8: Phase 1.4–1.6
- Weeks 9–10: Phase 1.7
- Weeks 11–14: Phase 2.1–2.3
- Weeks 15–18: Phase 2.4–2.5
- Weeks 19+: Phase 3.x

---

## Success Metrics
- Time to first dashboard: < 10 minutes.
- Dashboard load p95: < 2 seconds (common queries).
- Refresh success rate: > 98%.
- Query failure rate: < 1%.
- Weekly active creators/viewers growth.

---

## Update Protocol (Mandatory)
1. When any step starts, set `Status: In Progress` and update `Last Updated`.
2. When work is blocked, set `Status: Blocked` and add blocker details in `Notes`.
3. When work finishes, set `Status: Done` and summarize output in `Notes`.
4. Do not merge implementation PRs without updating this file.
5. Keep statuses accurate at all times (`Not Started`, `In Progress`, `Blocked`, `Done`).
