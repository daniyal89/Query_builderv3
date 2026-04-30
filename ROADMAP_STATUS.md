# Query Builder Project Roadmap & Execution Status

_Last updated: 2026-04-30 (UTC) - frontend test stack implemented, legacy upload guards added, CASE support marked implemented, and subquery remains deferred._

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
- `[In Progress]` Backend tests expanded for sidebar tools and build/parquet flows.
- `[Blocked]` Async/background job test process teardown noise is still observed in the local agent environment.
- `[Done]` Frontend Vitest + React Testing Library + MSW harness is now installed under `frontend/tests/`.
- `[Done]` Real frontend coverage now exists for Home connect flow, Query Builder execution flow, and Folder Merge/import flow.
- `[Not Started]` Full CI gate stack is still pending.

---

## Sprint 4 - Scale Architecture

**Goal:** production-grade job orchestration and resilience.

### Planned items
- Move in-memory job maps to persistent worker queue/store.
- Retry + dead-letter strategy.
- Environment profile hardening (`.env.example`, local/dev/prod docs).

### Current status
- `[Not Started]` Persistent queue/store architecture has not been started.

---

## Cross-cutting Git / Release Progress

### Branch/merge state (current workspace)
- Active branch currently: `main`.
- Worktree currently contains local roadmap implementation changes that are not yet committed.
- Latest verified local state includes passing frontend tests/build and targeted backend hardening tests.
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
- `[Not Started]` Performance and DX roadmap items have not been started.

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
- `[In Progress]` Path-safety validation now covers local folder-merge paths, importer temp-file identifiers, and stricter importer target-table validation; broader endpoint coverage is still incomplete.
- `[Done]` Request body size limits are now enforced for `/api/parse-csv`, `/api/upload-sheets`, and `/api/enrich-data`.
- `[Not Started]` Rate limiting for heavy endpoints is not yet implemented.
- `[Not Started]` Google OAuth token lifecycle management beyond the local token cache is not yet implemented.

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
1. Finish remaining Sprint 6 items: broader endpoint path audit plus rate limiting for heavy endpoints.
2. Complete remaining Query Builder gaps except subquery: report-mode joins, repeated-table aliasing, and Marcadose report/pivot flow.
3. Improve SQL editor and results-grid DX/performance (syntax highlighting, virtualization, bundle/HMR cleanup).
4. Expand CI quality gates to execute the new frontend tests in addition to existing build validation.
5. Revisit controlled visual subquery support only after the above slices stabilize.
6. Start Sprint 4 persistent queue/store architecture after the app is better covered and hardened.
