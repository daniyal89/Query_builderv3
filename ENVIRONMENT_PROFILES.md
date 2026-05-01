# Environment Profiles

This project now supports a small runtime profile surface through `DASHBOARD_*`
settings in a local `.env` file or the process environment.

## Recommended profiles

### `dev`
- Use the repo-local runtime directory.
- Example:
  - `DASHBOARD_ENV_PROFILE=dev`
  - `DASHBOARD_RUNTIME_DIR=./runtime`

### `desktop`
- Use a writable folder next to the packaged executable.
- Keep the persistent job store outside PyInstaller's temporary extraction
  directory.
- Example:
  - `DASHBOARD_ENV_PROFILE=desktop`
  - `DASHBOARD_RUNTIME_DIR=C:/QueryBuilder/runtime`

### `ci`
- Use an isolated runtime folder inside the workspace or temp directory.
- Example:
  - `DASHBOARD_ENV_PROFILE=ci`
  - `DASHBOARD_RUNTIME_DIR=./runtime-ci`

## Background job state

Persistent background jobs now write to `DASHBOARD_JOB_STORE_PATH`. That store
keeps:

- job status snapshots
- retry attempt counters
- cancellation requests
- dead-letter records for jobs that exhaust their configured attempts

If `DASHBOARD_JOB_RECOVER_INTERRUPTED=true`, any job left in `queued`,
`running`, or `cancelling` when the app restarts is marked failed with a
restart-recovery message instead of silently disappearing.
