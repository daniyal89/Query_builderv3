# Project: Local DuckDB Data Dashboard

# SYSTEM RULES FOR AI AGENT (CRITICAL)
- **Extreme Conciseness:** Never explain your code unless explicitly asked.
- **Diffs Only:** When modifying files, only output the specific blocks of code being changed. Never output the full file if it is longer than 50 lines.
- **Isolated Context:** Do not read files outside the specific task scope.

## 1. Tech Stack & Architecture
* **Frontend:** React 18, TypeScript 5, Vite 5. (Compiled to static files served by the backend).
* **Backend:** Python 3.11+, FastAPI, Uvicorn. (Serves static React build on `/`, API on `/api`).
* **Database Engine:** DuckDB (Reads local `.duckdb` files via user-supplied path).
* **Packaging:** PyInstaller (Bundles Python runtime, React `dist/`, and DuckDB into a single `.exe`).

---

## 2. Directory Tree

```
Query_builder/
│
├── main.py                          # Unified entry point: starts Uvicorn server, opens browser via webbrowser.open().
├── requirements.txt                 # Pinned Python dependencies (fastapi, uvicorn, duckdb, pyinstaller).
├── pyproject.toml                   # Project metadata and optional build-system config for pip/poetry.
├── .gitignore                       # Ignores dist/, build/, __pycache__/, node_modules/, *.spec, *.egg-info.
├── README.md                        # Project overview, setup instructions, and build-to-exe guide.
│
│   ══════════════════════════════════
│   ██  PYTHON / FASTAPI  BACKEND  ██
│   ══════════════════════════════════
│
├── backend/
│   ├── __init__.py                  # Marks backend/ as a Python package.
│   ├── app.py                       # Creates the FastAPI application instance, mounts static files, and includes all API routers.
│   ├── config.py                    # Centralizes runtime settings (host, port, debug flag, static files path via sys._MEIPASS).
│   │
│   ├── api/                         # All /api/* route definitions live here.
│   │   ├── __init__.py              # Marks api/ as a Python sub-package.
│   │   ├── router.py               # Aggregates all sub-routers into a single APIRouter prefixed with /api.
│   │   ├── endpoints/
│   │   │   ├── __init__.py          # Marks endpoints/ as a Python sub-package.
│   │   │   ├── connection.py        # POST /api/duckdb/connect — Validates and opens a DuckDB file path; returns connection status.
│   │   │   ├── schema.py           # GET /api/tables, GET /api/tables/{name}/columns — Introspects DuckDB schema metadata.
│   │   │   ├── query.py            # POST /api/query — Receives a structured query payload, executes SQL on DuckDB, returns results.
│   │   │   ├── importer.py         # POST /api/upload-csv — Accepts CSV upload + column mapping; bulk-inserts into a DuckDB table.
│   │   │   └── merge.py            # POST /api/upload-sheets, /api/merge-sheets, /api/enrich-data — Multi-sheet merge & enrichment flow.
│   │   └── deps.py                 # Shared FastAPI dependencies (get_db_service, get_connected_db via Depends()).
│   │
│   ├── services/                    # Business logic, decoupled from HTTP layer.
│   │   ├── __init__.py              # Marks services/ as a Python sub-package.
│   │   ├── duckdb_service.py        # Manages DuckDB connection lifecycle: connect, disconnect, execute, and introspect.
│   │   ├── query_builder_service.py # Translates the frontend's structured query JSON into parameterized SQL strings.
│   │   ├── csv_import_service.py    # Handles CSV parsing, column re-mapping, type coercion, and staged DuckDB insertion.
│   │   └── merge_service.py         # Orchestrates multi-sheet upload, conflict resolution, and Master Table join logic.
│   │
│   ├── models/                      # Pydantic schemas for request/response validation.
│   │   ├── __init__.py              # Marks models/ as a Python sub-package.
│   │   ├── connection.py            # ConnectionRequest (db_path: str) and ConnectionResponse (status, tables_count).
│   │   ├── schema.py               # TableMetadata (table_name, columns, row_count) and ColumnDetail (name, dtype).
│   │   ├── query.py                # QueryPayload (table, select, filters, sort, limit) and QueryResult (columns, rows).
│   │   ├── importer.py             # CSVMappingPayload (file_id, column_map) and ImportResult (rows_inserted, errors).
│   │   └── merge.py               # ConflictResolutionMap, ColumnResolution, EnrichmentRequest/Response, DetectedColumn.
│   │
│   └── utils/                       # Shared utilities.
│       ├── __init__.py              # Marks utils/ as a Python sub-package.
│       ├── path_resolver.py         # Resolves static file paths using sys._MEIPASS (PyInstaller) or fallback for dev mode.
│       └── exceptions.py           # Custom exception classes and FastAPI exception handlers for consistent error responses.
│
│   ══════════════════════════════════════
│   ██  REACT / TYPESCRIPT  FRONTEND  ██
│   ══════════════════════════════════════
│
├── frontend/
│   ├── package.json                 # Project dependencies (react, react-router-dom, axios, typescript, vite).
│   ├── tsconfig.json                # TypeScript compiler options (strict mode, path aliases, JSX settings).
│   ├── vite.config.ts               # Vite build config: output to ../frontend_dist/, proxy /api to backend in dev mode.
│   ├── index.html                   # Root HTML shell; Vite entry point that loads /src/main.tsx.
│   │
│   ├── public/                      # Static assets copied as-is into the build output.
│   │   └── favicon.ico              # Application favicon.
│   │
│   └── src/
│       ├── main.tsx                 # React DOM root render; wraps <App /> in <BrowserRouter> and context providers.
│       ├── App.tsx                  # Top-level route definitions: maps / to HomePage, /query to QueryBuilder, /import to DataImporter.
│       ├── index.css                # Global CSS reset, design tokens (colors, fonts, spacing), and base typography.
│       │
│       ├── api/                     # HTTP client layer; all backend calls are centralized here.
│       │   ├── client.ts            # Axios instance pre-configured with baseURL=/api and error interceptor.
│       │   ├── connectionApi.ts     # connect(dbPath) — POST /api/connect; returns ConnectionResponse.
│       │   ├── schemaApi.ts         # getTables(), getColumns(tableName) — schema introspection calls.
│       │   ├── queryApi.ts          # executeQuery(payload) — POST /api/query; returns QueryResult.
│       │   ├── importerApi.ts       # uploadCSV(file), submitMapping(payload) — CSV import workflow calls.
│       │   └── mergeApi.ts          # uploadSheets(), mergeSheets(), enrichData() — Multi-sheet merge workflow calls.
│       │
│       ├── types/                   # Shared TypeScript interfaces and type definitions.
│       │   ├── connection.types.ts  # ConnectionRequest, ConnectionResponse interfaces.
│       │   ├── schema.types.ts      # TableMetadata, ColumnDetail interfaces.
│       │   ├── query.types.ts       # QueryState (selected cols, filters, sort), QueryPayload, QueryResult interfaces.
│       │   ├── importer.types.ts    # CSVPreview, ColumnMapping, ImportResult interfaces.
│       │   └── merge.types.ts       # ConflictResolutionMap, ColumnResolution, EnrichmentRequest/Response, MergeWizardState.
│       │
│       ├── hooks/                   # Custom React hooks encapsulating stateful logic.
│       │   ├── useConnection.ts     # Manages DuckDB connection state (path, status, tables list).
│       │   ├── useQueryBuilder.ts   # Manages query composition state (selections, filters, pagination).
│       │   ├── useImporter.ts       # Manages CSV upload, column mapping preview, and import progress.
│       │   └── useMergeWizard.ts    # Manages the multi-step merge/enrichment wizard state.
│       │
│       ├── context/                 # React Context providers for cross-component state.
│       │   └── AppContext.tsx        # Provides global state: active DB path, connection status, and current table list.
│       │
│       ├── pages/                   # Full-page route components.
│       │   ├── HomePage.tsx          # Landing page: DuckDB file path input, connect button, and table list overview.
│       │   ├── QueryBuilderPage.tsx  # Visual query composer: table/column selector, filter rows, results grid.
│       │   └── DataImporterPage.tsx  # CSV upload zone, column mapping interface, import preview, and execution trigger.
│       │
│       ├── components/              # Reusable, modular UI building blocks.
│       │   ├── layout/
│       │   │   ├── Sidebar.tsx       # Primary navigation sidebar with links to Home, Query Builder, Data Importer.
│       │   │   ├── Header.tsx        # Top bar: app title, connection status indicator badge, theme toggle.
│       │   │   └── PageShell.tsx     # Wraps pages with Sidebar + Header; provides consistent layout frame.
│       │   │
│       │   ├── home/
│       │   │   ├── PathInput.tsx     # Text input + file-browse button for DuckDB path entry with validation feedback.
│       │   │   └── TableList.tsx     # Displays connected database's tables as cards with name, column count, row count.
│       │   │
│       │   ├── query/
│       │   │   ├── TableSelector.tsx  # Dropdown to pick the target table for the query.
│       │   │   ├── ColumnPicker.tsx   # Multi-select checklist of available columns for the SELECT clause.
│       │   │   ├── FilterRow.tsx      # Single filter condition row: column dropdown, operator select, value input.
│       │   │   ├── FilterPanel.tsx    # Manages a dynamic list of FilterRow components with add/remove controls.
│       │   │   ├── SortControl.tsx    # Column + ASC/DESC selector for ORDER BY clause.
│       │   │   └── ResultsGrid.tsx   # Paginated data table rendering query results with column headers and row data.
│       │   │
│       │   └── importer/
│       │       ├── FileDropZone.tsx   # Drag-and-drop area + click-to-browse for CSV file selection.
│       │       ├── MappingTable.tsx   # Two-column table: CSV header → DuckDB column dropdown for each field.
│       │       ├── PreviewGrid.tsx    # Shows first N rows of the parsed CSV for user verification before import.
│       │       └── ImportProgress.tsx # Progress bar + status messages during the CSV bulk-insert operation.
│       │
│       └── utils/                   # Frontend utility functions.
│           ├── formatters.ts        # Data display helpers: number formatting, date formatting, truncation.
│           └── validators.ts        # Input validation: file path syntax check, required-field checks.
│
│   ═══════════════════════════════════════
│   ██  BUILD, PACKAGING & CI PIPELINE  ██
│   ═══════════════════════════════════════
│
├── build/
│   ├── build_frontend.sh            # Runs `npm run build` in frontend/, copies output to frontend_dist/.
│   ├── build_frontend.ps1           # Windows PowerShell equivalent of build_frontend.sh.
│   ├── build_exe.sh                 # Runs PyInstaller with the .spec file; produces the final single-file .exe.
│   ├── build_exe.ps1                # Windows PowerShell equivalent of build_exe.sh.
│   └── build_all.py                 # Master build orchestrator: runs frontend build → PyInstaller in sequence via subprocess.
│
├── query_builder.spec               # PyInstaller spec file: defines entry point (main.py), data files (frontend_dist/), hidden imports.
│
├── frontend_dist/                   # AUTO-GENERATED — Vite build output; committed or .gitignored based on workflow preference.
│   └── (index.html, assets/...)     # Static HTML/JS/CSS bundle served by FastAPI's StaticFiles mount.
│
├── dist/                            # AUTO-GENERATED — PyInstaller output directory containing the final .exe.
│   └── query_builder.exe            # Single-file executable: double-click to launch the full dashboard.
│
└── tests/
    ├── backend/
    │   ├── test_connection.py       # Tests the /api/connect endpoint with valid/invalid DuckDB paths.
    │   ├── test_schema.py           # Tests schema introspection endpoints return correct table/column metadata.
    │   ├── test_query.py            # Tests query execution endpoint with various filter/sort/limit combinations.
    │   ├── test_importer.py         # Tests CSV upload and column-mapping import pipeline end-to-end.
    │   └── test_merge.py            # Tests upload-sheets, merge-sheets, and enrich-data endpoints.
    │
    ├── frontend/
    │   ├── HomePage.test.tsx        # Tests PathInput rendering, connect button interaction, and table list display.
    │   ├── QueryBuilder.test.tsx    # Tests filter addition/removal, column selection, and query submission flow.
    │   └── DataImporter.test.tsx    # Tests file drop, mapping table rendering, and import trigger behavior.
    │
    └── test_connect_e2e.py          # E2E test: creates test DuckDB, hits connect/tables/columns, validates responses.
```

