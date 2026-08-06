# Improvement plan: build performance, storage design, and UX

_Written 2026-08-04. Supersedes nothing; complements `FEATURE_IMPROVEMENT_PLAN.md`,
`UI_DESIGN_IMPROVEMENT_PLAN.md` and `BACKEND_VULNERABILITY_AND_LOGIC_IMPROVEMENT_PLAN.md`._

## Context

Two asks: **the DuckDB build takes too long**, and **suggest design improvements**. Everything
below was measured on the real production data rather than guessed, and the build finding reframes
the whole storage design.

### Measured: why the build is slow

| What | Measured |
|---|---|
| Full month build (46M rows, 577 parquet files) | **~41 min** (extrapolated from 5.1M rows in 272.9s on C:) |
| Effective write throughput | **4.5 MB/s** on C:, 2.9 MB/s on D: |
| Same CTAS into an **in-memory** DB | 10.9s vs 50s to disk → **~80% of build time is the storage write** |
| `SELECT *` with no casts at all | *Not faster* (55s vs 48s) → casts and `union_by_name` are **not** the bottleneck |
| `checkpoint_threshold='1GB'` | No effect (bulk CTAS bypasses the WAL entirely) |

4.5 MB/s is ~100× below what any SSD does, so this is **not disk bandwidth**. It is either a
per-write filter driver (Windows Defender real-time scanning) or storage-compression CPU.
Note D: is *slower* than C:, so moving the DB would make it worse — worth stating because it is
the intuitive "fix" that backfires.

### Measured: the storage design is the real problem

`C:\Users\aimld\uppcl_latest.duckdb` is **46.7 GB**: `Master_0326` (45.75M rows), `Master_0426`
(45.90M), `Master_0526` (46.08M), `Master_0626` (46.24M), plus two lookups — 184M rows.
`_normalize_master_object_name` mints a new `Master_MMYY` per month, so `DROP TABLE IF EXISTS`
never collides across months. The file grows **~11.7 GB/month and is never reclaimed** — there is
no `CHECKPOINT`, `VACUUM` or `ATTACH` anywhere in the codebase.

### Measured: what materialising actually buys

46M-row month, native table vs `read_parquet` over the same 577 files:

| query | native | parquet |
|---|---|---|
| `count(*)` | 0.02s | 0.35s |
| `GROUP BY DISCOM` | 0.10s | 0.35s |
| filter + `sum` | 0.10s | 0.34s |
| point lookup by `ACCT_ID` | 0.73s | 1.45s |
| `SELECT * LIMIT 100` | 0.26s | 1.00s |
| wide `GROUP BY` 3 cols + 3 aggs | 1.07s | 1.86s |
| `ORDER BY amount DESC LIMIT 100` | 0.12s | 1.94s |

**41 minutes and 11.7 GB per month to save 0.25–1.8s per query.**

### Confirmed correctness bug in the same path

Phase 1 writes `CATEGORY` into the parquet. Phase 2's `_build_select_sql_for_schema` emits
`CAST("CATEGORY" AS VARCHAR) AS "CATEGORY"` **and** appends a freshly-derived
`_category_case_sql()` (9 `REGEXP_EXTRACT` per row). DuckDB silently renames the second one.
Verified: the built table has both **`CATEGORY` and `CATEGORY_1`**. `DISCOM` is re-derived too but
not duplicated, because line 1288 drops the source column.

### Decisions taken

- **Hybrid storage**: build creates a **VIEW** over the month's parquet by default (~2s); a
  **Materialise** action writes that month to its own `uppcl_MMYY.duckdb`. Reclaiming space
  becomes deleting a file — the only thing that actually shrinks DuckDB storage.
- **Dark mode**: scope it down. Remove the harmful blanket override, fix the three worst
  surfaces, spend the saved days on polling/status/accessibility.

### Outcome

