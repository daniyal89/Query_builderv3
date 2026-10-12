# Monthly Master Automation — one click, then scheduled

## What happens today, by hand, every month

1. On the **3rd evening** the DISCOMs' master CSVs appear on `ftp.uppclonline.com`
   under `/01-MASTER_DATA/<MON_YYYY>/`.
2. **FTP Download** page → Load Master preset → Start. Writes
   `G:\MASTER\<MON_YYYY>\<DISCOM>\*.csv.gz` (615 files, ~9 GB).
3. **Upload master in Drive** page → folder `G:\MASTER\<MON_YYYY>` → parent
   `1fJFN1orOrMaKtjDTX6oWdT0FGYX2Gvng`, root name `MASTER_DATA_<YYYY>_<MM>` → Start.
4. **Data Tools** page → UPPCL preset → Run full pipeline. CSV → parquet →
   `CREATE VIEW Master_<MMYY>` in `uppcl_latest.duckdb` (~2 s for the view).
5. Optionally **Materialise** the month (41 min) and demote the previous one.

Three pages, three forms, three "Start" buttons, and someone has to notice the
FTP folder has appeared. Everything else is already automated inside each step.

## What already exists, and what is missing

Every step is already a persistent background job in `backend/services/job_runtime.py`
(SQLite store, cancel, retry policy, dead letters). Nothing needs to be rewritten.

| Step | Job + endpoint | Idempotent re-run? | Unattended-safe? |
|---|---|---|---|
| FTP download | `FTPDownloadService` · `POST /api/ftp-download/start` | yes — `skip_existing` size-matches | **no** — passwords come from the browser form |
| Drive upload | `GoogleDriveService` · `POST /api/drive/upload/start` | yes — `skip_existing` by name | **mostly** — refreshes a cached token silently, but falls back to opening a browser (`run_local_server`) |
| CSV → parquet → view | `_run_full_pipeline_job` · `POST /api/sidebar-tools/full-pipeline/start` | yes — parquet skipped unless `overwrite_parquet`; view `replace=True` | yes |

What is **missing** is the glue:

- Nothing chains the three steps or passes the month between them.
- Nothing knows whether the FTP folder is there yet.
- Nothing checks step N finished cleanly before starting N+1.
- There is **no scheduler of any kind** in the app, and no CLI entry point.
- A second app instance is dangerous: `recover_interrupted_jobs` on startup marks
  the *first* instance's running jobs as failed (`PIPELINE_PERFORMANCE_AND_DESIGN_PLAN.md`,
  Phase 12). Any scheduler that "just launches the exe" would trip this.
- `main.py` falls back to a **random port** when 8741 is busy, so nothing outside
  the app can reliably find it.

## Design

### One job that drives the three existing ones

A new orchestrator job type `monthly_master_run` in a new
`backend/services/monthly_run_service.py`. It calls the existing **service
functions directly** (not HTTP — so rate limits and the browser never enter into
it), runs the steps in order, and keeps one combined status snapshot:

```
sense FTP ──► download ──► gate ──┬─► upload to Drive ──┐
                                  └─► csv→parquet→view ─┴─► (optional) materialise ──► done
```

Drive upload and the conversion both only *read* the downloaded `.gz` files, so
they run **in parallel** after the download gate. Upload is network-bound and
conversion is CPU-bound; running them together roughly halves wall-clock time.

Everything is derived from one input, the **month**:

| Derived value | Rule | Example (July 2026) |
|---|---|---|
| FTP remote dir | `/01-MASTER_DATA/<MON>_<YYYY>/` | `/01-MASTER_DATA/JUL_2026/` |
| Local CSV root | `<csv_root>/<MON>_<YYYY>` | `G:\MASTER\JUL_2026` |
| Parquet root | `<parquet_root>/<MON>_<YYYY>` | `G:\MASTER_PARQUET\JUL_2026` |
| DuckDB object | `Master_<MM><YY>`, built as a **VIEW** | `Master_0726` |
| Drive root folder | `MASTER_DATA_<YYYY>_<MM>` | `MASTER_DATA_2026_07` |