---

## 3. Core Data Contracts (Strict Types)

### Backend (Pydantic Models)

| Model               | Key Fields                                       | Purpose                      |
|----------------------|--------------------------------------------------|------------------------------|
| `ConnectionRequest`  | `db_path: str`                                   | User-supplied DuckDB path    |
| `ConnectionResponse` | `status: str, tables_count: int`                 | Connection confirmation      |
| `TableMetadata`      | `table_name: str, columns: list[ColumnDetail], row_count: int` | Schema introspection result  |
| `ColumnDetail`       | `name: str, dtype: str, nullable: bool`          | Individual column descriptor |
| `MasterTable`        | `source_table: str, row_index: int, data: dict`  | Schema-agnostic row record   |
| `QueryPayload`      | `table: str, select: list, joins: list, filters: list, sort: list, limit: int` | Structured query definition  |
| `QueryResult`       | `columns: list[str], rows: list[list], total: int` | Query execution response     |
| `CSVMappingPayload` | `file_id: str, target_table: str, column_map: list` | CSV → DuckDB column mapping  |
| `ImportResult`      | `rows_inserted: int, errors: list[str]`          | Import outcome summary       |

#### Merge & Enrichment Models (NEW)

| Model                    | Key Fields                                                        | Purpose                              |
|--------------------------|-------------------------------------------------------------------|--------------------------------------|
| `DetectedColumn`         | `name, source_file, source_sheet, sample_values`                  | Column found in an uploaded sheet    |
| `UploadSheetsResponse`   | `file_ids, detected_columns, conflicts`                           | Phase 1 result: parsed uploads       |
| `ColumnResolution`       | `source_file, source_column, action: map\|ignore, standard_name`  | Single column resolution directive   |
| `ConflictResolutionMap`  | `file_ids, resolutions[], composite_key`                          | Phase 2 input: full conflict map     |
| `MergeSheetsResponse`    | `merged_columns, total_rows, preview_rows, merge_id`              | Phase 2 result: merged dataset info  |
| `EnrichmentRequest`      | `merge_id, master_table, composite_key, fetch_columns, output_format` | Phase 3 input: join specification |
| `EnrichmentResponse`     | `download_url, total_rows, matched_rows, unmatched_rows`          | Phase 3 result: download + stats     |