Monthly build goes from ~41 min to ~2s; ~47 GB reclaimed; the app stops freezing during builds;
job status stops lying about failures; the six copy-pasted job pollers become one correct hook.

---

## Phase 0 — Measure the 4.5 MB/s cause (1 hour, no code)

Everything in Phase 8 is contingent on this. Run the 12-file build and record:

1. Task Manager → Disk C: during the CTAS. **~100% active at 4.5 MB/s → Defender**;
   **disk idle, one core pegged → compression CPU**.
2. `SET force_compression='uncompressed'` — if 50s → ~15s, it is compression.
3. `SET disabled_compression_methods='fsst'` — FSST is the expensive string compressor and the
   schema is 83 VARCHAR + 13 CHAR columns. Record time *and* file size.
4. `duckdb.connect(path, config={'storage_compatibility_version':'latest'})` — the default is
   **`v0.10.2`**, five releases old, with newer compression disabled. Only settable at file creation.

**Windows Defender exclusion** is worth recommending *if* test 1 shows the signature — scoped to
the `.duckdb` path and temp dir, **not** the parquet tree (it receives FTP downloads). Needs IT
approval on a managed machine, so it cannot be the only fix.

Record results in `HANDOVER.md`.

---

## Phase 1 — `list_tables` is O(tables × COUNT) under a global lock (½ day, risk ~0)

`duckdb_service.py:120-132` runs `SELECT COUNT(*)` + an `information_schema.columns` query **per
table**, holding the service-wide `threading.Lock`. The Home page calls it on every load and after
every build reconnect, and the table count grows monthly.

Replace with three catalog queries: `duckdb_tables()` (`estimated_size` is the stored cardinality —
exact and free), `duckdb_views()`, `duckdb_columns()`. Keep exact counting behind a new
`GET /api/tables/{name}/row-count`. `duckdb_columns()` is keyed by `database_name`, so this is
already correct for the ATTACHed months in Phase 4.

---

## Phase 2 — Stop the build freezing the whole app (1 day, low risk)

Every DB endpoint is `async def` calling blocking code, so `build_duckdb`
(`api/endpoints/sidebar_tools.py:48`) runs a 41-minute CTAS **on the event loop** — freezing the UI,
static files, and even its own `/status/{job_id}` polling.

- Change `async def` → `def` in `schema.py`, `query.py`, `connection.py`, `sidebar_tools.py`,
  `export.py`, `local_object.py`, `merge.py`, `importer.py` where they call blocking code.
  Starlette then runs them in its threadpool. `alter_db.py` already does this — follow it.
- **Narrow the lock**: `DuckDBService.execute` holds `_lock` for the entire query and
  `export_to_csv` for the entire `COPY`. Take the lock only to obtain `self._conn.cursor()`, then
  run outside it, so a Home page load no longer queues behind a 10-minute export.
- **Narrow the disconnect window**: `_execute_build_duckdb:1114-1127` disconnects the dashboard for
  the whole build (every endpoint 503s) and **swallows a failed reconnect** at `:1181-1185`. With
  Phase 4 a view build writes a catalog entry in milliseconds and a materialise build writes a
  *different file*, so this mostly evaporates. Keep it guarded by `same_db`, surface the reconnect
  failure on `BuildOutcome`, and return a specific 409 rather than a bare 503 while a build runs.

Verify: `/api/health` responds within 1s while a slow query is in flight.

---

## Phase 3 — Fix `CATEGORY` / `CATEGORY_1` (½ day, low risk)

For parquet produced by this app's phase 1, the *entire* phase-2 select is redundant —
`pipeline_sql.schema_cast_expr` already applied the MERCADOS types and `_assign` already derived
`DISCOM` and `CATEGORY`. This matters doubly under Phase 4, because in a view those 9
`REGEXP_EXTRACT` per row would run on **every query**.

Give `_build_select_sql_for_schema` a `derive` mode:

