# Query Builder Project Roadmap & Execution Status

_Last updated: 2026-08-04 (UTC) - **silent row loss in the CSV→Parquet→DuckDB pipeline is fixed**: the enrichment path was deleting every row with a non-numeric ACCT_ID (4 of 10 realistic values survived) and 100% of rows from any file lacking the column, while reporting success. ACCT_ID is now normalised and zero-padded to 10 digits with invalid rows quarantined and counted; every job reconciles `source = written + quarantined`; parquet writes are atomic and corrupt outputs are rebuilt rather than skipped forever; the build stages into a temp table so a failed build cannot destroy a good one. Enrichment moved from pandas to DuckDB SQL (27.9s → 3.5s, 90 MB → 0.1 MB on the real 103k-row file), pinned by a differential test. Added `backend/tools/audit_rows.py` to measure what past months lost. Backend `143 passed`, frontend `20 passed`, build and lint clean._

_Earlier on 2026-08-04: backend suite passes end-to-end (`109 passed`); the query builder workspace, virtualized results grid, and background large-CSV export (DuckDB `COPY … TO`) are in place, along with local DuckDB alterations (`/api/alter-db/*`); sidebar tooling has been split into `backend/services/sidebar_tools_service.py` so the endpoint module is routes only; startup now uses a `lifespan` handler; a repository-hygiene pass untracked the committed OAuth client file (**secret still needs rotating**), pytest artifacts, and root data files. See "Cross-cutting - Cleanup & Tech Debt" and the 2026-08-04 handover section for detail._

_Previously (2026-05-01): frontend tests/build pass locally with dark mode baseline, new SQL highlighting, virtualized result rendering, route prefetching, and generated bundle reports; the frontend CI gate now runs both tests and build; the backend suite now passes locally end-to-end (`108 passed`) with the persistent job runtime in place for FTP, Drive, and Sidebar Tools; repeated-table join aliasing is implemented; Sprint 6 security hardening is functionally complete, including Google Drive logout/revoke UX; subquery remains deferred; Sprint 2 Data Tools UX consistency implementation continues with shared alert-component adoption in progress, including completed-job success summaries in Sidebar Tools._

## Status Legend
- `[Done]`
- `[In Progress]`
- `[Not Started]`
- `[Blocked]`

---

## Sprint 0 - Main Stabilization

**Goal:** keep `main` buildable and prevent broken merges.

### Planned items
- Frontend TypeScript build stability for `SidebarToolsPage` and Data Tools flow.
- Clean recovery instructions for local dev after bad merges/resets.
- CI gate to block merge when frontend build fails.

### Current status
- `[Done]` Frontend build passes locally in this workspace (`npm run build` in `frontend`).
- `[Done]` Frontend build gate workflow added (`.github/workflows/frontend-build-gate.yml`) for push/PR validation.
- `[Done]` Remote merge/release workflow completed by maintainer.

### Git execution status
- `[Done]` Local stabilization work from earlier slices exists in git history.
- `[Done]` Push/merge to remote `main` completed by maintainer release flow.

---

## Sprint 1 - Safety / Foundations

**Goal:** remove foundational tech debt and improve operational safety.

### Planned items
- Implement exception handler registration and normalized error envelope.
- Migrate Pydantic settings config to v2 `ConfigDict` style.
- Add request/job correlation IDs in logs and responses.
- Add dependency security automation (Dependabot + dependency review policy).

### Current status
- `[Done]` Custom exception handlers registered with consistent error envelope/status mapping.
- `[Done]` Pydantic settings config migrated to v2 `SettingsConfigDict`.
- `[Done]` Request correlation IDs now added to error responses and response headers (`X-Request-ID`).
- `[Done]` Dependency automation started (`.github/dependabot.yml`) and PR dependency review workflow added (`.github/workflows/dependency-review.yml`).

---

## Sprint 2 - UX Completion

**Goal:** complete visible TODO UI areas and standardize operational UX.

### Planned items
- Complete importer TODO components (`FileDropZone`, `ImportProgress`, `PreviewGrid`, `MappingTable`).
- Add global Axios response interceptor.
- Standardize status cards and error summaries across operational pages.