### Frontend (TypeScript Interfaces)

| Interface            | Key Fields                                       | Purpose                        |
|----------------------|--------------------------------------------------|--------------------------------|
| `QueryState`         | `selectedColumns, joins[], filters[], sortBy, limit`      | Tracks query builder UI state  |
| `FilterCondition`    | `column: string, operator: string, value: string` | Single WHERE clause condition  |
| `CSVPreview`         | `headers: string[], rows: string[][], rowCount`  | Parsed CSV preview data        |
| `ColumnMapping`      | `csvColumn: string, dbColumn: string, skip: boolean` | Per-column mapping decision    |

#### Query Builder Join Interfaces (NEW)

| Interface                | Key Fields                                                | Purpose                              |
|--------------------------|-----------------------------------------------------------|--------------------------------------|
| `JoinClause`             | `table, joinType, conditions[]`                           | Ordered join definition in builder state |
| `JoinCondition`          | `leftColumn, rightColumn`                                 | One equality pair inside a join      |
| `QueryColumnOption`      | `key, label, tableName, columnName, dtype`                | Qualified `table.column` option for joined builders |

#### Merge & Enrichment Interfaces (NEW)

| Interface                | Key Fields                                                | Purpose                              |
|--------------------------|-----------------------------------------------------------|--------------------------------------|
| `ConflictResolutionMap`  | `file_ids, resolutions[], composite_key`                  | TS mirror of Pydantic model          |
| `ColumnResolution`       | `source_file, source_column, action, standard_name?`      | Per-column user decision             |
| `MergeWizardState`       | `step, uploadResult, resolutions, mergeResult, enrichResult` | UI state for the 4-step wizard    |
| `CompositeKey`           | `"Acc_id+DISCOM" \| "Acc_id+DIV_CODE"`                    | Composite key type union             |

---

## 4. PyInstaller Build Pipeline — Critical Notes

> **⚠️ This section is the most failure-prone part of the project. Read carefully.**

### Path Resolution Strategy
```
┌─────────────────────────────────────────────────────────┐
│  main.py / config.py must resolve static files via:     │
│                                                         │
│  if getattr(sys, 'frozen', False):                      │
│      BASE_DIR = sys._MEIPASS        # ← PyInstaller    │
│  else:                                                  │
│      BASE_DIR = Path(__file__).parent  # ← Dev mode     │
│                                                         │
│  STATIC_DIR = BASE_DIR / "frontend_dist"                │
└─────────────────────────────────────────────────────────┘
```

### Build Sequence
```
1. cd frontend/ && npm install && npm run build
      ↓ outputs to → frontend_dist/
2. pyinstaller query_builder.spec
      ↓ bundles main.py + backend/ + frontend_dist/ → dist/query_builder.exe
3. dist/query_builder.exe  ← single click to run
```

### Spec File Key Directives
| Directive      | Value                                           | Reason                                           |
|----------------|------------------------------------------------|--------------------------------------------------|
| `datas`        | `[('frontend_dist', 'frontend_dist')]`         | Embeds the React build inside the executable.     |
| `hiddenimports`| `['uvicorn.logging', 'uvicorn.lifespan.on']`   | Uvicorn sub-modules PyInstaller cannot detect.    |
| `onefile`      | `True`                                         | Produces a single portable `.exe`.                |
| `console`      | `False`                                        | Hides the terminal window; app runs as a tray/GUI.|
| `name`         | `query_builder`                                | Output executable name.                           |

---

## 5. Current State (What is Working)

