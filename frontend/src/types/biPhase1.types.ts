export type BIDataSourceType = "duckdb" | "parquet" | "csv" | "tsv" | "json" | "csv_gz" | "json_gz";
export type BIDataSourceSelection = "auto" | BIDataSourceType;
export type BIFieldRole = "dimension" | "measure" | "attribute";
export type BIMetricAggregation = "SUM" | "COUNT" | "AVG" | "MIN" | "MAX" | "COUNT_DISTINCT";
export type BIChartType = "table" | "bar" | "line" | "pie" | "kpi";

export interface BIWorkspace {
  id: string;
  name: string;
  description: string;
}

export interface BIDataSource {
  id: string;
  workspace_id: string;
  name: string;
  source_type: BIDataSourceType;
  location: string;
  status: "active" | "syncing" | "error" | "disabled";
}

export interface BIDataset {
  id: string;
  workspace_id: string;
  data_source_id: string;
  name: string;
  published: boolean;
}

export interface BITable {
  id: string;
  dataset_id: string;
  name: string;
}

export interface BIFieldModel {
  id: string;
  table_id: string;
  name: string;
  data_type: string;
  role: BIFieldRole;
}

export interface BIMetric {
  id: string;
  dataset_id: string;
  name: string;
  expression: string;
  aggregation: BIMetricAggregation;
}

export interface BIChart {
  id: string;
  dataset_id: string;
  title: string;
  chart_type: BIChartType;
  field_ids: string[];
  metric_ids: string[];
}

export interface BIDashboard {
  id: string;
  workspace_id: string;
  name: string;
  chart_ids: string[];
}

export interface BISourceInsight {
  source_id: string;
  detected_type: BIDataSourceType;
  capabilities: Record<string, boolean>;
  table_names: string[];
  selected_table?: string | null;
  schema: Array<{ name: string; type: string }>;
  preview_rows: Array<Record<string, unknown>>;
  status: string;
  last_sync: string;
  load_strategy: string;
}

export interface BIAuditEvent {
  at: string;
  actor: string;
  action: string;
  target: string;
}

export interface BIPhase1State {
  workspaces: BIWorkspace[];
  data_sources: BIDataSource[];
  datasets: BIDataset[];
  tables: BITable[];
  fields: BIFieldModel[];
  metrics: BIMetric[];
  charts: BIChart[];
  dashboards: BIDashboard[];
  source_insights: BISourceInsight[];
  audits: BIAuditEvent[];
}
