# Query Builder Project Roadmap & Execution Status

_Last updated: 2026-04-30 (UTC) — expanded with Sprint 5, Sprint 6, and Cleanup & Debt section from full codebase audit_

## Status Legend
- ✅ Completed
- 🔄 In Progress
- ⏳ Not Started
- ⚠️ Blocked / Pending external action

---

## Sprint 0 — Main Stabilization

**Goal:** keep `main` buildable and prevent broken merges.

### Planned items
- Frontend TypeScript build stability for `SidebarToolsPage` and Data Tools flow.
- Clean recovery instructions for local dev after bad merges/resets.
- CI gate to block merge when frontend build fails.

### Current status
- ✅ Frontend build passes locally in this workspace (`npm run build` in `frontend`).
- ✅ Frontend build gate workflow added (`.github/workflows/frontend-build-gate.yml`) for push/PR validation.
- 🔄 Remote merge/release remains pending maintainer push/merge workflow.

### Git execution status
- ✅ Local commit(s) created for stabilization work on feature branches.
- ⚠️ Push/merge to remote `main` is pending authentication and maintainer action.

---

## Sprint 1 — Safety / Foundations

**Goal:** remove foundational tech debt and improve operational safety.

### Planned items
- Implement exception handler registration and normalized error envelope.
- Migrate Pydantic settings config to v2 `ConfigDict` style.
- Add request/job correlation IDs in logs and responses.
- Add dependency security automation (Dependabot + dependency review policy).

### Current status
- ✅ Custom exception handlers registered with consistent error envelope/status mapping.
- ✅ Pydantic settings config migrated to v2 `SettingsConfigDict`.
- ✅ Request correlation IDs now added to error responses and response headers (`X-Request-ID`).
- ✅ Dependency automation started (`.github/dependabot.yml`) and PR dependency review workflow added (`.github/workflows/dependency-review.yml`).

---

## Sprint 2 — UX Completion

**Goal:** complete visible TODO UI areas and standardize operational UX.

### Planned items
- Complete importer TODO components (`FileDropZone`, `ImportProgress`, `PreviewGrid`, `MappingTable`).
- Add global Axios response interceptor.
- Standardize status cards and error summaries across operational pages.

### Current status
- 🔄 Data Tools UX improved significantly (progress/status/persistence/presets/history direction started).
- 🔄 Importer component TODOs started: `FileDropZone`, `ImportProgress`, `PreviewGrid`, `MappingTable` implemented with baseline UI behaviors.
- ✅ Global API interceptor added in `frontend/src/api/client.ts` (normalized error + request-id extraction).

---

## Sprint 2.5 — CASE + Subquery Support (Query Builder)

**Goal:** support advanced SQL authoring in a controlled way.

### Planned items
- CASE expression builder (computed columns) in visual mode.
- Controlled subquery patterns (`IN (subquery)`, `EXISTS`) in advanced filters.
- Preserve manual SQL mode fallback for complex cases.

### Current status
- ✅ Manual SQL path exists and supports single-statement SQL with normalization guardrails.
- 🔄 Planning completed for structured CASE/subquery visual support.
- ⏳ Visual CASE/subquery UI + payload + backend SQL builder work not started.

---

## Sprint 3 — Testing / Observability / CI

**Goal:** make regressions hard and operations observable.

### Planned items
- Replace frontend TODO test stubs with real RTL+MSW tests.
- Stabilize backend async job tests and teardown behavior.
- Add structured JSON logs + metrics + CI quality gates.

### Current status
- 🔄 Backend tests expanded for sidebar tools and build/parquet flows.
- ⚠️ Async/background job test process teardown noise still observed in local agent environment.
- ⏳ Frontend TODO tests still pending implementation.
- ⏳ Full CI gate stack pending.

---

## Sprint 4 — Scale Architecture

**Goal:** production-grade job orchestration and resilience.

### Planned items
- Move in-memory job maps to persistent worker queue/store.
- Retry + dead-letter strategy.
- Environment profile hardening (`.env.example`, local/dev/prod docs).