- [x] Architecture & directory tree defined
- [x] Project skeleton scaffolded (files created on disk)
- [x] Backend: FastAPI app with static file serving + SPA fallback
- [x] Backend: DuckDB connection service (connect, list_tables, get_columns, execute)
- [x] Backend: POST /api/duckdb/connect endpoint (implemented + E2E tested)
- [x] Backend: GET /api/tables + GET /api/tables/{name}/columns endpoints (implemented + tested)
- [x] Backend: Merge & enrichment upload parsing is implemented (`/api/upload-sheets`)
- [x] Backend: Merge & enrichment Pydantic models (ConflictResolutionMap, etc.)
- [x] Frontend: Merge & enrichment TypeScript interfaces (merge.types.ts)
- [x] main.py: Uvicorn launch + port fallback + browser auto-open
- [x] Backend: POST /api/query endpoint implemented
- [x] Backend: POST /api/upload-csv endpoint implemented
- [x] Backend: MergeService.process_enrichment uses explicit uploaded-column mapping for the composite-key LEFT JOIN
- [x] Frontend: Vite + React + TypeScript initialized (npm install)
- [x] Frontend: Home Page (path input + connect)
- [x] Frontend: Query Builder page
- [x] Frontend: Data Importer / Merge Wizard page
- [x] PyInstaller `.spec` file configured
- [x] End-to-end build pipeline tested
- [x] Single `.exe` produced and verified
- [x] Series 1 complete: local Query Builder WHERE operator support expanded across backend + frontend UI
- [x] Series 1 complete: filter UI now adapts operators by column type to stay simpler and more helpful
- [x] Series 1 complete: local filter support now includes `NOT IN`, `NOT LIKE`, `BETWEEN`, `NOT BETWEEN`, `CONTAINS`, `NOT CONTAINS`, `STARTS WITH`, and `ENDS WITH`
- [x] Series 1 complete: frontend production build verified after the operator slice
- [x] Series 2 complete: separate `/query/local` and `/query/marcadose` frontend routes now exist
- [x] Series 2 complete: `AppContext` now stores independent `duckdbConnection` and `marcadoseConnection` state
- [x] Series 2 complete: Marcadose credential form with browser `localStorage` autofill is implemented
- [x] Series 2 complete: navigation, header badges, and dashboard shortcuts now expose the dual-engine frontend shell
- [x] Series 2 complete: frontend production build verified after the dual-engine shell slice
- [x] Series 3 complete: backend Oracle support added with `python-oracledb` Thin mode connection handling
- [x] Series 3 complete: Marcadose connection + schema endpoints implemented (`/api/oracle/connect`, `/api/oracle/tables`, `/api/oracle/tables/{name}/columns`)
- [x] Series 3 complete: query execution is now engine-aware through the `engine` flag (`duckdb` or `oracle`)
- [x] Series 3 complete: Marcadose route can connect, load schema metadata, and run read-only list queries through the shared query builder UI
- [x] Series 3 complete: server-side read-only enforcement added for Marcadose / Oracle queries
- [x] Series 3 complete: frontend production build verified after the Oracle slice
- [x] Series 4 complete: engine-specific SQL preview endpoint and SQL editor panel are implemented for the active builder
- [x] Series 4 complete: direct SQL/manual SQL mode is implemented for both local DuckDB and Marcadose
- [x] Series 4 complete: builder/editor sync keeps the generated SQL in sync until the user detaches into manual SQL
- [x] Series 4 complete: Marcadose read-only enforcement applies to manual SQL preview and execution paths
- [x] Series 4 complete: frontend production build and local DuckDB preview/manual execution were verified after the SQL workflow slice
- [x] Series 5 first slice complete: visual join composition is implemented for the active builder in `Fetch List` mode
- [x] Series 5 first slice complete: join-aware SQL preview/execution/count translation now supports ordered `INNER`, `LEFT`, and `RIGHT` joins with one or more equality conditions
- [x] Series 5 first slice complete: joined-query column selection, filtering, and sorting now use qualified `table.column` references across DuckDB and Oracle builders
- [x] Series 5 first slice complete: backend join translation tests were added and passing (`tests/backend/test_query_builder_service.py`)
- [x] Series 5 first slice complete: frontend production build was re-verified after the join slice
- [x] Series 5 UX follow-up complete: the select-column checklist now supports inline search for large schemas
- [x] Series 5 UX follow-up complete: each filter row now supports searching the column dropdown before selecting a field
- [x] Series 6 Merge & Enrich hardening complete: the current UI supports `.csv`, `.xlsx`, and `.xls` uploads
- [x] Series 6 Merge & Enrich hardening complete: the current UI is now a single-file upload-to-enrich workflow
- [x] Series 6 Merge & Enrich hardening complete: upload/enrich requests use a much longer timeout and clearer timeout messaging for large files
- [x] Series 6 Merge & Enrich hardening complete: the enrich screen can reconnect DuckDB from its path field and load columns inline
- [x] Series 6 Merge & Enrich hardening complete: enrichment no longer hardcodes `master`; the user can choose the DuckDB source table and the backend joins against that selected table
- [x] Series 7 Local Quality of Life: Local Excel-to-DuckDB table/view creation flow is implemented and integrated in the UI
- [x] Series 7 Local Quality of Life: Added native OS file dialogs (via tkinter) for browsing to local DuckDB and data files in the UI
- [x] Series 7 Local Quality of Life: Updated data export to use `showSaveFilePicker` allowing custom filename and folder selection
- [x] Series 7 Local Quality of Life: Updated filter UI to use native browser calendar inputs for date columns
- [ ] Dual-engine architecture is still partially implemented overall; Oracle list-query flow works, but advanced Marcadose features are still pending
- [ ] Query Builder join support is only partially complete: `Fetch List` joins work, but report-mode joins, repeated same-table aliasing, and broader production validation are still pending
- [ ] Expanded WHERE/filter operators still need broader Oracle/Marcadose validation against real production data
- [ ] Marcadose report/pivot mode is not implemented yet; the UI currently keeps Oracle on `Fetch List`
- [ ] `merge-sheets` and the legacy conflict-resolution path still remain in the codebase but are not the primary working merge workflow

---

## 6. Next Immediate Task

* **Status:** Series 7 Local Quality of Life enhancements complete (file pickers, date calendars, native save dialogs, local object creation).
* **Task:** Continue closing the remaining dual-engine/query-builder gaps.
* **Scope:** Revisit report-mode joins, repeated-table aliasing, and broader Marcadose validation on production-like data. Also, implement Marcadose pivot/report mode.
* **After This:** Decide whether to retain/remove the legacy `merge-sheets` path, and consider saved-query/query-history features.
* **Important:** Ensure you have dependencies installed by running: `pip install -r requirements.txt`.

---

## 7. Crucial Context & "Gotchas"

* **PyInstaller `sys._MEIPASS` Rule:** The backend MUST use `sys._MEIPASS` to locate `frontend_dist/` when running as a frozen executable. Never hardcode relative paths from `__file__` alone.
* **Port Collision:** `main.py` should attempt port `8741` (non-standard to avoid conflicts), and fall back to a random available port if occupied.
* **CORS in Dev:** During development, Vite runs on `:5173` and FastAPI on `:8741`. The Vite config MUST proxy `/api` requests to `http://localhost:8741` to avoid CORS issues. In production (bundled), this is irrelevant since everything is served from one origin.
* **DuckDB Thread Safety:** DuckDB connections are NOT thread-safe. The service must use a connection-per-request pattern or a threading lock.
* **CSV Size Limit:** FastAPI's default upload limit is 1MB. Override with `UploadFile` and set a reasonable max (e.g., 500MB) in the import endpoint.
* **React Router + SPA Fallback:** FastAPI must serve `index.html` for any non-`/api` route that doesn't match a static file — this enables client-side routing in the React app.

## 8. Strict Business Rules
* **Master Table Keys:** The primary key for matching is ALWAYS a composite key. It must be either `(ACCT_ID, DISCOM)` OR `(ACCT_ID, DIV_CODE)`. The user explicitly maps which uploaded columns correspond to those keys during enrichment.
* **Merge & Enrich Flow (Current Working Path):**
  1. **Upload Phase:** User uploads one or more CSV/Excel files. Backend parses columns and returns `UploadSheetsResponse` with detected column names.
  2. **Enrichment Phase:** The current working wizard skips the legacy conflict-resolution path and goes straight to explicit key mapping. The user maps uploaded columns to `ACCT_ID` and a secondary key (`DISCOM` or `DIV_CODE`), then selects one or more `master` columns to fetch.
  3. **Export Phase:** Backend performs a LEFT JOIN using the mapped composite key and returns a downloadable Excel file.
* **Connection Reuse:** The enrichment endpoint reuses the active global DuckDB connection (`DuckDBService._conn`) instead of opening a second concurrent connection.
* **Row Integrity:** The LEFT JOIN preserves every uploaded row even when no match is found in the `master` table.