```python
def _build_select_sql_for_schema(relation_sql, col_names, *,
                                 derive: str = "always",        # "always" | "if_missing"
                                 legacy_category_alias: bool = True) -> str:
    # "always"     : CSV source — re-derive DISCOM/CATEGORY, drop any source copy
    # "if_missing" : parquet from phase 1 — pass through, derive only what is absent
```

Never emit the source column *and* the derived one — that was the bug. Call sites: the build
(`:1134`) passes `derive="if_missing"`; the CSV→Parquet paths (`:1813`, `_run_csv_to_parquet_job`)
keep `"always"`.

Keep `SELECT *, "CATEGORY" AS "CATEGORY_1"` for one release so saved queries referencing either
name keep working (free in a view). Before dropping it, settle whether they were ever different:

```sql
SELECT count(*) FROM Master_0626 WHERE CATEGORY IS DISTINCT FROM CATEGORY_1;
```

---

## Phase 4 — Hybrid storage: views by default (1–2 days, medium risk) — the payoff

**New `uppcl_catalog.duckdb`** — permanently small. Holds one `VIEW Master_MMYY` per month, the
`HIR` / `hir_discom_lookup` tables, and a `_master_registry` table.

**4a. Views must use the glob, not a frozen file list.** `_resolve_relation_sql:818` returns
`read_parquet([<577 literals>])`. Baked into a view that is a 70 KB frozen list that never sees new
files. For the VIEW branch, embed the glob so it re-expands at bind time:

```python
view_relation = (f"read_parquet({_sql_string_literal(resolved_input)}, "
                 "union_by_name = true, hive_partitioning = false)")
conn.execute(f"CREATE OR REPLACE VIEW {object_sql} AS "
             f"{_build_select_sql_for_schema(view_relation, col_names, derive='if_missing')}")
```

Keep the expanded list for the materialise path (footer row-count verification needs it), and keep
the existing footer-vs-table row-count check — it costs 0.35s and catches a bad glob immediately.

**4b. `_master_registry`** — `object_name`, `month_label`, `kind` (`view` | `attached_table`),
`parquet_glob`, `parquet_files`, `row_count` (from footers at build time), `db_file`, `built_at`.
Feeds Home page row counts for views, the materialised badge, the connect-time path health check,
and the Phase 5 migration's resumability.

**4c. `DuckDBService.connect` session preamble:**

```python
conn.execute("SET parquet_metadata_cache = true")   # currently false — caches 577 footers
conn.execute("SET enable_external_file_cache = true")
conn.execute(f"SET temp_directory = {lit(runtime_tmp)}")   # default '.tmp' is CWD-relative
for name, db_file in registry_attached_months():
    conn.execute(f"ATTACH {lit(db_file)} AS {ident(name)} (READ_ONLY)")
conn.execute(f"SET search_path = {lit(','.join(['main'] + attached))}")
```

The `search_path` line keeps `SELECT * FROM Master_0326` resolving unqualified across attached
files, including cross-month joins.

**4d. Frontend** (`SidebarToolsPage.tsx:821`, `:986`): default to VIEW, relabel —
*Link to Parquet (recommended)* "instant, no extra disk, queries ~0.3–2s slower" vs
*Materialise* "~41 min, ~11.7 GB, own file".

**What breaks — state it plainly:**

1. **A view stores absolute parquet paths.** Rename the folder or re-letter the drive and that
   month's queries fail at bind. Mitigations: the registry records the glob; a connect-time health
   check stats one file per month and shows a banner; a "Repoint month" action; and
   `DASHBOARD_PARQUET_ROOT` so a drive-letter change is one setting.
2. **The parquet tree becomes the database of record** — back it up, not just the `.duckdb`.
3. **`alter_db` cannot ALTER a view.** Filter `get_alter_db_tables` (`alter_db.py:174`) to
   `duckdb_tables()` only, and have the page say "Materialise this month to alter it".
4. Saved queries are unaffected — names and columns stay the same (except `CATEGORY_1`, Phase 3).

