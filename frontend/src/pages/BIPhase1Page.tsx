import React, { useEffect, useMemo, useState } from "react";
import {
  createBIChart,
  createBIDashboard,
  createBIDataset,
  createBIMetric,
  createBIWorkspace,
  getBIPhase1State,
  publishBIDataset,
  registerBISource,
} from "../api/biPhase1Api";
import { pickSystemFile } from "../api/systemApi";
import { StatusAlert } from "../components/common/StatusAlert";
import { useAppContext } from "../context/AppContext";
import type {
  BIChart,
  BIChartType,
  BIDataSourceSelection,
  BIDataset,
  BIFieldModel,
  BIPhase1State,
  BISourceInsight,
  BIMetricAggregation,
} from "../types/biPhase1.types";

const EMPTY_STATE: BIPhase1State = {
  workspaces: [],
  data_sources: [],
  datasets: [],
  tables: [],
  fields: [],
  metrics: [],
  charts: [],
  dashboards: [],
  source_insights: [],
  audits: [],
};

type FieldProps = {
  label: string;
  hint?: string;
  children: React.ReactNode;
};

type SectionProps = {
  eyebrow: string;
  title: string;
  description: string;
  children: React.ReactNode;
};

function getErrorMessage(error: unknown): string {
  if (
    typeof error === "object" &&
    error !== null &&
    "normalizedMessage" in error &&
    typeof (error as { normalizedMessage?: unknown }).normalizedMessage === "string"
  ) {
    return (error as { normalizedMessage: string }).normalizedMessage;
  }

  if (
    typeof error === "object" &&
    error !== null &&
    "response" in error &&
    typeof (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail === "string"
  ) {
    return (error as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? "Request failed.";
  }

  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }

  return "Request failed.";
}

const Field: React.FC<FieldProps> = ({ label, hint, children }) => (
  <label className="block space-y-2">
    <span className="block text-sm font-semibold text-slate-800">{label}</span>
    {children}
    {hint ? <span className="block text-xs text-slate-500">{hint}</span> : null}
  </label>
);

const SectionCard: React.FC<SectionProps> = ({ eyebrow, title, description, children }) => (
  <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
    <p className="text-xs font-semibold uppercase tracking-[0.24em] text-indigo-600">{eyebrow}</p>
    <div className="mt-3">
      <h2 className="text-2xl font-bold text-slate-900">{title}</h2>
      <p className="mt-2 text-sm leading-6 text-slate-600">{description}</p>
    </div>
    <div className="mt-6">{children}</div>
  </section>
);

function buildDatasetFieldMap(state: BIPhase1State): Record<string, BIFieldModel[]> {
  const tableToDataset = new Map(state.tables.map((table) => [table.id, table.dataset_id]));
  return state.fields.reduce<Record<string, BIFieldModel[]>>((accumulator, field) => {
    const datasetId = tableToDataset.get(field.table_id);
    if (!datasetId) return accumulator;
    accumulator[datasetId] = [...(accumulator[datasetId] ?? []), field];
    return accumulator;
  }, {});
}

function ensureCurrentSelection(currentId: string, ids: string[]): string {
  if (currentId && ids.includes(currentId)) return currentId;
  return ids[0] ?? "";
}

function formatShortPath(path: string): string {
  if (path.length <= 52) return path;
  return `${path.slice(0, 20)}...${path.slice(-28)}`;
}

export function BIPhase1Page() {
  const { duckdbConnection } = useAppContext();
  const [state, setState] = useState<BIPhase1State>(EMPTY_STATE);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [workspaceForm, setWorkspaceForm] = useState({
    name: "BI Phase 1 Workspace",
    description: "Self-service analytics starter workspace for connector, semantic, and dashboard setup.",
  });
  const [sourceForm, setSourceForm] = useState<{
    workspace_id: string;
    name: string;
    location: string;
    source_type: BIDataSourceSelection;
  }>({
    workspace_id: "",
    name: "",
    location: "",
    source_type: "auto",
  });
  const [datasetForm, setDatasetForm] = useState({
    workspace_id: "",
    data_source_id: "",
    name: "",
  });
  const [metricForm, setMetricForm] = useState<{
    dataset_id: string;
    name: string;
    expression: string;
    aggregation: BIMetricAggregation;
  }>({
    dataset_id: "",
    name: "",
    expression: "",
    aggregation: "SUM",
  });
  const [chartForm, setChartForm] = useState<{
    dataset_id: string;
    title: string;
    chart_type: BIChartType;
    field_ids: string[];
    metric_ids: string[];
  }>({
    dataset_id: "",
    title: "",
    chart_type: "bar",
    field_ids: [],
    metric_ids: [],
  });
  const [dashboardForm, setDashboardForm] = useState({
    workspace_id: "",
    name: "",
    chart_ids: [] as string[],
  });

  const refreshState = async (showSpinner = true) => {
    if (showSpinner) setIsLoading(true);
    try {
      const nextState = await getBIPhase1State();
      setState(nextState);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      if (showSpinner) setIsLoading(false);
    }
  };

  useEffect(() => {
    void refreshState();
  }, []);

  useEffect(() => {
    if (!duckdbConnection.dbPath) return;
    setSourceForm((current) => {
      if (current.location.trim()) return current;
      return {
        ...current,
        location: duckdbConnection.dbPath,
        name: current.name || "Connected DuckDB",
        source_type: "duckdb",
      };
    });
  }, [duckdbConnection.dbPath]);

  useEffect(() => {
    const workspaceIds = state.workspaces.map((workspace) => workspace.id);
    const sourceIds = state.data_sources.map((source) => source.id);
    const datasetIds = state.datasets.map((dataset) => dataset.id);
    const chartIds = state.charts.map((chart) => chart.id);

    setSourceForm((current) => {
      const workspaceId = ensureCurrentSelection(current.workspace_id, workspaceIds);
      if (workspaceId === current.workspace_id) return current;
      return { ...current, workspace_id: workspaceId };
    });

    setDatasetForm((current) => {
      const workspaceId = ensureCurrentSelection(current.workspace_id, workspaceIds);
      const sourceId = ensureCurrentSelection(current.data_source_id, sourceIds);
      const defaultName =
        current.name ||
        (sourceId ? `${state.data_sources.find((source) => source.id === sourceId)?.name ?? "Source"} Dataset` : "");
      if (
        workspaceId === current.workspace_id &&
        sourceId === current.data_source_id &&
        defaultName === current.name
      ) {
        return current;
      }
      return { ...current, workspace_id: workspaceId, data_source_id: sourceId, name: defaultName };
    });

    setMetricForm((current) => {
      const datasetId = ensureCurrentSelection(current.dataset_id, datasetIds);
      if (datasetId === current.dataset_id) return current;
      return { ...current, dataset_id: datasetId };
    });

    setChartForm((current) => {
      const datasetId = ensureCurrentSelection(current.dataset_id, datasetIds);
      const validFieldIds = current.field_ids.filter((id) => state.fields.some((field) => field.id === id));
      const validMetricIds = current.metric_ids.filter((id) => state.metrics.some((metric) => metric.id === id));
      if (
        datasetId === current.dataset_id &&
        validFieldIds.length === current.field_ids.length &&
        validMetricIds.length === current.metric_ids.length
      ) {
        return current;
      }
      return { ...current, dataset_id: datasetId, field_ids: validFieldIds, metric_ids: validMetricIds };
    });

    setDashboardForm((current) => {
      const workspaceId = ensureCurrentSelection(current.workspace_id, workspaceIds);
      const validChartIds = current.chart_ids.filter((id) => chartIds.includes(id));
      if (workspaceId === current.workspace_id && validChartIds.length === current.chart_ids.length) {
        return current;
      }
      return { ...current, workspace_id: workspaceId, chart_ids: validChartIds };
    });
  }, [state]);

  const fieldsByDataset = useMemo(() => buildDatasetFieldMap(state), [state]);
  const metricsByDataset = useMemo(
    () =>
      state.metrics.reduce<Record<string, typeof state.metrics>>((accumulator, metric) => {
        accumulator[metric.dataset_id] = [...(accumulator[metric.dataset_id] ?? []), metric];
        return accumulator;
      }, {}),
    [state.metrics],
  );
  const insightsBySourceId = useMemo(
    () =>
      state.source_insights.reduce<Record<string, BISourceInsight>>((accumulator, insight) => {
        accumulator[insight.source_id] = insight;
        return accumulator;
      }, {}),
    [state.source_insights],
  );
  const datasetsById = useMemo(
    () =>
      state.datasets.reduce<Record<string, BIDataset>>((accumulator, dataset) => {
        accumulator[dataset.id] = dataset;
        return accumulator;
      }, {}),
    [state.datasets],
  );
  const fieldsById = useMemo(
    () =>
      state.fields.reduce<Record<string, BIFieldModel>>((accumulator, field) => {
        accumulator[field.id] = field;
        return accumulator;
      }, {}),
    [state.fields],
  );
  const chartsById = useMemo(
    () =>
      state.charts.reduce<Record<string, BIChart>>((accumulator, chart) => {
        accumulator[chart.id] = chart;
        return accumulator;
      }, {}),
    [state.charts],
  );

  const selectedDatasetFields = fieldsByDataset[chartForm.dataset_id] ?? [];
  const selectedDatasetMetrics = metricsByDataset[chartForm.dataset_id] ?? [];
  const selectedSourceInsight =
    insightsBySourceId[datasetForm.data_source_id] ??
    insightsBySourceId[state.data_sources[0]?.id ?? ""] ??
    null;

  const runMutation = async (action: () => Promise<void>, message: string) => {
    setIsSaving(true);
    setError(null);
    setSuccess(null);
    try {
      await action();
      await refreshState(false);
      setSuccess(message);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  const handleCreateWorkspace = async (event: React.FormEvent) => {
    event.preventDefault();
    await runMutation(async () => {
      await createBIWorkspace(workspaceForm);
    }, "Workspace created.");
  };

  const handleRegisterSource = async (event: React.FormEvent) => {
    event.preventDefault();
    await runMutation(async () => {
      await registerBISource(sourceForm);
    }, "Source registered and previewed.");
  };

  const handleCreateDataset = async (event: React.FormEvent) => {
    event.preventDefault();
    await runMutation(async () => {
      await createBIDataset(datasetForm);
    }, "Dataset created and schema fields generated.");
  };

  const handleCreateMetric = async (event: React.FormEvent) => {
    event.preventDefault();
    await runMutation(async () => {
      await createBIMetric(metricForm);
    }, "Metric added to the semantic model.");
  };

  const handleCreateChart = async (event: React.FormEvent) => {
    event.preventDefault();
    await runMutation(async () => {
      await createBIChart(chartForm);
    }, "Chart definition saved.");
  };

  const handleCreateDashboard = async (event: React.FormEvent) => {
    event.preventDefault();
    await runMutation(async () => {
      await createBIDashboard(dashboardForm);
    }, "Dashboard created.");
  };

  const handlePublishDataset = async (datasetId: string) => {
    await runMutation(async () => {
      await publishBIDataset(datasetId);
    }, "Dataset published.");
  };

  const previewColumns = selectedSourceInsight?.schema.map((column) => column.name) ?? [];

  return (
    <section className="space-y-6">
      <header className="overflow-hidden rounded-[2rem] border border-slate-200 bg-gradient-to-br from-white via-slate-50 to-indigo-50 shadow-sm">
        <div className="grid gap-8 px-6 py-8 lg:grid-cols-[1.25fr_0.75fr] lg:px-8">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-indigo-600">Phase 1 Live</p>
            <h1 className="mt-3 text-3xl font-bold text-slate-900">BI Workspace Builder</h1>
            <p className="mt-4 max-w-3xl text-sm leading-7 text-slate-600">
              This page now works as an actual Phase 1 sandbox. Create a workspace, register a file source, generate
              a dataset schema, add semantic metrics, and assemble starter charts and dashboards from one place.
            </p>
            <div className="mt-5 flex flex-wrap gap-2 text-xs text-slate-600">
              <span className="rounded-full border border-slate-200 bg-white px-3 py-1.5">
                Local DuckDB: {duckdbConnection.isConnected ? "connected" : "not connected"}
              </span>
              <span className="rounded-full border border-slate-200 bg-white px-3 py-1.5">
                Current path: {duckdbConnection.dbPath ? formatShortPath(duckdbConnection.dbPath) : "none"}
              </span>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {[
              { label: "Workspaces", value: state.workspaces.length },
              { label: "Sources", value: state.data_sources.length },
              { label: "Datasets", value: state.datasets.length },
              { label: "Dashboards", value: state.dashboards.length },
            ].map((item) => (
              <div key={item.label} className="rounded-2xl border border-white/70 bg-white/80 p-4 shadow-sm backdrop-blur">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{item.label}</p>
                <p className="mt-2 text-3xl font-bold text-slate-900">{item.value}</p>
              </div>
            ))}
          </div>
        </div>
      </header>

      {error ? (
        <StatusAlert tone="error" title="BI Phase 1 error">
          {error}
        </StatusAlert>
      ) : null}
      {success ? (
        <StatusAlert tone="success" title="Workspace updated">
          {success}
        </StatusAlert>
      ) : null}

      {isLoading ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-8 text-sm text-slate-600 shadow-sm">
          Loading BI workspace state...
        </div>
      ) : null}

      {!isLoading ? (
        <>
          <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
            <SectionCard
              eyebrow="Workspace"
              title="Create the collaboration space"
              description="Start with a named BI workspace. Every source, dataset, chart, and dashboard attaches to this boundary."
            >
              <form className="space-y-4" onSubmit={handleCreateWorkspace}>
                <Field label="Workspace name">
                  <input
                    className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-700 focus:border-indigo-500 focus:outline-none"
                    value={workspaceForm.name}
                    onChange={(event) =>
                      setWorkspaceForm((current) => ({ ...current, name: event.target.value }))
                    }
                    placeholder="Example: Executive BI Lab"
                  />
                </Field>
                <Field label="Description">
                  <textarea
                    className="min-h-24 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-700 focus:border-indigo-500 focus:outline-none"
                    value={workspaceForm.description}
                    onChange={(event) =>
                      setWorkspaceForm((current) => ({ ...current, description: event.target.value }))
                    }
                    placeholder="What is this workspace for?"
                  />
                </Field>
                <button
                  type="submit"
                  disabled={isSaving || workspaceForm.name.trim() === ""}
                  className="rounded-2xl bg-indigo-600 px-5 py-3 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isSaving ? "Saving..." : "Create workspace"}
                </button>
              </form>

              <div className="mt-6 space-y-3">
                {state.workspaces.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-500">
                    No workspace exists yet. Create one first, then the rest of the page becomes usable immediately.
                  </div>
                ) : (
                  state.workspaces.map((workspace) => (
                    <div key={workspace.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-lg font-semibold text-slate-900">{workspace.name}</p>
                          <p className="mt-1 text-sm text-slate-600">
                            {workspace.description || "No description added yet."}
                          </p>
                        </div>
                        <span className="rounded-full bg-indigo-100 px-3 py-1 text-xs font-semibold text-indigo-700">
                          {workspace.id}
                        </span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </SectionCard>

            <SectionCard
              eyebrow="Connectors"
              title="Register a source and inspect it"
              description="Point the workspace at a DuckDB, Parquet, CSV, TSV, or JSON file. The backend detects the connector, infers schema, and stores a sample preview."
            >
              <form className="space-y-4" onSubmit={handleRegisterSource}>
                <Field label="Workspace">
                  <select
                    className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-700 focus:border-indigo-500 focus:outline-none"
                    value={sourceForm.workspace_id}
                    onChange={(event) =>
                      setSourceForm((current) => ({ ...current, workspace_id: event.target.value }))
                    }
                  >
                    <option value="">Select workspace</option>
                    {state.workspaces.map((workspace) => (
                      <option key={workspace.id} value={workspace.id}>
                        {workspace.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Source name">
                  <input
                    className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-700 focus:border-indigo-500 focus:outline-none"
                    value={sourceForm.name}
                    onChange={(event) =>
                      setSourceForm((current) => ({ ...current, name: event.target.value }))
                    }
                    placeholder="Example: Monthly revenue parquet"
                  />
                </Field>
                <Field label="Source type">
                  <select
                    className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-700 focus:border-indigo-500 focus:outline-none"
                    value={sourceForm.source_type}
                    onChange={(event) =>
                      setSourceForm((current) => ({
                        ...current,
                        source_type: event.target.value as BIDataSourceSelection,
                      }))
                    }
                  >
                    <option value="auto">Auto detect</option>
                    <option value="duckdb">DuckDB</option>
                    <option value="parquet">Parquet</option>
                    <option value="csv">CSV</option>
                    <option value="tsv">TSV</option>
                    <option value="json">JSON</option>
                    <option value="csv_gz">CSV.GZ</option>
                    <option value="json_gz">JSON.GZ</option>
                  </select>
                </Field>
                <Field
                  label="File path"
                  hint="Tip: use the connected DuckDB path shortcut if you already connected from the home page."
                >
                  <div className="flex flex-col gap-3 md:flex-row">
                    <input
                      className="w-full rounded-2xl border border-slate-300 px-4 py-3 font-mono text-sm text-slate-700 focus:border-indigo-500 focus:outline-none"
                      value={sourceForm.location}
                      onChange={(event) =>
                        setSourceForm((current) => ({ ...current, location: event.target.value }))
                      }
                      placeholder="D:\\Data\\sales.parquet"
                    />
                    <button
                      type="button"
                      className="rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                      onClick={async () => {
                        const typeHint =
                          sourceForm.source_type === "duckdb"
                            ? "duckdb"
                            : sourceForm.source_type === "json"
                              ? "json"
                              : undefined;
                        const path = await pickSystemFile(typeHint);
                        if (!path) return;
                        setSourceForm((current) => ({
                          ...current,
                          location: path,
                          name: current.name || path.split(/[/\\]/).pop() || current.name,
                        }));
                      }}
                    >
                      Browse file
                    </button>
                    <button
                      type="button"
                      className="rounded-2xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm font-semibold text-indigo-700 hover:bg-indigo-100"
                      onClick={() =>
                        setSourceForm((current) => ({
                          ...current,
                          location: duckdbConnection.dbPath,
                          source_type: duckdbConnection.dbPath ? "duckdb" : current.source_type,
                          name: current.name || "Connected DuckDB",
                        }))
                      }
                      disabled={!duckdbConnection.dbPath}
                    >
                      Use connected DuckDB
                    </button>
                  </div>
                </Field>
                <button
                  type="submit"
                  disabled={
                    isSaving ||
                    sourceForm.workspace_id === "" ||
                    sourceForm.name.trim() === "" ||
                    sourceForm.location.trim() === ""
                  }
                  className="rounded-2xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isSaving ? "Inspecting..." : "Register source"}
                </button>
              </form>

              <div className="mt-6 space-y-3">
                {state.data_sources.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-500">
                    No source is registered yet. Add one file source and the page will show detected schema and sample rows.
                  </div>
                ) : (
                  state.data_sources.map((source) => {
                    const insight = insightsBySourceId[source.id];
                    return (
                      <div key={source.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <p className="text-lg font-semibold text-slate-900">{source.name}</p>
                            <p className="mt-1 break-all font-mono text-xs text-slate-500">{source.location}</p>
                          </div>
                          <div className="flex gap-2">
                            <span className="rounded-full bg-indigo-100 px-3 py-1 text-xs font-semibold text-indigo-700">
                              {source.source_type}
                            </span>
                            <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700">
                              {insight?.schema.length ?? 0} fields
                            </span>
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </SectionCard>
          </div>

          <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
            <SectionCard
              eyebrow="Dataset"
              title="Generate the semantic dataset"
              description="Create a dataset from one registered source. The backend creates a starter table entry and semantic fields from the detected schema."
            >
              <form className="space-y-4" onSubmit={handleCreateDataset}>
                <Field label="Workspace">
                  <select
                    className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-700 focus:border-indigo-500 focus:outline-none"
                    value={datasetForm.workspace_id}
                    onChange={(event) =>
                      setDatasetForm((current) => ({ ...current, workspace_id: event.target.value }))
                    }
                  >
                    <option value="">Select workspace</option>
                    {state.workspaces.map((workspace) => (
                      <option key={workspace.id} value={workspace.id}>
                        {workspace.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Source">
                  <select
                    className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-700 focus:border-indigo-500 focus:outline-none"
                    value={datasetForm.data_source_id}
                    onChange={(event) =>
                      setDatasetForm((current) => ({ ...current, data_source_id: event.target.value }))
                    }
                  >
                    <option value="">Select source</option>
                    {state.data_sources.map((source) => (
                      <option key={source.id} value={source.id}>
                        {source.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Dataset name">
                  <input
                    className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-700 focus:border-indigo-500 focus:outline-none"
                    value={datasetForm.name}
                    onChange={(event) =>
                      setDatasetForm((current) => ({ ...current, name: event.target.value }))
                    }
                    placeholder="Example: Monthly Revenue Model"
                  />
                </Field>
                <button
                  type="submit"
                  disabled={
                    isSaving ||
                    datasetForm.workspace_id === "" ||
                    datasetForm.data_source_id === "" ||
                    datasetForm.name.trim() === ""
                  }
                  className="rounded-2xl bg-emerald-600 px-5 py-3 text-sm font-semibold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isSaving ? "Generating..." : "Create dataset"}
                </button>
              </form>

              <div className="mt-6 space-y-3">
                {state.datasets.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-500">
                    No dataset has been created yet.
                  </div>
                ) : (
                  state.datasets.map((dataset) => {
                    const fields = fieldsByDataset[dataset.id] ?? [];
                    return (
                      <div key={dataset.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <p className="text-lg font-semibold text-slate-900">{dataset.name}</p>
                            <p className="mt-1 text-sm text-slate-600">
                              {fields.length} fields • {metricsByDataset[dataset.id]?.length ?? 0} metrics
                            </p>
                          </div>
                          <div className="flex items-center gap-2">
                            <span
                              className={`rounded-full px-3 py-1 text-xs font-semibold ${
                                dataset.published
                                  ? "bg-emerald-100 text-emerald-700"
                                  : "bg-amber-100 text-amber-700"
                              }`}
                            >
                              {dataset.published ? "Published" : "Draft"}
                            </span>
                            {!dataset.published ? (
                              <button
                                type="button"
                                className="rounded-full border border-slate-300 bg-white px-3 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-100"
                                onClick={() => void handlePublishDataset(dataset.id)}
                                disabled={isSaving}
                              >
                                Publish
                              </button>
                            ) : null}
                          </div>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {fields.map((field) => (
                            <span
                              key={field.id}
                              className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600"
                            >
                              {field.name} ({field.role})
                            </span>
                          ))}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </SectionCard>

            <SectionCard
              eyebrow="Preview"
              title="Schema and sample rows"
              description="The latest registered source exposes a compact preview so the modeler can verify fields before creating metrics and visuals."
            >
              {selectedSourceInsight ? (
                <div className="space-y-5">
                  <div className="grid gap-3 sm:grid-cols-3">
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Detected type</p>
                      <p className="mt-2 text-lg font-bold text-slate-900">{selectedSourceInsight.detected_type}</p>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Schema fields</p>
                      <p className="mt-2 text-lg font-bold text-slate-900">{selectedSourceInsight.schema.length}</p>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Preview rows</p>
                      <p className="mt-2 text-lg font-bold text-slate-900">{selectedSourceInsight.preview_rows.length}</p>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-slate-200">
                    <div className="border-b border-slate-200 px-4 py-3">
                      <p className="text-sm font-semibold text-slate-900">Inferred schema</p>
                    </div>
                    <div className="divide-y divide-slate-100">
                      {selectedSourceInsight.schema.map((column) => (
                        <div key={column.name} className="flex items-center justify-between px-4 py-3 text-sm">
                          <span className="font-medium text-slate-800">{column.name}</span>
                          <span className="font-mono text-xs text-slate-500">{column.type}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {selectedSourceInsight.preview_rows.length > 0 ? (
                    <div className="overflow-hidden rounded-2xl border border-slate-200">
                      <div className="border-b border-slate-200 px-4 py-3">
                        <p className="text-sm font-semibold text-slate-900">Sample rows</p>
                      </div>
                      <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-slate-200 text-sm">
                          <thead className="bg-slate-50">
                            <tr>
                              {previewColumns.map((column) => (
                                <th key={column} className="px-4 py-3 text-left font-semibold text-slate-700">
                                  {column}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100 bg-white">
                            {selectedSourceInsight.preview_rows.map((row, index) => (
                              <tr key={`preview-row-${index}`}>
                                {previewColumns.map((column) => (
                                  <td key={`${index}-${column}`} className="px-4 py-3 text-slate-600">
                                    {String(row[column] ?? "")}
                                  </td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : (
                <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-500">
                  Register a source to see its inferred schema and preview rows here.
                </div>
              )}
            </SectionCard>
          </div>

          <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
            <SectionCard
              eyebrow="Semantic"
              title="Add reusable metrics"
              description="Metrics turn raw columns into reusable business definitions that charts and dashboards can reference."
            >
              <form className="space-y-4" onSubmit={handleCreateMetric}>
                <Field label="Dataset">
                  <select
                    className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-700 focus:border-indigo-500 focus:outline-none"
                    value={metricForm.dataset_id}
                    onChange={(event) =>
                      setMetricForm((current) => ({ ...current, dataset_id: event.target.value }))
                    }
                  >
                    <option value="">Select dataset</option>
                    {state.datasets.map((dataset) => (
                      <option key={dataset.id} value={dataset.id}>
                        {dataset.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Metric name">
                  <input
                    className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-700 focus:border-indigo-500 focus:outline-none"
                    value={metricForm.name}
                    onChange={(event) =>
                      setMetricForm((current) => ({ ...current, name: event.target.value }))
                    }
                    placeholder="Example: Total Revenue"
                  />
                </Field>
                <Field label="Aggregation">
                  <select
                    className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-700 focus:border-indigo-500 focus:outline-none"
                    value={metricForm.aggregation}
                    onChange={(event) =>
                      setMetricForm((current) => ({
                        ...current,
                        aggregation: event.target.value as BIMetricAggregation,
                      }))
                    }
                  >
                    <option value="SUM">SUM</option>
                    <option value="COUNT">COUNT</option>
                    <option value="AVG">AVG</option>
                    <option value="MIN">MIN</option>
                    <option value="MAX">MAX</option>
                    <option value="COUNT_DISTINCT">COUNT_DISTINCT</option>
                  </select>
                </Field>
                <Field
                  label="Expression"
                  hint="You can write SQL-like expressions such as SUM(amount) or COUNT_DISTINCT(customer_id)."
                >
                  <input
                    className="w-full rounded-2xl border border-slate-300 px-4 py-3 font-mono text-sm text-slate-700 focus:border-indigo-500 focus:outline-none"
                    value={metricForm.expression}
                    onChange={(event) =>
                      setMetricForm((current) => ({ ...current, expression: event.target.value }))
                    }
                    placeholder="SUM(amount)"
                  />
                </Field>
                <button
                  type="submit"
                  disabled={
                    isSaving ||
                    metricForm.dataset_id === "" ||
                    metricForm.name.trim() === "" ||
                    metricForm.expression.trim() === ""
                  }
                  className="rounded-2xl bg-violet-600 px-5 py-3 text-sm font-semibold text-white hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isSaving ? "Saving..." : "Create metric"}
                </button>
              </form>

              <div className="mt-6 space-y-3">
                {state.metrics.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-500">
                    No metrics yet.
                  </div>
                ) : (
                  state.metrics.map((metric) => (
                    <div key={metric.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                      <p className="text-lg font-semibold text-slate-900">{metric.name}</p>
                      <p className="mt-1 text-xs font-semibold uppercase tracking-wide text-violet-700">
                        {metric.aggregation}
                      </p>
                      <p className="mt-3 font-mono text-sm text-slate-600">{metric.expression}</p>
                    </div>
                  ))
                )}
              </div>
            </SectionCard>

            <SectionCard
              eyebrow="Visuals"
              title="Compose starter charts"
              description="Link a dataset, one field, and one metric into a saved chart definition that dashboards can later reuse."
            >
              <form className="space-y-4" onSubmit={handleCreateChart}>
                <Field label="Dataset">
                  <select
                    className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-700 focus:border-indigo-500 focus:outline-none"
                    value={chartForm.dataset_id}
                    onChange={(event) =>
                      setChartForm((current) => ({ ...current, dataset_id: event.target.value }))
                    }
                  >
                    <option value="">Select dataset</option>
                    {state.datasets.map((dataset) => (
                      <option key={dataset.id} value={dataset.id}>
                        {dataset.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Chart title">
                  <input
                    className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-700 focus:border-indigo-500 focus:outline-none"
                    value={chartForm.title}
                    onChange={(event) =>
                      setChartForm((current) => ({ ...current, title: event.target.value }))
                    }
                    placeholder="Example: Revenue by region"
                  />
                </Field>
                <div className="grid gap-4 md:grid-cols-3">
                  <Field label="Chart type">
                    <select
                      className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-700 focus:border-indigo-500 focus:outline-none"
                      value={chartForm.chart_type}
                      onChange={(event) =>
                        setChartForm((current) => ({
                          ...current,
                          chart_type: event.target.value as BIChartType,
                        }))
                      }
                    >
                      <option value="table">Table</option>
                      <option value="bar">Bar</option>
                      <option value="line">Line</option>
                      <option value="pie">Pie</option>
                      <option value="kpi">KPI</option>
                    </select>
                  </Field>
                  <Field label="Field">
                    <select
                      className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-700 focus:border-indigo-500 focus:outline-none"
                      value={chartForm.field_ids[0] ?? ""}
                      onChange={(event) =>
                        setChartForm((current) => ({
                          ...current,
                          field_ids: event.target.value ? [event.target.value] : [],
                        }))
                      }
                    >
                      <option value="">Optional field</option>
                      {selectedDatasetFields.map((field) => (
                        <option key={field.id} value={field.id}>
                          {field.name}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Metric">
                    <select
                      className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-700 focus:border-indigo-500 focus:outline-none"
                      value={chartForm.metric_ids[0] ?? ""}
                      onChange={(event) =>
                        setChartForm((current) => ({
                          ...current,
                          metric_ids: event.target.value ? [event.target.value] : [],
                        }))
                      }
                    >
                      <option value="">Optional metric</option>
                      {selectedDatasetMetrics.map((metric) => (
                        <option key={metric.id} value={metric.id}>
                          {metric.name}
                        </option>
                      ))}
                    </select>
                  </Field>
                </div>
                <button
                  type="submit"
                  disabled={isSaving || chartForm.dataset_id === "" || chartForm.title.trim() === ""}
                  className="rounded-2xl bg-fuchsia-600 px-5 py-3 text-sm font-semibold text-white hover:bg-fuchsia-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isSaving ? "Saving..." : "Create chart"}
                </button>
              </form>

              <div className="mt-6 space-y-3">
                {state.charts.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-500">
                    No charts defined yet.
                  </div>
                ) : (
                  state.charts.map((chart) => (
                    <div key={chart.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-lg font-semibold text-slate-900">{chart.title}</p>
                          <p className="mt-1 text-sm text-slate-600">{chart.chart_type} chart</p>
                        </div>
                        <span className="rounded-full bg-fuchsia-100 px-3 py-1 text-xs font-semibold text-fuchsia-700">
                          {datasetsById[chart.dataset_id]?.name ?? chart.dataset_id}
                        </span>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {chart.field_ids.map((fieldId) => (
                          <span
                            key={fieldId}
                            className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600"
                          >
                            Field: {fieldsById[fieldId]?.name ?? fieldId}
                          </span>
                        ))}
                        {chart.metric_ids.map((metricId) => (
                          <span
                            key={metricId}
                            className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600"
                          >
                            Metric: {state.metrics.find((metric) => metric.id === metricId)?.name ?? metricId}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </SectionCard>
          </div>

          <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
            <SectionCard
              eyebrow="Dashboards"
              title="Assemble a starter dashboard"
              description="Choose a workspace and bundle any saved charts into a named dashboard definition."
            >
              <form className="space-y-4" onSubmit={handleCreateDashboard}>
                <Field label="Workspace">
                  <select
                    className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-700 focus:border-indigo-500 focus:outline-none"
                    value={dashboardForm.workspace_id}
                    onChange={(event) =>
                      setDashboardForm((current) => ({ ...current, workspace_id: event.target.value }))
                    }
                  >
                    <option value="">Select workspace</option>
                    {state.workspaces.map((workspace) => (
                      <option key={workspace.id} value={workspace.id}>
                        {workspace.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Dashboard name">
                  <input
                    className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-700 focus:border-indigo-500 focus:outline-none"
                    value={dashboardForm.name}
                    onChange={(event) =>
                      setDashboardForm((current) => ({ ...current, name: event.target.value }))
                    }
                    placeholder="Example: Revenue command center"
                  />
                </Field>
                <Field label="Charts to include">
                  <div className="space-y-2">
                    {state.charts.length === 0 ? (
                      <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-500">
                        Create at least one chart first.
                      </div>
                    ) : (
                      state.charts.map((chart) => (
                        <label
                          key={chart.id}
                          className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700"
                        >
                          <input
                            type="checkbox"
                            checked={dashboardForm.chart_ids.includes(chart.id)}
                            onChange={(event) =>
                              setDashboardForm((current) => ({
                                ...current,
                                chart_ids: event.target.checked
                                  ? [...current.chart_ids, chart.id]
                                  : current.chart_ids.filter((id) => id !== chart.id),
                              }))
                            }
                          />
                          <span className="font-medium">{chart.title}</span>
                          <span className="text-xs text-slate-500">{chart.chart_type}</span>
                        </label>
                      ))
                    )}
                  </div>
                </Field>
                <button
                  type="submit"
                  disabled={isSaving || dashboardForm.workspace_id === "" || dashboardForm.name.trim() === ""}
                  className="rounded-2xl bg-sky-600 px-5 py-3 text-sm font-semibold text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isSaving ? "Saving..." : "Create dashboard"}
                </button>
              </form>

              <div className="mt-6 space-y-3">
                {state.dashboards.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-500">
                    No dashboards yet.
                  </div>
                ) : (
                  state.dashboards.map((dashboard) => (
                    <div key={dashboard.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-lg font-semibold text-slate-900">{dashboard.name}</p>
                          <p className="mt-1 text-sm text-slate-600">
                            {dashboard.chart_ids.length} chart{dashboard.chart_ids.length === 1 ? "" : "s"}
                          </p>
                        </div>
                        <span className="rounded-full bg-sky-100 px-3 py-1 text-xs font-semibold text-sky-700">
                          {state.workspaces.find((workspace) => workspace.id === dashboard.workspace_id)?.name ??
                            dashboard.workspace_id}
                        </span>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {dashboard.chart_ids.map((chartId) => (
                          <span
                            key={chartId}
                            className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600"
                          >
                            {chartsById[chartId]?.title ?? chartId}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </SectionCard>

            <SectionCard
              eyebrow="Audit"
              title="Recent activity"
              description="Every create and publish action is recorded so Phase 1 work can be traced while the backend remains in-memory."
            >
              {state.audits.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-500">
                  No activity yet.
                </div>
              ) : (
                <div className="space-y-3">
                  {[...state.audits].reverse().slice(0, 8).map((audit) => (
                    <div key={`${audit.at}-${audit.target}`} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-slate-900">{audit.action}</p>
                          <p className="mt-1 text-xs text-slate-500">
                            Actor: {audit.actor} • Target: {audit.target}
                          </p>
                        </div>
                        <span className="rounded-full bg-slate-200 px-3 py-1 text-xs font-semibold text-slate-700">
                          {new Date(audit.at).toLocaleString()}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </SectionCard>
          </div>
        </>
      ) : null}
    </section>
  );
}