## 9. Database Schema
* **Local Database Path:** MUST be dynamically provided by the user via the frontend UI and passed to the backend API. DO NOT hardcode.
* **Target Table:** `master`
* **Core Keys:** `ACCT_ID`, `DISCOM`, `DIV_CODE`
* **Data Types:** All 152 columns in the `master` table are `VARCHAR`.
 ## 10. Query Builder Modes
The Query Builder operates in two strictly isolated modes:
* **Mode 1: Fetch List:** Applies standard WHERE filters and returns raw tabular data.
* **Mode 2: Generate Report (Pivot):** Operates like an Excel Pivot Table. The user configures `Rows`, `Columns`, `Values`, and an `Aggregation Function` (e.g., SUM, COUNT). The backend must use DuckDB's native `PIVOT` syntax or Pandas `pivot_table` to aggregate the data before returning it.
* **Join Scope:** Visual joins are available in both `Fetch List` and `Generate Report`; report fields use qualified joined column references.
* **Query Row Limits:** By default, the 'Fetch List' mode must limit results to 1000 rows to prevent browser UI freezing. Users can configure this limit. A limit of `0` means 'No Limit' (fetch all rows). The frontend table must use CSS scrolling (e.g., `overflow-y: auto` with a max height) to handle large datasets gracefully.

## 11. Dual-Engine Architecture (DuckDB & Marcadose)
* **Status:** Core dual-engine shell and Oracle list-query execution are implemented through Series 3.
* **Independent Builders:** The dashboard must expose two fully independent Query Builders:
  1. `Query Builder (Local)` for local `.duckdb` files.
  2. `Query Builder (Marcadose)` for the remote Oracle database.
* **Routing & State:** Implemented in the frontend shell. `/query/local` and `/query/marcadose` now exist, and the React `AppContext` stores independent `duckdbConnection` and `marcadoseConnection` state.
* **Marcadose Credentials:** Implemented in the frontend shell. Oracle credentials are captured in a UI form (`host`, `port`, `sid`, `username`, `password`) and saved in browser `localStorage` only for auto-fill.
* **Backend Oracle Engine:** Implemented for connection, schema loading, and read-only list-query execution. The backend now uses the `oracledb` Python package in Thin mode, and the `engine` discriminator (`'duckdb'` or `'oracle'`) routes query execution to the proper service.

## 12. Query Builder Feature Expansion
* **Join Support Status:** The first join slice is implemented for both builders in `Fetch List`. Users can add ordered joins, choose `INNER` / `LEFT` / `RIGHT`, configure one or more equality key pairs, and then select/filter/sort by qualified `table.column` fields.
* **Current Join Limits:** `FULL` join is not in scope, and the visual builder currently allows each joined table only once (no repeated-table aliasing yet).
* **WHERE Operator Expansion:** The Query Builder must support a broader set of WHERE/filter operators than the current implementation.
* **Type-Aware Operators:** To keep the UI simple and helpful, the operator list should depend on the selected column type and engine instead of showing every operator for every field.
* **Expected Coverage:** Plan for common operators such as equality/inequality, comparison, `IN`, `NOT IN`, `LIKE`, `NOT LIKE`, `IS NULL`, `IS NOT NULL`, and range-style filters such as `BETWEEN` where appropriate.
* **Friendly UI Mapping:** Text-friendly operators such as `contains`, `starts with`, and `ends with` may be exposed in the UI if they are translated safely to the correct engine SQL.
* **Supported Usage:** This join functionality applies to both builders, but any generated SQL must respect the active engine dialect and permissions.
* **Builder Output:** Implemented for the current join slice. The visual builder now translates the configured joins into executable engine-specific SQL and matching count SQL for the selected engine.

## 13. SQL Preview, Editing, and Direct Execution
* **SQL Preview:** For every query built in the UI, the app must show the corresponding generated SQL.
* **Engine-Specific SQL:** The SQL preview must match the active engine:
  1. DuckDB SQL when using `Query Builder (Local)`.
  2. Oracle/Marcadose SQL when using `Query Builder (Marcadose)`.
* **Editable SQL:** Users must be able to customize the generated SQL before execution.
* **Sync Behavior:** Visual-builder state and SQL-editor state should remain synced where safely possible.
* **Fallback Behavior:** If edited SQL can no longer be reliably mapped back into the visual builder, the app should preserve the SQL and switch to a manual-SQL workflow instead of silently rewriting it.
* **Direct SQL Mode:** Users must also be able to write SQL directly without using the visual builder.
* **Execution:** The app must support running either:
  1. SQL generated by the visual builder.
  2. User-authored SQL entered directly in the editor.

## 14. Local DuckDB Excel Import / Object Creation
* **Excel/CSV as Source:** Implemented in the local DuckDB query builder. Users can enter a full local `.csv`, `.tsv`, or `.xlsx` path and create a DuckDB table or view from it.
* **Object Creation Scope:** This object creation capability is local-only and must never target Marcadose.
* **Use Cases:** This feature is intended to let users quickly stage local data for further querying, joining, reporting, or enrichment inside DuckDB.
* **DuckDB XLSX Limit:** DuckDB supports `.xlsx` through the `excel` extension; legacy `.xls` should be saved as `.xlsx` or CSV first.

## 15. Engine Permission Rules
* **Marcadose is Read-Only:** Implemented server-side for current Oracle query execution. The Marcadose / Oracle builder allows read-only operations only.
* **Forbidden on Marcadose:** Implemented server-side for current Oracle query execution. No create, replace, alter, drop, insert, update, delete, merge, truncate, or other write-side operations may be executed against Marcadose.
* **Allowed on Local:** Local DuckDB may support broader write-side operations, including table/view creation and other local data-prep operations required by the dashboard workflow.
* **Safety Requirement:** Implemented for current Oracle query execution. The backend enforces these rules server-side, not only in the frontend UI.

## 16. Confirmed Decisions Before Implementation
* **SQL Sync Model:** Keep the visual builder and SQL editor synced where possible. If the edited SQL cannot be safely represented by the builder model, switch to a manual-SQL workflow while preserving the user's query.
* **Join Types:** The current implemented builder supports `INNER`, `LEFT`, and `RIGHT`. `FULL` join is not currently planned.
* **Join Ordering Rule:** Later joins may reference the base table or earlier joins on the left side of the join predicate. The joined table itself must stay on the right side of each join condition in the current builder model.
* **Repeated Table Aliasing:** Not implemented in the visual builder yet. If the same table must be joined multiple times, that currently requires manual SQL.
* **Local Write Scope:** Local DuckDB direct SQL may allow broader write operations. Marcadose remains strictly read-only.
* **UX Principle:** The product should stay simple, helpful, and approachable. Prefer clarity and guided workflows over a dense or overly technical UI.
* **Large Selectors:** Any table/column selector with more than 20 options should expose inline search before selection.
* **Schema/Data Awareness:** During implementation, inspect the actual local DuckDB schema and representative data so the app can better understand field formats, likely data types, and practical defaults for filters, joins, previews, and imports.

