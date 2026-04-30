# Query Builder Project Roadmap & Execution Status

_Last updated: 2026-04-30 (UTC) - frontend tests/build pass locally with dark mode baseline, new SQL highlighting, virtualized result rendering, route prefetching, and generated bundle reports; the frontend CI gate now runs both tests and build; the backend suite now passes locally end-to-end (`108 passed`) with the persistent job runtime in place for FTP, Drive, and Sidebar Tools; repeated-table join aliasing is implemented; Sprint 6 security hardening is functionally complete, including Google Drive logout/revoke UX; subquery remains deferred._

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
- `[In Progress]` Remote merge/release remains pending maintainer push/merge workflow.

### Git execution status
- `[Done]` Local stabilization work from earlier slices exists in git history.
- `[Blocked]` Push/merge to remote `main` still depends on maintainer credentials and release flow.

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
- `[In Progress]` Data Tools UX improved significantly (progress/status/persistence/presets/history direction started).
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
- `[In Progress]` Subquery work is intentionally deferred for the current execution phase.
- `[Not Started]` Controlled visual subquery patterns (`IN (subquery)`, `EXISTS`) remain unimplemented.

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
- `[Done]` Backend CI now runs the full `tests/backend` suite via `.github/workflows/backend-targeted-tests.yml`.
- `[In Progress]` Full CI gate stack is still broader than frontend/backend tests and remains incomplete.

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
- Active branch currently: `main`.
- Worktree currently contains local roadmap implementation changes that are not yet committed.
- Latest verified local state includes passing frontend tests/build, targeted backend hardening tests, and targeted backend query-builder/query-workflow tests.
- Latest verified local state now also includes a passing full backend suite (`python -m pytest tests/backend` => `108 passed`).
- Remote push/merge status cannot be completed from this environment without configured credentials/remotes.

### Required release actions by maintainer
1. Ensure the selected fixes land on a shareable branch.
2. Verify `frontend` build passes on a clean clone (`npm install && npm run build`).
3. Push branch and merge into `main`.
4. Keep CI enabled to block merges on frontend/build failures.

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

---

## Recommended next execution order
1. Expand CI/observability beyond the current frontend/backend test and build gates if broader release confidence or operational visibility becomes the next priority.
2. Finish the remaining Sprint 2 Data Tools UX polish so the operational workflows feel as complete as the backend capabilities.
3. Revisit controlled visual subquery support only after the current frontend/backend stabilization holds up in regular usage.