**Verify before shipping:** create a view, close and reopen the DB, confirm `duckdb_columns()`
still returns its columns (the column picker depends on this entirely); diff the full saved-query
set against a materialised month; re-run the 7 benchmarks with `parquet_metadata_cache=true`.

---

## Phase 5 — Migrate the 46.7 GB file (1 day + soak, highest risk)

**Do not copy database-to-database** — `COPY FROM DATABASE` for 184M rows takes hours and needs
93 GB free. Re-point at the parquet you already have.

**Invariant: `uppcl_latest.duckdb` is opened read-only and never modified until sign-off.**

```
0  Preflight: ATTACH old READ_ONLY; per month compare estimated_size against
   SELECT sum(num_rows) FROM parquet_file_metadata('<glob>')
1  Create uppcl_catalog.duckdb with storage_compatibility_version='latest';
   copy HIR + hir_discom_lookup (1,815 + 1,814 rows)
2  Per month, resumable and registry-tracked:
   2a footers match -> CREATE VIEW, verify count(*), record DONE
   2b parquet missing/mismatched -> re-export from old, PARTITION_BY (DISCOM),
      verify on total count, per-DISCOM counts, and sum(TOTAL_AMT), then create the view
3  Cut over to uppcl_catalog.duckdb; old file untouched on disk
4  Soak one billing cycle, diffing a fixed query suite against both files
5  Delete uppcl_latest.duckdb — 46.7 GB back instantly
```

Do not start Phase 5 until Phase 4 has survived one real month's build.

---

## Phase 6 — One job poller, one status card (3 days, medium risk)

The single highest-value frontend change. The same polling loop exists **six times** with three
different bug sets:

| Site | Bug |
|---|---|
| `FtpDownloadPage.tsx:361-395` | cleanup never clears the pending `setTimeout`; **stops polling permanently on the first non-404 error** while the job runs on |
| `DriveDownloadPage.tsx:193-224`, `UploadMasterDrivePage.tsx:194-225` | identical |
| `SidebarToolsPage.tsx` ×3 (425, 472, 509) | correct-ish — has `isTransientPollError` — but three copies |
| `LocalDbAlterationsPage.tsx:183-200` | marks the job **`"failed"`** on any transient blip, during a destructive `DROP COLUMN` |
| `ExportModal.tsx:73-101` | `while` loop with no unmount exit — polls forever after close |

**`hooks/useJobPoller.ts`** — single scheduling source with the timer id in a ref and an
`AbortController`; transient tolerance (lift the existing `isTransientPollError`); 404 → `onMissing`;
non-transient retried to a threshold, and **never** forges a `"failed"` status of its own; stop on
terminal with `onTerminal` fired exactly once. It also supplies the 1 Hz `nowMs` tick, replacing six
duplicated clock effects.

**`components/common/JobStatusCard.tsx`** — one shell with tone derived from
`(status, failureCount)`. This fixes the dishonest cards: `FtpDownloadPage.tsx:708-719` shows an
emerald **"Download complete"** when `total_failed_files > 0`, and `SidebarToolsPage.tsx:727-733`
shows a green "Latest completed jobs" directly above a `RowReconciliation` reporting row loss.
`completed && failureCount > 0` → **amber**, "completed with N failure(s)". Build in
`role="status" aria-live="polite"` and `role="progressbar"` so all six job regions get announced.

Wire up telemetry that exists and is never rendered: `BuildDuckDbJobStatusResponse.data_quality`,
`row_delta`, `excluded_input_files`, `table_rows` (`sidebarToolsApi.ts:72-76`) — a build that drops
rows currently reports nothing; also `ExportCsvJobStatusResponse.last_error`.

Also `api/errors.ts`: `client.ts:28` sets `normalizedMessage` and `requestId` (from the
`X-Request-ID` the backend already sends) and **neither is ever read** — instead there are four
copies of `getErrorMessage` and ~20 inline `detail || message || "..."` chains, only one of which
understands the object-shaped `detail` that `/api/query` returns. Make the interceptor the single
source and delete the copies.