Default month = the previous calendar month (what the 3rd-of-the-month drop
contains). Two parquet conventions exist in the wild today
(`G:/MASTER_PARQUET/MAR_2026` in the UI preset, `D:/DATA/MASTER/JUL_26_PAR` on
this machine); the roots are config, the `<MON>_<YYYY>` suffix is fixed.

### Gates — never feed a partial month forward

- **Sense.** The FTP service already reports a missing month folder as a profile
  error (`"DVVNL: 550 …"`) with `found_files = 0`, and the job still *completes*.
  The orchestrator classifies that:
  - all 5 profiles missing → `not_available_yet` → stop quietly, retry later;
  - some missing → `partial` → stop, retry later (DISCOMs upload at different times);
  - 0 files with no error → treated as **not available**, never as success.
- **Download gate.** Every profile: `found_files > 0`, `failed_files == 0`, no
  errors. Advisory: file count within ±20 % of the previous month's run, else warn.
- **Build gate.** The pipeline's existing row reconciliation must not report
  `"loss"`, and the ledger must balance. (Both built earlier this year; the view
  build already refuses when its footer sum disagrees.)
- **Upload gate.** `failed_items == 0`.

A failed gate fails the run with the step named. Nothing downstream starts.

### Resume, not restart

`recover_interrupted_jobs` marks any job that was running at shutdown as failed
— it does not resume. So the job row cannot be the memory of what is done.
Each run writes `RUNTIME_DIR/monthly_runs/<MON>_<YYYY>.json`:

```json
{"month": "JUL_2026",
 "steps": {"download": {"status": "completed", "files": 615, "at": "..."},
           "upload":   {"status": "completed", "items": 615, "at": "..."},
           "build":    {"status": "completed", "object": "Master_0726", "rows": 46380696, "at": "..."}}}
```

Starting a run for a month that already has a marker **skips completed steps**.
Re-clicking after a crash costs seconds, not another 9 GB upload. "Run again from
scratch" is an explicit option.

### Single instance

`job_runtime` gains `active_jobs(job_type)`. Starting a monthly run while one is
active returns 409 with the running job's id. The same check backs the scheduler.

### Credentials that work with nobody at the keyboard

- **FTP.** Passwords move out of `FtpDownloadPage.tsx` into
  `config/ftp_profiles.json` (gitignored, beside the exe), read server-side only.
  The API never returns a password, and `password` is excluded from the persisted
  job payload. **They are in git history and must be rotated regardless.**