## 17. Research-Based Recommended Capabilities To Consider
* **Status:** Recommended from current query-builder / SQL-workbench research. These are not yet confirmed project requirements.
* **Saved Queries:** Ability to save, load, rename, edit, and delete builder queries and manual SQL queries.
* **Query History:** Show previously executed SQL and builder runs so users can reopen and rerun recent work.
* **Step Preview:** Allow previewing intermediate results while building a query, not only final execution.
* **Custom Expressions:** Support calculated columns / formula-style expressions in the builder without forcing users into manual SQL.
* **Parameterized SQL:** Allow bind-style parameters / template variables so users can reuse the same query with different inputs.
* **Schema Explorer + Autocomplete:** Provide searchable object/column browsing plus SQL editor autocomplete for tables, columns, and keywords.
* **Explain / Validation Tools:** Add SQL validation, and for Oracle/Marcadose especially, an explain-plan style view before or after execution.
* **Execution Controls:** Support cancel/stop for long-running queries and SQL formatting in the editor.
* **Result Export:** Export query results to common formats such as CSV / XLSX / JSON.
* **Reusable Query Sources:** Allow starting a new query from a saved query, model, metric, or local view to avoid rebuilding common logic.
* **Shareability:** Optional saved-query links / permalink-style sharing may be useful later if multiple users will use the tool.


### 8. Merge & Enrich restoration in Query_builderv3
The current v3 regression where `/import` showed the Folder Merge UI was corrected.

#### Correct route split
- `/import` = Merge & Enrich wizard
- `/folder-merge` = Folder Merge
- `/ftp-download` = FTP Download

#### Merge & Enrich behavior retained
- upload one or more CSV or Excel files
- detect uploaded columns via `upload-sheets`
- map uploaded `ACCT_ID` plus one secondary key (`DISCOM` or `DIV_CODE`)
- choose master table columns to fetch
- run LEFT JOIN enrichment and download the exported file
- preserve every uploaded row even when no match is found

#### Frontend files changed
- `frontend/src/App.tsx`
- `frontend/src/components/layout/Sidebar.tsx`
- `frontend/src/components/layout/Header.tsx`
- `frontend/src/pages/MergeEnrichPage.tsx`
- `frontend/src/pages/FolderMergePage.tsx`

#### Note
Backend merge and enrich endpoints already existed in v3. The regression was in route-to-page wiring, not in the main merge backend.

---

## 18. Latest Update — FTP and Google Drive Sidebar Expansion

### 18.1 Scope of this update
This update documents all changes added after the base Query Builder v3 handover. The app is no longer only a DuckDB query dashboard. It now also acts as a local UPPCL operations shell for FTP download, Google Drive upload, and Google Drive download workflows.

The latest sidebar routes are:

| Sidebar label | Route | Main frontend page |
|---|---|---|
| Dashboard | `/` | `HomePage.tsx` |
| Query Builder (Local) | `/query/local` | `QueryBuilderPage.tsx` |
| Query Builder (Marcadose) | `/query/marcadose` | `MarcadoseQueryBuilderPage.tsx` |
| Merge & Enrich | `/import` | `MergeEnrichPage.tsx` |
| Folder Merge | `/folder-merge` | `FolderMergePage.tsx` |
| FTP Download | `/ftp-download` | `FtpDownloadPage.tsx` |
| Upload master in Drive | `/drive-upload-master` | `UploadMasterDrivePage.tsx` |
| Drive Download | `/drive-download` | `DriveDownloadPage.tsx` |

### 18.2 Structural changes

#### Backend files added or materially changed

| File | Purpose |
|---|---|
| `backend/api/endpoints/ftp_download.py` | API endpoints for starting, polling, and stopping FTP download jobs. |
| `backend/models/ftp_download.py` | Pydantic request/response models for FTP profiles, job start response, job status, and per-profile results. |
| `backend/services/ftp_download_service.py` | Core FTP download engine: connects to each DISCOM FTP account, scans remote folders, downloads `.gz` files, skips existing local files by size, retries failures, tracks progress, and supports cancellation. |
| `backend/api/endpoints/google_drive.py` | API endpoints for Google auth status/login plus Drive upload/download start, status, and stop. |
| `backend/models/google_drive.py` | Pydantic models for Drive auth config, upload/download requests, job status, and auth status. |
| `backend/services/google_drive_service.py` | Core Google Drive service: OAuth login, optional service-account mode, public-link download attempt, recursive folder download, recursive folder upload, Google Docs/Sheets/Slides export, skip-existing logic, and cancellation support. |
| `backend/api/router.py` | Now includes `ftp_download.router` and `google_drive.router`. |
| `requirements.txt` | Added Google API dependencies: `google-api-python-client`, `google-auth`, and `google-auth-oauthlib`. |

#### Frontend files added or materially changed

| File | Purpose |
|---|---|
| `frontend/src/pages/FtpDownloadPage.tsx` | Full FTP Download page including DISCOM profiles, date/month helper, progress/status cards, stop button, and editable remote/local profile fields. |
| `frontend/src/pages/UploadMasterDrivePage.tsx` | Google Drive upload page for uploading a local MASTER folder tree into a Drive parent folder. |
| `frontend/src/pages/DriveDownloadPage.tsx` | Google Drive file/folder download page with public-first auto mode, optional advanced service-account mode, progress/status, and stop button. |
| `frontend/src/api/ftpApi.ts` | Client wrappers for `/api/ftp-download/start`, `/api/ftp-download/status/{job_id}`, and `/api/ftp-download/stop/{job_id}`. |
| `frontend/src/api/driveApi.ts` | Client wrappers for Drive auth, upload/download start, status polling, and stop APIs. |
| `frontend/src/types/ftp.types.ts` | TypeScript interfaces matching FTP Pydantic models. |
| `frontend/src/types/drive.types.ts` | TypeScript interfaces matching Drive Pydantic models. |
| `frontend/src/App.tsx` | Added routes for FTP Download, Upload master in Drive, and Drive Download. |
| `frontend/src/components/layout/Sidebar.tsx` | Added sidebar links for the three operations pages. |

#### Config and notes files added

| File | Purpose |
|---|---|
| `config/README_google_oauth.txt` | Explains how to place the OAuth Desktop client JSON for Google login. |
| `DRIVE_AUTH_UPDATE_NOTES.md` | Documents the OAuth/public-first auth update. |
| `STOP_AND_SKIP_UPDATE_NOTES.md` | Documents stop/cancel and skip-existing behavior. |
| `FTP_PERIOD_HELPER_UPDATE_NOTES.md` | Documents the FTP Master/Billed date/month helper. |

### 18.3 FTP Download feature