Migrate one page per commit, starting with `DriveDownloadPage` (it has a test). Add tests for the
four workflow pages that currently have none.

---

## Phase 7 — `alter_db` safety and service extraction (1 day, medium risk)

`api/endpoints/alter_db.py` holds its entire job worker and has **zero tests**.

- **`alter_db.py:79`**: `f"UPDATE {tbl} SET {col} = {request.sql_formula}"`. The formula is
  deliberately user SQL (there is a formula builder), so it cannot be parameterised — but DuckDB
  executes multi-statement strings, so a stray `;` in a pasted formula turns a typo into silent data
  loss. Layer: reject `;` outside string literals; reject a leading statement keyword; **dry-run**
  `SELECT ({formula}) AS probe FROM {tbl} LIMIT 0` before mutating; whitelist `column_type`; wrap
  ADD COLUMN + UPDATE in a transaction (today a failed UPDATE leaves an orphan all-NULL column).
- **`alter_db.py:53`** opens the same `.duckdb` `read_only=False` while the dashboard holds it → it
  fails in the normal workflow. Extract the disconnect/reconnect dance from
  `sidebar_tools_service.py:1116-1185` into `duckdb_handoff.exclusive_duckdb()` and use it in both.
- **`alter_db.py:186,209` and `merge.py:214`** execute on `DuckDBService._conn` **without the lock**.
  Add `DuckDBService.borrow_connection()` (a context manager holding `_lock`) and use it.
- Extract `backend/services/alter_db_service.py`; add `tests/backend/test_alter_db.py`.

---

## Phase 8 — Make materialising fast and observable (1–2 days, gated on Phase 0)

Only for months the user chooses to materialise.

**Real progress and real cancellation.** Today the job jumps 25% → silence for 41 minutes → 100%,
and `is_cancelled` is checked only before and after the CTAS, so Stop does nothing. Replace the
single `CREATE TABLE AS` with a batched load — `CREATE TABLE … LIMIT 0`, then
`INSERT INTO … BY NAME` per batch of files, checking cancellation and reporting rows between
batches. This gives progress every few minutes, working cancellation, bounded memory, and a crash
loses one batch instead of everything.

**Levers, honestly classified:**

| Lever | Status |
|---|---|
| `checkpoint_threshold`, CHECKPOINT placement | **Measured: no effect** (bulk CTAS bypasses the WAL) |
| Per-column casts, `union_by_name` | **Measured: not the bottleneck** |
| DB on the same drive as parquet | **Measured: worse** (D: 2.9 MB/s vs C: 4.5) |
| `memory_limit` | Leave alone unless a build OOMs |
| `temp_directory` | Pin it — default `.tmp` is CWD-relative, wrong in a frozen exe. Robustness, not speed |
| `storage_compatibility_version='latest'` | Speculative, high value; default is `v0.10.2`. Only settable at file creation → Phase 5 is the opportunity |
| `disabled_compression_methods='fsst'` | Speculative, 5 min to test (Phase 0) |
| Parquet `ROW_GROUP_SIZE 1000000` in phase 1 | Real lever for the **view** path — fewer footers, faster binds |
| Defender exclusion | Recommend **if** Phase 0 test 1 shows the signature |

**Phase 1 (CSV→Parquet) throughput while here:** `_enrich_csv_to_parquet_sql:398` opens a fresh
`duckdb.connect()` and re-runs `_register_lookups` for **each of 577 files**. Hoist both to the
caller. (Not setting `PRAGMA threads` there is harmless — DuckDB defaults to core count.)

---

## Phase 9 — Workflow IA and routing (1 day, low risk)