- **Drive.** Add `interactive=False` to credential loading: an unattended run
  that would need a browser **raises** ("Google login expired — open Upload
  master in Drive and sign in once") instead of blocking forever on
  `run_local_server`. One trap to know: if the GCP OAuth consent screen is in
  *Testing* mode, Google expires refresh tokens after **7 days**, which would
  break every scheduled run. Either publish the app (internal) or use a service
  account into a **Shared Drive** (service accounts have no My Drive quota).
  Verify `drive/auth/status` as part of the pre-flight before starting.

### Scheduling — keep the app up, let it schedule itself

Two options were considered.

**Rejected: Windows Task Scheduler launching the exe.** It hits the second-instance
trap, `console=False` hides every failure, and `.env` is unreachable from the
frozen build, so nothing can be configured.

**Chosen: an in-app scheduler + the app started at logon.**

- A scheduler thread in the FastAPI lifespan, enabled by
  `config/monthly_automation.json`:

  ```json
  {"enabled": true, "sense_from_day": 3, "sense_time": "18:00", "retry_every_hours": 2,
   "give_up_after_day": 8, "csv_root": "G:/MASTER", "parquet_root": "G:/MASTER_PARQUET",
   "db_path": "G:/MASTER/uppcl_latest.duckdb", "drive_parent_folder_id": "1fJFN...",
   "object_type": "VIEW", "materialise_after": false, "notify": {"toast": true, "email": null}}
  ```

- Once a minute it checks: is it on/after `sense_from_day` at/after `sense_time`,
  is the previous month's marker incomplete, is no run active? If so, start one.
  A `not_available_yet` result schedules the next attempt `retry_every_hours`
  later, until `give_up_after_day`, then raises a visible alert.
- `main.py` gains `--no-browser` and `--minimized`; a one-line
  `schtasks /Create /SC ONLOGON ...` starts the exe that way at login, so "the app
  is running" is simply always true. The app writes `RUNTIME_DIR/app.port` on
  startup so any helper can find it despite the port fallback.
- Status is visible where people already look: a Home banner — *"Latest monthly
  run: JUL_2026 ✓ 3 Aug 19:42 · FTP 615 files · Drive 615 uploaded · View
  Master_0726 46,380,696 rows"* — and a Windows toast on finish or failure.
  Email via SMTP is optional config.

## Phases

### Phase A — single click (1–2 days). Everything else depends on this.

Backend
- `monthly_run_service.py`: month derivation, sense classification, the three
  gates, marker file, parallel upload∥build, `start/status/stop`.
- `job_runtime.active_jobs(job_type)` + 409 on concurrent start.
- `config/ftp_profiles.json` loader; FTP endpoint accepts profile *names* with
  no password when the file resolves them; `password` dropped from persisted
  payloads. `.gitignore` entry.
- `GoogleDriveService` `interactive=False` guard; pre-flight calls auth status.
- `POST /api/automation/monthly-run/start` `{month?, from_scratch?}`,
  `GET .../status/{id}`, `POST .../stop/{id}`, `GET .../latest`.

Frontend
- New **Monthly Run** card (Data Tools, top): month picker defaulting to last
  month, one **Run monthly master** button, a step list with live status, the
  gate results, and a *Resume* / *Run again from scratch* choice when a marker
  exists. Persist nothing sensitive in localStorage.
- Remove the five passwords from `FtpDownloadPage.tsx`; the page shows profile
  names from the server and a "passwords are configured on the server" note.

Tests
- Orchestrator with fake step workers: ordering, each gate stopping the run,
  resume skipping completed steps, 409 on a second start, `not_available_yet`
  vs `partial` vs success classification from real-shaped FTP results.
- Drive guard raises instead of opening a browser when `interactive=False`.
- Credential file: missing file → clear error; API response never contains a password.
- Frontend: the card posts the derived month and renders the step list.

### Phase B — scheduled (½–1 day)
- Scheduler thread with an injectable clock; config file + validation.
- `--no-browser` / `--minimized`; `app.port` file; `schtasks` one-liner in
  `HANDOVER.md`.
- **Automation** settings page; Home banner for the latest run.
- Tests: scheduler fires exactly once per day-window, honours retry/give-up,
  never starts while a run is active, does nothing when disabled.

### Phase C — nice to have (½ day)
- Windows toast + optional SMTP email.
- `materialise_after: true` → promote the new month and demote the previous one
  as the final step (the existing `materialise` job).
- Previous-month file-count comparison on the download gate.

## Decisions needed before Phase A starts

1. **Parquet root convention** — `G:/MASTER_PARQUET/<MON>_<YYYY>` (UI preset) or
   `D:/DATA/MASTER/<MON>_<YY>_PAR` (this machine)? One rule, config for the root.
2. **Drive auth for unattended runs** — publish the OAuth app, or service
   account + Shared Drive? Determines whether scheduled runs survive 7 days.
3. **FTP password storage** — plaintext JSON protected by NTFS ACLs, or Windows
   DPAPI? (Rotation happens either way.)
4. **Materialise automatically?** The policy agreed earlier is "new month =
   view, materialise is a deliberate action". Default `false`; the toggle exists.

## Out of scope
- Replacing the Drive uploader with `rclone`. Viable fallback if OAuth expiry
  becomes a problem, but the in-app uploader already works and reports progress.
- Multi-machine coordination. One machine owns the monthly run.