### Current status
- `[In Progress]` Data Tools UX polish is actively in execution for Sprint 2 completion (status cards/error-summary consistency and final workflow polish in progress).
- `[Done]` Importer component TODOs now exist with baseline UI behavior.
- `[Done]` Global API interceptor added in `frontend/src/api/client.ts` (normalized error + request-id extraction).

---

## Sprint 2.5 - CASE + Subquery Support (Query Builder)

**Goal:** support advanced SQL authoring in a controlled way.

### Planned items
- CASE expression builder (computed columns) in visual mode.
- Controlled subquery patterns (`IN (subquery)`, `EXISTS`) in advanced filters.
- Preserve manual SQL mode fallback for complex cases.

### Current status
- `[Done]` Manual SQL path exists and supports single-statement SQL with normalization guardrails.
- `[Done]` Visual CASE expression support is already implemented end-to-end (UI, payload/types, backend SQL builder).
- `[Done]` Visual builder now supports repeated joins against the same table through unique join references/aliases, and alias changes propagate through builder state.
- `[Done]` Report-mode join SQL and pivoted report shaping are verified for joined-column report rows/columns in backend tests.
- `[Blocked]` Subquery work is intentionally deferred until the user explicitly requests it.
- `[Blocked]` Controlled visual subquery patterns (`IN (subquery)`, `EXISTS`) remain intentionally unimplemented until user approval.

---

## Sprint 3 - Testing / Observability / CI

**Goal:** make regressions hard and operations observable.

### Planned items
- Replace frontend TODO test stubs with real RTL+MSW tests.
- Stabilize backend async job tests and teardown behavior.
- Add structured JSON logs + metrics + CI quality gates.

### Current status
- `[Done]` Backend temp-path, rate-limit, and sidebar/background-job test stabilization now allows the full backend suite to pass locally (`python -m pytest tests/backend` => `108 passed`).
- `[Done]` Shared pytest temp-root override and rate-limit reset fixtures removed the prior local agent-environment blockers for backend file-system-bound and heavy-endpoint tests.
- `[Done]` Focused persistent-job runtime tests now cover retry/dead-letter behavior, interrupted-job recovery, and snapshot persistence.
- `[Done]` Frontend Vitest + React Testing Library + MSW harness is now installed under `frontend/tests/`.
- `[Done]` Real frontend coverage now exists for Home connect flow, Query Builder execution flow, and Folder Merge/import flow.
- `[Done]` Frontend CI quality gate now runs both `npm test` and `npm run build` on push/PR via `.github/workflows/frontend-build-gate.yml`.
- `[Done]` Frontend lint gate now has a baseline ESLint v9 flat configuration (`frontend/eslint.config.js`) so CI lint execution is enforceable.
- `[Done]` Backend CI now runs the full `tests/backend` suite via `.github/workflows/backend-targeted-tests.yml`.
- `[In Progress]` Sprint 3 next-priority work is active: CI/observability expansion beyond current frontend/backend test-build gates is in progress.

---

## Sprint 4 - Scale Architecture

**Goal:** production-grade job orchestration and resilience.

### Planned items
- Move in-memory job maps to persistent worker queue/store.
- Retry + dead-letter strategy.
- Environment profile hardening (`.env.example`, local/dev/prod docs).

### Current status
- `[Done]` Persistent SQLite-backed job storage now replaces in-memory job maps for FTP Download, Google Drive upload/download, and Sidebar Tools background jobs.
- `[Done]` Retry attempt counters, dead-letter records, cancellation requests, and interrupted-job recovery are persisted through `backend/services/job_runtime.py`.
- `[Done]` App startup now initializes the runtime store, and the backend test harness isolates a fresh job-store file per test for deterministic coverage.
- `[Done]` Environment profile hardening is documented through `.env.example` and `ENVIRONMENT_PROFILES.md`.

---

## Cross-cutting Git / Release Progress

### Branch/merge state (current workspace)
- Active branch currently: `work` (local implementation branch).
- Worktree currently clean after latest implementation commits.
- Latest verified local state includes passing frontend tests/build, targeted backend hardening tests, and targeted backend query-builder/query-workflow tests.
- Latest verified local state now also includes a passing full backend suite (`python -m pytest tests/backend` => `108 passed`).
- Remote push/merge for Sprint 0 is reported completed by maintainer.