- **`SidebarToolsPage.tsx:932/1034` numbers its own cards backwards**: "1) Build DuckDB" then
  "2) Convert CSV→Parquet", while the page's own intro at `:737` states the correct order. Swap the
  JSX blocks and renumber. A new operator following the on-screen numbers runs Build against a
  non-existent parquet folder.
- Rename `/sidebar-6-tools` → `/data-tools` (keep a redirect); the ordinal no longer holds and the
  page is labelled "Data Tools".
- Single `app/routes.ts` registry consumed by `Sidebar.tsx` and `Header.tsx` — this also fixes the
  **three routes with no header title** (`/drive-upload-master`, `/drive-download`,
  `/alter-local-db` currently show the DB filename). Group by the real monthly sequence:
  FTP → Data Tools → Query → Upload to Drive.
- **`App.tsx:38`** `<Navigate to="/query/local">` drops the query string, so every dashboard table
  card (`TableList.tsx:30` → `/query?table=X`) lands on an empty builder — even though
  `QueryBuilderWorkspace.tsx:140` is ready to consume it. Preserve `search`.
- Add a catch-all route and a `RouteErrorBoundary` — there is **no error boundary anywhere**, so a
  render throw in any 1000-line page blanks the whole window.

---

## Phase 10 — Accessibility baseline (1.5 days, low risk)

91 `<label>` elements, exactly **one** `htmlFor`, **zero** `id` on any input.

- **Shared `Field` component** (biggest single win): `SidebarToolsPage.tsx:311-317` and
  `LocalDbAlterationsPage.tsx:34-40` render label and input as siblings — ~34 inputs across the two
  heaviest forms are unlabelled and not click-to-focus. Use `React.useId()` + `htmlFor` +
  `aria-describedby` for the help text.
- **Un-trap Tab in the SQL editor** — `HighlightedSqlEditor.tsx:306-319` unconditionally swallows
  Tab (WCAG 2.1.2); a keyboard user cannot leave the editor. Use Escape as a one-shot
  "next Tab moves focus" flag.
- **The two comboboxes** (`TableSelector`, `SearchableSelect`) back the table picker and every
  filter/CASE/pivot field and have no roles, arrow keys, Escape or click-outside. Add
  `useListboxKeys` + `useClickOutside`. Also a plain speed win over a 200-item scroll list.
- **Modals** (`ExportModal`, fullscreen SQL panel): `role="dialog"`, focus trap, Escape.

---

## Phase 11 — Dark mode, scoped down (½ day)

Delete the blanket override at `index.css:69-144`. It darkens neutral surfaces while leaving every
coloured one light, which is worse than no theming: the SQL editor sits at ~2.4:1, the FTP period
picker is light-grey on cream, and all 11 labels on the Full Pipeline card vanish. Add real `dark:`
classes to those three surfaces, keep the `:root`/`.dark` tokens and input base rules, and limit the
toggle to the chrome that genuinely supports it.

---

## Phase 12 — Secrets, packaging, hygiene (2 days) — needs decisions

Flagged, not assumed:

- **`FtpDownloadPage.tsx:61-67` hardcodes five real DISCOM FTP passwords in source.** They compile
  into the shipped bundle and are written to three localStorage keys. **They are in git history and
  must be rotated regardless.** Move to a `runtime/ftp_profiles.json` beside the exe, resolved
  server-side; the API never returns a password. *Decision: plaintext + NTFS ACLs, Windows DPAPI, or
  prompt-per-run?*
- **`ftp_download_service.py:101` persists passwords into `runtime/job_store.sqlite3`** and copies
  them to dead letters; neither table is ever pruned. Exclude `password` from the persisted payload;
  add retention.
- **Logs are discarded in the frozen exe** — `logger.py:135` and `error_log_service.py:14-17`
  resolve under `sys._MEIPASS`. `config.py` already has the correct `_resolve_runtime_dir()`.
  Combined with `console=False`, a startup failure is completely invisible today.
