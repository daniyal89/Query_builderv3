# Feature Improvement Plan (Planning Only)

## Goal
Increase productivity, reduce repeat work, and improve confidence in outputs.

## 1) High-Impact Feature Additions
- **Saved Queries (Local + Marcadose):** save, rename, clone, tag, delete.
- **Query History:** quick rerun from recent executions with parameters.
- **Template Library:** prebuilt templates for common reporting patterns.
- **Parameterized Queries:** user-editable input variables before run.
- **Scheduled Exports:** run saved reports at fixed intervals and export outputs.

## 2) Query Builder Enhancements
- Join assistant with relationship suggestions from schema hints.
- Aggregation builder (group by, having, calculated metrics).
- Column-level transformations (trim, cast, coalesce, date formatting).
- Explain/validate mode before execution.
- Result profile panel (null %, distinct count, min/max for numeric/date fields).

## 3) Merge & Enrich Improvements
- Smart column mapping suggestions using fuzzy matching.
- Conflict resolution presets (strict, permissive, custom).
- Match quality metrics (exact vs fallback matches).
- Preview unmatched reasons (missing keys, format mismatch, null key).
- Reusable mapping profiles per source format.

## 4) FTP & Drive Workflow Improvements
- Job queue manager with multi-job overview and filtering.
- Retry failed files only (without rerunning full job).
- Throughput and ETA metrics by profile.
- Resume support for interrupted runs.
- Audit export (CSV/JSON) for each job session.

## 5) Data Governance & Collaboration Features
- Role-based access levels (viewer/operator/admin).
- Named workspaces per team.
- Change log for saved queries/templates.
- Shareable run presets (without exposing credentials).

## 6) Observability & Support Features
- Built-in diagnostics panel (API health, last error, dependency checks).
- User-visible operation logs with copy/export.
- Guided recovery actions in error states.

## 7) Prioritized Rollout
1. Saved queries + history.
2. Parameterized templates.
3. Merge smart mapping + quality metrics.
4. FTP/Drive retry & resume.
5. Scheduling + governance.

---
Planning only. No implementation included.
