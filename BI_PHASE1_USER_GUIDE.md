# BI Phase 1 User Guide

## What BI Phase 1 does

BI Phase 1 is the starter workspace for building a small analytics flow inside the app. From one page you can:

- create a BI workspace
- register a local data source
- inspect inferred schema and sample rows
- generate a dataset
- publish the dataset
- define metrics
- create chart definitions
- assemble a starter dashboard
- review recent audit activity

This page is available from the left navigation as `BI Phase 1`.

## Before you start

Have one of these local source files ready:

- `.duckdb`
- `.parquet`
- `.csv`
- `.tsv`
- `.json`
- `.csv.gz`
- `.json.gz`

Helpful notes:

- If you already connected a local DuckDB database elsewhere in the app, BI Phase 1 can reuse it with `Use connected DuckDB`.
- The page currently works as an in-memory Phase 1 builder. Created workspaces, datasets, charts, and dashboards are meant for rapid modeling and validation in the running app session.

## Quick workflow

The normal order is:

1. Create workspace
2. Register source
3. Review schema and sample rows
4. Create dataset
5. Publish dataset
6. Create metric
7. Create chart
8. Create dashboard
9. Review audit log

## Step-by-step instructions

### 1. Open BI Phase 1

Open the app and click `BI Phase 1` in the left sidebar. The page title should show `BI Workspace Builder`.

At the top of the page you will also see:

- whether local DuckDB is connected
- the current connected DuckDB path, if one exists
- counters for workspaces, sources, datasets, and dashboards

### 2. Create the workspace

In `Create the collaboration space`:

1. Enter `Workspace name`.
2. Enter `Description`.
3. Click `Create workspace`.

What this does:

- creates the parent container for all BI Phase 1 assets
- unlocks the rest of the page flow

Tip:

- If no workspace exists yet, the rest of the page will stay mostly empty until you create one.

### 3. Register a source

In `Register a source and inspect it`:

1. Choose the `Workspace`.
2. Enter `Source name`.
3. Select `Source type`.
4. Fill `File path`, or click `Browse file`.
5. If you already have a DuckDB connection in the app, click `Use connected DuckDB`.
6. Click `Register source`.

Recommended source type:

- Use `Auto detect` unless you specifically want to force a connector type.

What happens after registration:

- the backend detects the connector
- the schema is inferred
- a sample preview is generated
- the source appears in the source list with detected type and field count

### 4. Review schema and sample rows

In `Schema and sample rows`, check:

- `Detected type`
- `Schema fields`
- `Preview rows`
- `Inferred schema`
- `Sample rows`

Use this step to confirm:

- the correct file was selected
- column names look right
- the file format was interpreted correctly
- the preview contains the expected values

### 5. Create the dataset

In `Generate the semantic dataset`:

1. Choose the `Workspace`.
2. Choose the registered `Source`.
3. Enter `Dataset name`.
4. Click `Create dataset`.

What happens:

- a dataset is created from the selected source
- a starter table entry is generated
- semantic fields are created from the detected schema
- each field is classified automatically, such as `measure`, `dimension`, or `attribute`

After creation, the dataset card shows:

- dataset name
- field count
- metric count
- current state: `Draft` or `Published`

### 6. Publish the dataset

After creating a dataset, click `Publish` on the dataset card when you are ready.

Use publish when:

- the schema looks correct
- you want to treat the dataset as ready for downstream metric and dashboard work

### 7. Create metrics

In `Add reusable metrics`:

1. Select the `Dataset`.
2. Enter `Metric name`.
3. Choose `Aggregation`.
4. Enter `Expression`.
5. Click `Create metric`.

Supported aggregation choices in the UI:

- `SUM`
- `COUNT`
- `AVG`
- `MIN`
- `MAX`
- `COUNT_DISTINCT`

Example expressions:

- `SUM(amount)`
- `COUNT(order_id)`
- `COUNT_DISTINCT(customer_id)`
- `AVG(unit_price)`

Use metrics for business-ready definitions such as:

- total revenue
- total orders
- average order value
- distinct customers

### 8. Create charts

In `Compose starter charts`:

1. Select the `Dataset`.
2. Enter `Chart title`.
3. Choose `Chart type`.
4. Optionally select one `Field`.
5. Optionally select one `Metric`.
6. Click `Create chart`.

Available chart types:

- `Table`
- `Bar`
- `Line`
- `Pie`
- `KPI`

Good starter examples:

- `Revenue by Region` using a region field and total revenue metric
- `Orders by Month` using a month field and order count metric
- `Total Revenue KPI` using only a revenue metric

### 9. Create the dashboard

In `Assemble a starter dashboard`:

1. Choose the `Workspace`.
2. Enter `Dashboard name`.
3. Select the charts to include.
4. Click `Create dashboard`.

After creation, the dashboard card shows:

- dashboard name
- number of charts included
- workspace tag
- chart titles inside the dashboard

### 10. Review recent activity

In `Recent activity`, BI Phase 1 records actions such as:

- workspace creation
- source registration
- dataset creation
- dataset publish
- metric creation
- chart creation
- dashboard creation

Use this section to confirm what was created and in what order.

## Example end-to-end use case

Example flow for a sales file:

1. Create workspace `Executive BI Lab`.
2. Register source `Monthly Sales` from `D:\Data\monthly_sales.parquet`.
3. Review columns such as `order_date`, `region`, `customer_id`, and `amount`.
4. Create dataset `Monthly Sales Model`.
5. Publish the dataset.
6. Create metric `Total Revenue` with `SUM(amount)`.
7. Create metric `Customer Count` with `COUNT_DISTINCT(customer_id)`.
8. Create chart `Revenue by Region`.
9. Create chart `Revenue Trend`.
10. Create dashboard `Sales Command Center`.

## Troubleshooting

### The page shows no data

This is normal before the first workspace and source are created. Start by creating a workspace, then register a source.

### Register source fails

Check the following:

- the selected file path exists on the machine running the app
- the file extension is supported
- the file is not locked or unreadable
- the selected source type matches the file, or use `Auto detect`

### `Use connected DuckDB` is disabled

This means the app does not currently have an active DuckDB path in context. Connect DuckDB elsewhere in the app first, then return to BI Phase 1.

### Dataset creation does not work

Make sure:

- a workspace exists
- a source has already been registered
- the dataset name is not empty

### I cannot build a useful chart

Usually this means the dataset exists but the metric has not been created yet, or the wrong dataset is selected. Create the metric first, then create the chart again.

### Dashboard is empty

Dashboards only include charts you explicitly check during creation. Create charts first, then select them in the dashboard form.

## Current scope of BI Phase 1

BI Phase 1 is designed as a practical modeling and definition workflow. In the current implementation it focuses on:

- source onboarding
- schema validation
- semantic setup
- chart definition
- dashboard assembly
- action traceability through audit history

It is best used as the first step for structuring analytics assets before deeper BI capabilities are layered on top.
