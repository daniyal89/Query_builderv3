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
| `QueryPayload`      | `table: str, select: list, filters: list, sort: list, limit: int` | Structured query definition  |
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
| `QueryState`         | `selectedColumns, filters[], sortBy, limit`      | Tracks query builder UI state  |
| `FilterCondition`    | `column: string, operator: string, value: string` | Single WHERE clause condition  |
| `CSVPreview`         | `headers: string[], rows: string[][], rowCount`  | Parsed CSV preview data        |
| `ColumnMapping`      | `csvColumn: string, dbColumn: string, skip: boolean` | Per-column mapping decision    |

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
- [x] Backend: Merge & enrichment endpoint stubs (upload-sheets, merge-sheets, enrich-data)
- [x] Backend: Merge & enrichment Pydantic models (ConflictResolutionMap, etc.)
- [x] Frontend: Merge & enrichment TypeScript interfaces (merge.types.ts)
- [x] main.py: Uvicorn launch + port fallback + browser auto-open
- [x] Backend: POST /api/query endpoint implemented
- [x] Backend: POST /api/upload-csv endpoint implemented
- [x] Backend: Merge service logic (upload-sheets, merge-sheets, enrich-data)
- [x] Frontend: Vite + React + TypeScript initialized (npm install)
- [x] Frontend: Home Page (path input + connect)
- [x] Frontend: Query Builder page
- [x] Frontend: Data Importer / Merge Wizard page
- [x] PyInstaller `.spec` file configured
- [x] End-to-end build pipeline tested
- [x] Single `.exe` produced and verified

---

## 6. Next Immediate Task

* **Status:** Complete!
* **Task:** The project pipeline, dashboard, build steps, and backend API are fully implemented and verified. You may run `main.py` directly, or compile the single executable using PyInstaller.
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
* **Master Table Keys:** The primary key for matching is ALWAYS a composite key. It must be either `(Acc_id, DISCOM)` OR `(Acc_id, DIV_CODE)`.
* **Data Importer Flow:** 1. **Merge Phase:** User uploads multiple files/sheets. If columns conflict, prompt a UI to match or ignore them.
  2. **Enrichment Phase:** User selects which column value they want to fetch from the Master Table.
  3. **Export Phase:** Backend performs the join and returns a downloadable Excel/CSV file.

## 9. Database Schema
* **Local Database Path:** MUST be dynamically provided by the user via the frontend UI and passed to the backend API. DO NOT hardcode.
* **Target Table:** `master`
* **Core Keys:** `ACCT_ID`, `DISCOM`, `DIV_CODE`
* **Data Types:** All 152 columns in the `master` table are `VARCHAR`.
 ## 10. Query Builder Modes
The Query Builder operates in two strictly isolated modes:
* **Mode 1: Fetch List:** Applies standard WHERE filters and returns raw tabular data.
* **Mode 2: Generate Report (Pivot):** Operates like an Excel Pivot Table. The user configures `Rows`, `Columns`, `Values`, and an `Aggregation Function` (e.g., SUM, COUNT). The backend must use DuckDB's native `PIVOT` syntax or Pandas `pivot_table` to aggregate the data before returning it.
* **Query Row Limits:** By default, the 'Fetch List' mode must limit results to 1000 rows to prevent browser UI freezing. Users can configure this limit. A limit of `0` means 'No Limit' (fetch all rows). The frontend table must use CSS scrolling (e.g., `overflow-y: auto` with a max height) to handle large datasets gracefully.