### Required release actions by maintainer
1. [Done] Selected fixes landed on a shareable branch.
2. [Done] Frontend build verified on maintainer side.
3. [Done] Branch pushed and merged into `main` by maintainer.
4. [Done] CI remains enabled to block frontend build failures.

---

## Sprint 5 - Performance & Developer Experience

**Goal:** improve daily development speed and end-user responsiveness for large datasets.

### Planned items
- Dark mode support (design tokens already use CSS custom properties).
- SQL syntax highlighting in the editor panel (Monaco or CodeMirror lite).
- Virtual scrolling / windowed rendering for large result grids.
- Frontend bundle analysis and code splitting for heavy pages (`SidebarToolsPage`, `FtpDownloadPage`).
- Reduce HMR cascade noise (observed excessive full-page reloads during dev).

### Current status
- `[Done]` SQL editor now has lightweight syntax highlighting with inline manual editing and tab indentation support.
- `[Done]` Large query results now use windowed row rendering in the results grid to reduce DOM cost on big result sets.
- `[Done]` Route-level lazy loading now includes hover/focus/idle prefetching so likely next pages warm before navigation.
- `[Done]` Frontend build now emits a generated bundle report at `frontend_dist/build-report.json`, and Vite chunking is split across `react-vendor`, `router-vendor`, `app-shell`, `query-builder`, `data-workflows`, `drive-ops`, and `operations`.
- `[Done]` Vite dev server now ignores generated/cache directories (`frontend_dist`, `__pycache__`, `.pytest_cache`) to reduce avoidable watch churn.
- `[Done]` Dark mode baseline is now available through a persisted shell-level toggle with global surface/text/form overrides.

---

## Sprint 6 - Security Hardening

**Goal:** eliminate credential leaks, harden file-system-bound endpoints, and add abuse prevention.

### Planned items
- Remove credential files (`cred`, `cred.pub`, `credential`, `credential.pub`) from project root and add to `.gitignore`.
- Add path traversal prevention to all file-system-bound endpoints (upload, browse, snapshot).
- Add request body size limits to upload endpoints.
- Rate limiting for heavy endpoints (FTP start, Drive start, query execution).
- Google OAuth token lifecycle management (expiry, refresh, revoke).

### Current status
- `[Done]` Credential files were removed from project root and gitignored.
- `[Done]` Path-safety validation now covers DuckDB connect, local object creation, importer/merge flows, FTP/Drive local path inputs, sidebar-tools file/glob inputs, and save-dialog suggestion sanitization.
- `[Done]` Request body size limits are now enforced for `/api/parse-csv`, `/api/upload-sheets`, and `/api/enrich-data`.
- `[Done]` Rate limiting now protects `/api/query`, `/api/query/preview`, `/api/ftp-download/start`, `/api/drive/auth/login`, `/api/drive/upload/start`, `/api/drive/download/start`, and the heavy Sidebar Tools build/conversion endpoints.
- `[Done]` Google OAuth lifecycle now covers refresh-on-use, explicit logout/revoke behavior, cached-token cleanup, and signed-in/signed-out status refresh in the Drive pages.

---

## Cross-cutting - Cleanup & Tech Debt

**Goal:** remove dead code, fix stale copy, and close hygiene gaps identified during audit.