- **`dialogs.py:40` relaunches the whole app** in a onefile build (`sys.executable -c` ignores
  `-c`), and the second instance's `recover_interrupted_jobs` marks the first's running jobs failed.
  Add an env sentinel plus a single-instance mutex.
- **`SampleSnapshotService` writes 1000 rows of consumer PII** (`NAME`, `ADDRESS`, `MOBILE_NO`) to a
  CWD-relative `samples/` folder on every first connect, silently. *Decision: delete, or opt-in with
  PII excluded?*
- **Pin `duckdb==1.5.3`** — `>=1.0.0` across a major is dangerous given DuckDB's on-disk format
  changes; a pip upgrade could make existing `.duckdb` files unopenable. Split dev requirements.
- **`.env` is unreachable from the exe** — `env_file` resolves to `_MEIPASS/.env` and the spec
  doesn't bundle it, so no `DASHBOARD_*` setting can be supplied in the shipped build.
- Delete dead code: `pages/DataImporterPage.tsx` (265 lines, unrouted duplicate),
  `hooks/useImporter.ts`, `api/importerApi.ts`, `schemaApi.ts:38-79` (stale duplicate of
  `systemApi`). Downgrade the two `// @ts-nocheck` files to targeted `@ts-expect-error`.
- `utils/exceptions.py` defines four exceptions and registers handlers; **none is raised anywhere**
  outside tests. *Decision: adopt `DatabaseNotConnectedError` + `InvalidPathError`, or delete?*

---

## Sequencing

| Phase | Effort | Risk | Benefit |
|---|---|---|---|
| 0 Measure the 4.5 MB/s cause | 1 h | none | decides Phase 8 |
| 1 `list_tables` O(1) | ½ d | ~0 | every page load |
| 2 Unblock the event loop | 1 d | low | app stays alive during builds |
| 3 `CATEGORY` fix | ½ d | low | correctness; prerequisite for cheap views |
| 4 **Views by default** | 1–2 d | med | **41 min → ~2s; growth stops** |
| 5 Migrate the 46.7 GB file | 1 d + soak | high | **46.7 GB reclaimed** |
| 6 `useJobPoller` + `JobStatusCard` | 3 d | med | six polling bugs; honest status |
| 7 `alter_db` safety | 1 d | med | page works during the monthly run |
| 8 Fast materialise | 1–2 d | low | gated on Phase 0 |
| 9 Workflow IA | 1 d | low | step order stops being wrong |
| 10 Accessibility | 1.5 d | low | clickable labels, keyboard nav |
| 11 Dark mode scope-down | ½ d | low | removes an actively harmful override |
| 12 Secrets & packaging | 2 d | med | credentials out of the bundle |

Phases 1–3 are cheap, independently valuable, and de-risk 4. **Phase 4 is the headline.** Phase 5
waits for one real month on Phase 4. Phase 6 is the highest-value frontend work. Splitting
`sidebar_tools_service.py` (1972 lines) comes *after* Phase 8, not alongside it.

---

## Verification

1. `.venv/Scripts/python.exe -m pytest tests -q` — 146 passing today; must stay green each phase.
2. `cd frontend && npx vitest run && npm run build && npm run lint` — 20 tests, 0 lint errors today.
3. **Phase 4 gate**: build a month as a view, reopen the DB, confirm the column picker still works;
   diff every saved query against the materialised table; re-run the 7 benchmarks with
   `parquet_metadata_cache=true`.
4. **Phase 5 gate**: `audit_rows` (already shipped) plus per-DISCOM counts and `sum(TOTAL_AMT)` for
   every migrated month, against the read-only original.
5. **Phase 6 gate**: start an FTP download, navigate away and back, confirm progress resumes; force a
   transient 500 during polling and confirm the job is not reported failed.
6. New tests: `useJobPoller`, `JobStatusCard`, the four untested workflow pages,
   `tests/backend/test_alter_db.py`, `tests/backend/test_export.py`.