#### Purpose
The FTP Download page replaces manual FTP scripts for downloading UPPCL `.gz` files from DISCOM FTP folders into a local folder tree.

#### Supported DISCOM profile pattern
The UI is designed around these DISCOM profiles:

- `MVVNL`
- `DVVNL`
- `PVVNL`
- `PuVNL`
- `KESCO`

Each profile contains FTP username, password, remote folder, and local subfolder. Users can edit remote and local paths directly in the UI.

#### Date and month helper
A helper card was added below the FTP Download header to reduce confusion around `{MONTH}` and `{DATE}` placeholders.

The helper supports two presets:

1. **Master data**
   - User selects a month from a month picker.
   - Remote folder is filled as `/01-MASTER_DATA/{MONTH}/`.
   - Local subfolder is filled as `{MONTH}/{PROFILE}`.
   - Output root defaults to `G:\MASTER` when the field is blank or still on a default root.

2. **Billed data**
   - User selects a date from a calendar input.
   - User can also see/edit the billed local month folder because billed output paths use both month and date.
   - Remote folder is filled as `/03_CSV_BILLED/{DATE}/`.
   - Local subfolder is filled as `{MONTH}/{DATE}/{PROFILE}`.
   - Output root defaults to `G:\BILLED` when the field is blank or still on a default root.

Examples:

```text
Master March 2026
Remote folder: /01-MASTER_DATA/MAR_2026/
Local subfolder for MVVNL: MAR_2026/MVVNL

Billed 24-Apr-2026
Remote folder: /03_CSV_BILLED/24042026/
Local subfolder for MVVNL: MAR_2026/24042026/MVVNL
```

The helper only fills defaults. The user can still manually edit every profile's remote folder and local subfolder before starting the job.

#### FTP skip-existing behavior
`skip_existing` is enabled by default. The backend skips a file when:

- the local file already exists, and
- the local file size matches the FTP file size.

This avoids re-downloading files already downloaded in a previous run.

#### FTP stop behavior
The FTP page includes **Stop download**. The stop endpoint sets the job state to `cancelling`; active file transfer may need to complete or hit timeout before the final state becomes `cancelled`.

#### FTP backend endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/ftp-download/start` | Start FTP background job. |
| `GET` | `/api/ftp-download/status/{job_id}` | Poll job status. |
| `POST` | `/api/ftp-download/stop/{job_id}` | Request cancellation. |

### 18.4 Google Drive authentication model

#### Normal user flow
Normal users should not browse for OAuth JSON. They should only:

1. Paste a Drive file/folder link or ID.
2. Choose a local download folder, or choose a local folder to upload.
3. Click Sign in with Google only when private Drive access is required.

#### Developer/admin OAuth requirement
The app still needs one Google OAuth Desktop client JSON as the app identity. This file is provided once by the developer/admin, not by each normal user.

Default expected path:

```text
config/google_oauth_client.json
```

Environment override:

```text
QUERY_BUILDER_GOOGLE_OAUTH_CLIENT_JSON=C:\path\to\client_secret.json
```

The OAuth JSON must be a Desktop OAuth client file with an `installed` object. It is not a service-account JSON file.

#### Token cache
After the first successful Google login, the app writes a local token cache:

```text
config/google_drive_token.json
```

This token cache is local to the app/user environment and should not be committed or shared.

#### Optional service-account mode
Service-account JSON remains available under **Advanced authentication**. Use it only for admin/automation workflows.

Rules for service-account mode:

- User must provide the service-account JSON path in the advanced section.
- The target/source Drive folder must be shared with the service account's `client_email`.
- A service account is not the same as a normal Google login and does not represent the end user's Google account unless Workspace domain-wide delegation is separately configured outside this app.

### 18.5 Upload master in Drive feature

#### Purpose
The Upload master in Drive page uploads a local MASTER folder tree to Google Drive.

Typical local folder:

```text
G:\MASTER\MAR_2026
```

Typical root Drive folder name:

```text
MASTER_DATA_2026_03
```

The user provides:

- local MASTER folder path,
- Drive parent folder ID,
- optional root Drive folder name,
- parallel worker count,
- skip-existing setting.

#### Upload skip-existing behavior
When **Skip files that already exist in Drive folder by name** is checked, the service lists files already in each target Drive folder and skips a local file if a file with the same name already exists there.

#### Upload stop behavior
The page includes **Stop upload**. Stop sets the job to `cancelling`; active upload chunks may need to finish or timeout before the job becomes `cancelled`.

### 18.6 Drive Download feature

#### Purpose
The Drive Download page downloads a Google Drive file or folder from a full link or raw Drive ID into a local folder.

The user provides:

- Drive file/folder link or ID,
- local download folder,
- whether to export Google Docs/Sheets/Slides,
- whether to overwrite existing local files.

#### Link handling
The app accepts full links such as:

```text
https://drive.google.com/file/d/FILE_ID/view?usp=drive_link
https://drive.google.com/drive/folders/FOLDER_ID
```

It extracts the internal Drive ID automatically.

#### Auto/public-first mode
Default mode is **Auto: public first, then Google login**.

Behavior:

1. For public file links, the backend first tries direct public download without Google login.
2. If the public attempt fails, or if folder listing/API metadata is needed, the backend falls back to OAuth Google login.
3. For private files/folders, user login is required unless service-account mode is selected and has permission.

Important constraint: public folder listing needs Google Drive API access, so public folder links usually still require OAuth/API login for recursive download.

#### Google Docs/Sheets/Slides export
Google-native files cannot be downloaded as raw binary files. When export is enabled:

| Google file type | Export format |
|---|---|
| Google Docs | `.docx` |
| Google Sheets | `.xlsx` |
| Google Slides | `.pptx` |
| Google Drawings | `.png` |
| Unknown Google app type | `.pdf` fallback |

#### Drive download skip-existing behavior
When **Overwrite existing local files** is unchecked, existing local files are skipped. This prevents re-downloading files already downloaded in a previous run.

#### Drive download stop behavior
The page includes **Stop download**. Stop sets the job to `cancelling`; current download/export chunk may need to finish or timeout before cancellation is visible.

#### Drive backend endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/drive/auth/status` | Show OAuth configuration and token status. |
| `POST` | `/api/drive/auth/login` | Start Google OAuth login and save token cache. |
| `POST` | `/api/drive/upload/start` | Start Drive upload background job. |
| `POST` | `/api/drive/download/start` | Start Drive download background job. |
| `GET` | `/api/drive/status/{job_id}` | Poll Drive job status. |
| `POST` | `/api/drive/stop/{job_id}` | Request upload/download cancellation. |

### 18.7 Job status model

FTP and Drive jobs are asynchronous background jobs. Frontend pages start a job and poll status until it reaches a terminal state.

Current status values:

```text
queued
running
cancelling
completed
failed
cancelled
```