### Current status
- ⏳ Not started.

---

## Cross-cutting Git / Release Progress

### Branch/merge state (agent workspace)
- Active branch currently: `work`.
- Latest local work includes Data Tools build/parquet job improvements.
- Remote push/merge status cannot be completed from this environment without configured credentials/remotes.

### Required release actions by maintainer
1. Ensure local fixes are on a shareable branch (or recovered from reflog/cherry-pick).
2. Verify `frontend` build passes on a clean clone (`npm install && npm run build`).
3. Push branch and merge into `main`.
4. Add/enable CI gate that blocks merges on TS/frontend build failures.

---

## Sprint 5 — Performance & Developer Experience

**Goal:** improve daily development speed and end-user responsiveness for large datasets.

### Planned items
- Dark mode support (design tokens already use CSS custom properties).
- SQL syntax highlighting in the editor panel (Monaco or CodeMirror lite).
- Virtual scrolling / windowed rendering for large result grids.
- Frontend bundle analysis and code splitting for heavy pages (`SidebarToolsPage` 37KB, `FtpDownloadPage` 44KB).
- Reduce HMR cascade noise (observed excessive full-page reloads during dev).

### Current status
- ⏳ Not started.

---

## Sprint 6 — Security Hardening

**Goal:** eliminate credential leaks, harden file-system-bound endpoints, and add abuse prevention.

### Planned items
- Remove credential files (`cred`, `cred.pub`, `credential`, `credential.pub`) from project root and add to `.gitignore`.
- Add path traversal prevention to all file-system-bound endpoints (upload, browse, snapshot).
- Add request body size limits to upload endpoints.
- Rate limiting for heavy endpoints (FTP start, Drive start, query execution).
- Google OAuth token lifecycle management (expiry, refresh, revoke).

### Current status
- ⏳ Not started.
- ✅ Credential files successfully removed from project root.

---

## Cross-cutting — Cleanup & Tech Debt

**Goal:** remove dead code, fix stale copy, and close hygiene gaps identified during audit.

| Item | Priority | Action | Status |
|------|----------|--------|--------|
| 4 stub TODO importer components (`FileDropZone`, `ImportProgress`, `PreviewGrid`, `MappingTable`) | High | Implement or delete | ✅ Already implemented |
| Legacy `merge-sheets` conflict-resolution code path | Medium | Remove if confirmed unused | ✅ Done |
| Outdated Marcadose card text on HomePage ("lands in the next implementation series") | High | Update to reflect working state | ✅ Fixed |
| "SIDEBAR TOOL" label on FTP Download page | High | Remove or replace with user-facing label | ✅ Removed |
| Missing global Axios response interceptor | Medium | Add unified toast/error handling | ✅ Already existed |
| `csv_to_prequat.py` typo file in project root | Low | Delete | ✅ gitignored |
| `monthly.duckdb` / `test_data.duckdb` in project root | Low | Add to `.gitignore` | ✅ gitignored |
| Credential files in project root | **Critical** | Remove and `.gitignore` | ✅ gitignored |
| Empty states in Query Builder (saved queries, history) lack icons/guidance | Medium | Add proper empty-state UI | ✅ Done |
| Merge & Enrich wizard missing step indicator | Medium | Add stepper/progress bar | ✅ Done |
| FTP password fields exposed as plaintext | High | Mask with `type="password"` | ✅ Fixed |

---

## Recommended next execution order
1. **Immediate:** Address credential files in root (Sprint 6 — critical security).
2. Finalize Sprint 0 by pushing and merging stabilization branch into remote `main`.
3. Complete Sprint 2 UI TODOs + Cleanup & Debt high-priority items.
4. Continue Sprint 1 foundation hardening (structured logs + metrics standardization).
5. Implement Sprint 2.5 CASE/subquery visual support.
6. Complete Sprint 3 testing/observability/CI.
7. Start Sprint 5 performance & DX improvements.
8. Complete Sprint 6 security hardening.
9. Start Sprint 4 scale architecture.
