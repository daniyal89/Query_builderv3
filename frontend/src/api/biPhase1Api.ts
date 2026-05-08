import apiClient from "./client";
import type {
  BIChart,
  BIChartType,
  BIDataSource,
  BIDataSourceSelection,
  BIDashboard,
  BIDataset,
  BIPhase1State,
  BIMetric,
  BIMetricAggregation,
  BIWorkspace,
} from "../types/biPhase1.types";

export async function getBIPhase1State(): Promise<BIPhase1State> {
  const response = await apiClient.get<BIPhase1State>("/bi-phase1/state");
  return response.data;
}

export async function createBIWorkspace(payload: {
  name: string;
  description: string;
}): Promise<BIWorkspace> {
  const response = await apiClient.post<BIWorkspace>("/bi-phase1/workspaces", payload);
  return response.data;
}

export async function registerBISource(payload: {
  workspace_id: string;
  name: string;
  location: string;
  source_type: BIDataSourceSelection;
}): Promise<BIDataSource> {
  const response = await apiClient.post<BIDataSource>("/bi-phase1/data-sources", payload);
  return response.data;
}

export async function createBIDataset(payload: {
  workspace_id: string;
  data_source_id: string;
  name: string;
  table_name?: string | null;
}): Promise<BIDataset> {
  const response = await apiClient.post<BIDataset>("/bi-phase1/datasets", payload);
  return response.data;
}

export async function publishBIDataset(datasetId: string): Promise<BIDataset> {
  const response = await apiClient.post<BIDataset>(`/bi-phase1/datasets/${encodeURIComponent(datasetId)}/publish`);
  return response.data;
}

export async function createBIMetric(payload: {
  dataset_id: string;
  name: string;
  expression: string;
  aggregation: BIMetricAggregation;
}): Promise<BIMetric> {
  const response = await apiClient.post<BIMetric>("/bi-phase1/metrics", payload);
  return response.data;
}

export async function createBIChart(payload: {
  dataset_id: string;
  title: string;
  chart_type: BIChartType;
  field_ids: string[];
  metric_ids: string[];
}): Promise<BIChart> {
  const response = await apiClient.post<BIChart>("/bi-phase1/charts", payload);
  return response.data;
}

export async function createBIDashboard(payload: {
  workspace_id: string;
  name: string;
  chart_ids: string[];
}): Promise<BIDashboard> {
  const response = await apiClient.post<BIDashboard>("/bi-phase1/dashboards", payload);
  return response.data;
}