Do not assume Stop is instant. Current file operations may need to finish or timeout.

### 18.8 Build and run notes after these changes

#### Python dependencies
From project root:

```powershell
pip install -r requirements.txt
```

#### Frontend build
From project root:

```powershell
cd frontend
npm install
npm run build
cd ..
python main.py
```

#### NPM/Vite compatibility note
The working frontend package uses `@vitejs/plugin-react@^4.3.0` and `vite@^5.4.0`. Do not use Vite 8 with `@vitejs/plugin-react@4.x`; npm will raise a peer dependency conflict.

If dependency resolution fails after old lockfiles, delete `frontend/node_modules` and `frontend/package-lock.json`, then install again.

PowerShell-safe cleanup:

```powershell
cd D:\PROJECTS\Query_builderv3
if (Test-Path .\frontend\node_modules) { Remove-Item -Recurse -Force .\frontend\node_modules }
if (Test-Path .\frontend\package-lock.json) { Remove-Item -Force .\frontend\package-lock.json }
cd .\frontend
npm install
npm run build
```

#### Browser cache
After rebuilding frontend, restart `python main.py` and press `Ctrl+F5` in the browser.

#### EXE build
Only rebuild EXE after `python main.py` works:

```powershell
pyinstaller query_builder.spec --clean
```

For packaged EXE, keep the `config` folder beside the executable when OAuth login is required:

```text
dist\query_builder.exe
dist\config\google_oauth_client.json
```

### 18.9 Important operational rules

- The Drive OAuth JSON is developer/admin-provided app configuration, not a user-uploaded credential.
- The service-account JSON is optional advanced auth and must not be confused with OAuth Desktop client JSON.
- Never commit real `google_oauth_client.json`, `google_drive_token.json`, or `service_account.json` to source control.
- Public Drive files can often download without login; public folders and private items generally need Drive API access.
- FTP skip logic is size-based; Drive upload skip logic is name-based inside each Drive folder; Drive download skip logic is local-file-existence-based when overwrite is off.
- Remote FTP folder and local subfolder values generated by the helper are defaults only; manual edits by the user must remain supported.
- Stop/cancel APIs are cooperative and should be treated as graceful cancellation, not force-kill.

## Update: Marcadose Monthly Master Table Auto UNION Feature

### Feature Summary

The existing Marcadose Query Builder has been enhanced to support automatic monthly master table selection and optional `UNION ALL` query generation across selected DISCOMs.

No new sidebar item or new page was added. The feature is integrated into the existing Marcadose Query Builder screen.

### Supported Modes

The feature works with both existing Marcadose options:

1. Fetch List
2. Generate Report

### New UI Controls Added

Inside the existing Marcadose Query Builder page, the following controls are available:

- Month selector
- DISCOM selector
- Apply UNION ALL toggle
- Selected master table preview
- Insert List Template button
- Insert Report Template button
- Insert Table Placeholder button
- Add Grand Total row option for Generate Report mode

### Supported DISCOMs

The allowed DISCOM values are:

- DVVNL
- PVVNL
- PUVNL
- MVVNL
- KESCO

These values are whitelisted in the backend for safety.

### Monthly Master Table Format

The selected month and DISCOM are used to generate Marcadose master table names in this format:

```sql
MERCADOS.CM_master_data_<month_tag>_<DISCOM>

backend/services/marcadose_union_service.py
## 20. Latest Update — Auto Sample Snapshot on Connect (DuckDB + Marcadose)

To support future debugging, data profiling, and AI-assisted schema understanding, the app now captures a **one-time sample snapshot** (up to 1000 rows) whenever a database connection is made.

### 20.1 Why this exists
- Operators/developers often need a quick look at representative data without manually writing SQL.
- Future AI agents can use these sample files to understand column shape, value formats, and likely filter patterns.
- Snapshot capture is one-time per connection target to avoid repeated overhead.

### 20.2 What was added

#### New service
- **File:** `backend/services/sample_snapshot_service.py`
- **Responsibilities:**
  - one-time snapshot capture for DuckDB and Marcadose
  - writes CSV sample and metadata JSON
  - max rows captured: `1000`

#### Snapshot output folders
- DuckDB snapshots: `samples/duckdb/`
- Marcadose snapshots: `samples/marcadose/`

Each snapshot writes:
1. `<slug>_sample.csv`
2. `<slug>_sample.meta.json`

### 20.3 Connection-time integration

#### DuckDB connect flow
- **File:** `backend/services/duckdb_service.py`
- On successful connect, service calls:
  - `SampleSnapshotService.capture_duckdb_once(...)`
- Behavior:
  - if snapshot CSV already exists for that DB slug, do nothing
  - otherwise choose first main schema object (prefer BASE TABLE over VIEW) and save up to 1000 rows

#### Marcadose connect flow
- **File:** `backend/services/oracle_service.py`
- On successful connect, service calls:
  - `SampleSnapshotService.capture_oracle_once(...)`
- Behavior:
  - if snapshot CSV already exists for schema+connection slug, do nothing
  - otherwise choose **one representative object only** using preference:
    1) master object for preferred DISCOM (`DVVNL`)
    2) any object containing `MASTER`
    3) fallback to first object
  - saves up to 1000 rows from the selected single object

### 20.4 Important behavior notes
- Snapshot capture is **non-blocking** for connection success.
- Any snapshot failure is intentionally swallowed so connection APIs remain reliable.
- Snapshot is intended for profiling/reference, not full-data export.

### 20.5 Future enhancement ideas
- Add a UI page to view/download the latest snapshots.
- Add per-table sample capture options.
- Add configurable row limit and sampling strategy (random vs first N).

## 21. Latest Update — File Preview and Header Correction for DuckDB Table/View Creation

The Local "Create From File" flow now supports previewing top rows and correcting/adding headers before object creation.

### 21.1 Backend changes
- **Endpoint added:** `POST /api/duckdb/file-object/preview`
  - returns top rows (default 10) and detected columns from CSV/TSV/XLSX source.
- **Model updates:** `backend/models/local_object.py`
  - `FilePreviewRequest`, `FilePreviewResponse`
  - `FileObjectRequest.header_names` (optional custom output headers)
- **Service updates:** `backend/services/duckdb_service.py`
  - `preview_file_source(...)`
  - custom-header projection support via `_build_projected_relation_sql(...)`

### 21.2 Frontend changes
- **API:** `frontend/src/api/localObjectApi.ts`
  - `previewLocalFileObject(...)`
- **UI:** `frontend/src/components/query/LocalFileObjectCreator.tsx`
  - added "Preview top 10 rows" action
  - shows preview grid
  - allows editing column names before create
  - sends `header_names` to backend on create

### 21.3 Why this helps
- Users can validate whether header row is interpreted correctly.
- Users can add/correct final column names before creating table/view.
- Reduces confusion and post-create rename work when source files are inconsistent.
