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
**Status:** Not Started  
**Owner:** TBD  
**Last Updated:** 2026-05-07  
**Notes:**
- Define MVP scope and non-goals.
- Freeze initial architecture (frontend, backend API, query engine, metadata store, scheduler).
- Define entities: Workspace, DataSource, Dataset, Table, Field, Metric, Dashboard, Chart.

### 1.2 Connector Framework
**Status:** Not Started  
**Owner:** TBD  
**Last Updated:** 2026-05-07  
**Notes:**
- Implement connector interface:
  - `detect(source)`
  - `preview(source, limit)`
  - `infer_schema(source)`
  - `load_to_engine(source, mode)`
  - `refresh(source, strategy)`
  - `capabilities()`
- Add source registry with status and last sync data.

### 1.3 Initial Connectors
**Status:** Not Started  
**Owner:** TBD  
**Last Updated:** 2026-05-07  
**Notes:**
- DuckDB file connector.
- Parquet file/folder connector.
- CSV/TSV connector.
- `.gz` connectors (`.csv.gz`, `.json.gz`).
- Schema override UI (type corrections before publish).

### 1.4 Semantic Model v1
**Status:** Not Started  
**Owner:** TBD  
**Last Updated:** 2026-05-07  
**Notes:**
- Table joins and relationship definitions.
- Dimensions and measures.
- Calculated fields + date hierarchy.

### 1.5 Visualization Builder v1
**Status:** Not Started  
**Owner:** TBD  
**Last Updated:** 2026-05-07  
**Notes:**
- Drag-and-drop field assignment.
- Charts: table, bar, line, pie, KPI.
- Visual filters/sorting/top-N.

### 1.6 Dashboard Builder v1
**Status:** Not Started  
**Owner:** TBD  
**Last Updated:** 2026-05-07  
**Notes:**
- Multi-widget dashboard canvas.
- Global filters.
- Cross-filtering between charts.

### 1.7 MVP Delivery Hardening
**Status:** Not Started  
**Owner:** TBD  
**Last Updated:** 2026-05-07  
**Notes:**
- Role-based access (Admin/Editor/Viewer).
- Basic audit logs.
- Save/load reliability checks.

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