| Item | Priority | Action | Status |
|------|----------|--------|--------|
| 4 stub TODO importer components (`FileDropZone`, `ImportProgress`, `PreviewGrid`, `MappingTable`) | High | Implement or delete | Done |
| Legacy `merge-sheets` conflict-resolution code path | Medium | Remove if confirmed unused | Done |
| Outdated Marcadose card text on HomePage ("lands in the next implementation series") | High | Update to reflect working state | Done |
| "SIDEBAR TOOL" label on FTP Download page | High | Remove or replace with user-facing label | Done |
| Missing global Axios response interceptor | Medium | Add unified toast/error handling | Done |
| `csv_to_prequat.py` typo file in project root | Low | Delete | Gitignored |
| `monthly.duckdb` / `test_data.duckdb` in project root | Low | Add to `.gitignore` | Gitignored |
| Credential files in project root | Critical | Remove and `.gitignore` | Done |
| Empty states in Query Builder (saved queries, history) lack icons/guidance | Medium | Add proper empty-state UI | Done |
| Merge & Enrich wizard missing step indicator | Medium | Add stepper/progress bar | Done |
| FTP password fields exposed as plaintext | High | Mask with `type="password"` | Done |
| `config/google_oauth_client.json` tracked in git despite `.gitignore` | Critical | Untrack; **rotate the client secret** | Untracked 2026-08-04 — rotation still pending |
| ~150 `test-tmp/` pytest artifacts + `samples/` tracked in git | Medium | Untrack (files stay on disk) | Done 2026-08-04 |
| Root data files (`BILLED_DVVNL_*.csv.gz/.parquet`, `*.duckdb`) tracked | Medium | Untrack and gitignore | Done 2026-08-04 |
| `old_results_grid.tsx` / `old_results_grid_utf8.tsx` stale root copies | Low | Delete | Done 2026-08-04 |
| Debug `print()` in query preview / alter-db / dialogs | Medium | Route through `app_logger` | Done 2026-08-04 |
| Deprecated `@app.on_event("startup")` | Medium | Migrate to `lifespan` | Done 2026-08-04 |
| `sidebar_tools.py` at 1,439 lines mixing routes and business logic | High | Extract `sidebar_tools_service.py` | Done 2026-08-04 |
| Silent `.env` precedence across three candidate paths | Low | Log which file supplied each value | Done 2026-08-04 |
| Time-dependent FTP test hardcoding `MAR_2026` | Medium | Derive month from `_expand_tokens` | Done 2026-08-04 |
| `useQueryBuilder.ts` (1,205) / `QueryBuilderWorkspace.tsx` (1,043) oversized | Medium | Split into focused hooks/components | Not started |
| Silent row loss: ACCT_ID filter dropped recoverable rows; missing column dropped 100% | Critical | Normalise + LPAD to 10; quarantine invalid rows with counts | Done 2026-08-04 |
| No row accounting anywhere (source→parquet→table never reconciled) | Critical | `ConversionLedger` + `reconciliation` + `data_quality` in job status and UI | Done 2026-08-04 |
| Crashed writes left 0-byte parquet that was then skipped forever | High | Atomic temp+rename; footer validation before reuse | Done 2026-08-04 |
| `DROP TABLE` before `CREATE TABLE AS` destroyed good tables on failure | High | Staging table + verified count + transactional swap | Done 2026-08-04 |
| Two divergent conversion branches (pandas vs DuckDB) with different output | High | Unified into `pipeline_sql.py`; differential test pins equivalence | Done 2026-08-04 |
| Retire `_apply_csv_enrichment_pandas` + differential test | Low | Delete after one clean production month on the SQL path | Pending |
| `LOAD_KW` / `TOTAL_AMT` stored as strings (absent from MERCADOS_SCHEMA) | Low | Decide whether to type them properly — changes master table column types | Not started |

---

## Recommended next execution order
1. Expand CI/observability beyond the current frontend/backend test and build gates (Sprint 3 priority now in progress).
2. Finish the remaining Sprint 2 Data Tools UX polish (actively in progress).
3. Keep controlled visual subquery support deferred/blocked until the user explicitly asks for it.


## Improvement Backlog (Post Sprint 3)

- [In Progress] Broaden frontend lint coverage from baseline JS rules to TypeScript + React-specific rules (implementation in progress with TS/React hooks lint config enabled and warning burn-down underway (now down to 7 warnings in local lint run)).
- [In Progress] Backend/frontend coverage artifacts are wired in CI and backend + frontend PR test annotations are now published from JUnit reports; frontend quality gate now uploads `frontend_dist/build-report.json` as a CI artifact for bundle observability.
- [Done] Unified CI meta-gate now runs frontend + backend quality jobs and requires both before merge (`.github/workflows/ci-meta-gate.yml`).
- [In Progress] Continue Data Tools UX consistency passes using shared status/alert patterns (latest: Sidebar Tools error summary now uses shared `StatusAlert`).
