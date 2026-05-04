/**
 * HomePage.tsx â€” Landing page with local DuckDB connection and route shortcuts.
 */

import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PathInput } from "../components/home/PathInput";
import { TableList } from "../components/home/TableList";
import { deleteLocalObject } from "../api/schemaApi";
import { useAppContext } from "../context/AppContext";
import { useConnection } from "../hooks/useConnection";

const EMERGENCY_PROXY_STORAGE_KEY = "dashboard_emergency_proxy_settings_v1";

export const HomePage: React.FC = () => {
  const { dbPath, setDbPath, connect, isConnecting, isConnected, tables, error, refreshTables } = useConnection();
  const { marcadoseConnection } = useAppContext();
  const [tableActionMessage, setTableActionMessage] = React.useState<string>("");
  const [emergencyProxyEnabled, setEmergencyProxyEnabled] = useState(false);
  const [emergencyProxyHost, setEmergencyProxyHost] = useState("10.96.5.20");
  const [emergencyProxyPort, setEmergencyProxyPort] = useState("80");

  useEffect(() => {
    if (dbPath && !isConnected && !isConnecting && !error) {
      connect();
    }
  }, [dbPath, isConnected, isConnecting, error, connect]);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(EMERGENCY_PROXY_STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw) as { enable?: boolean; host?: string; port?: string };
      setEmergencyProxyEnabled(Boolean(parsed.enable));
      setEmergencyProxyHost(parsed.host || "10.96.5.20");
      setEmergencyProxyPort(parsed.port || "80");
    } catch {}
  }, []);

  const saveEmergencyProxySettings = () => {
    window.localStorage.setItem(EMERGENCY_PROXY_STORAGE_KEY, JSON.stringify({
      enable: emergencyProxyEnabled,
      host: emergencyProxyHost.trim() || "10.96.5.20",
      port: emergencyProxyPort.trim() || "80",
    }));
    setTableActionMessage("Saved emergency proxy settings for Drive tools.");
  };

  const handleDeleteTable = async (tableName: string) => {
    const ok = window.confirm(`Delete '${tableName}' from local DuckDB? This action cannot be undone.`);
    if (!ok) return;

    try {
      const response = await deleteLocalObject(tableName);
      setTableActionMessage(response.message);
      await refreshTables();
    } catch (err: any) {
      setTableActionMessage(err?.response?.data?.detail || err?.message || "Failed to delete object.");
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 py-12">
      <div className="mx-auto mb-10 max-w-4xl px-4 text-center">
        <h1 className="text-4xl font-extrabold tracking-tight text-gray-900 sm:text-5xl">
          Query Builder <span className="text-indigo-600">Workspace</span>
        </h1>
        <p className="mt-4 text-lg text-gray-500">
          Keep the local DuckDB workflow fast and simple while preparing a separate Marcadose route for read-only
          Oracle queries.
        </p>
      </div>

      <div className="mx-auto mb-8 grid max-w-5xl grid-cols-1 gap-4 px-4 lg:grid-cols-2">
        <div className="rounded-lg border border-indigo-100 bg-white p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600">Local</p>
          <h2 className="mt-2 text-xl font-semibold text-gray-900">Query Builder (Local)</h2>
          <p className="mt-2 text-sm text-gray-500">
            Connect to a `.duckdb` file, browse tables, and run the local builder today.
          </p>
          <Link to="/query/local" className="mt-4 inline-flex text-sm font-semibold text-indigo-600 hover:text-indigo-800">
            Open local builder
          </Link>
        </div>

        <div className="rounded-lg border border-blue-100 bg-white p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-blue-600">Remote</p>
          <h2 className="mt-2 text-xl font-semibold text-gray-900">Query Builder (Marcadose)</h2>
          <p className="mt-2 text-sm text-gray-500">
            Connect to Marcadose Oracle for read-only queries, monthly master table selection, and DISCOM UNION reports.
          </p>
          <div className="mt-4 flex items-center justify-between gap-4">
            <Link to="/query/marcadose" className="inline-flex text-sm font-semibold text-blue-600 hover:text-blue-800">
              Open Marcadose setup
            </Link>
            <span
              className={`rounded-full px-3 py-1 text-xs font-semibold ${
                marcadoseConnection.isConnected
                  ? "bg-blue-100 text-blue-700"
                  : marcadoseConnection.isConfigured
                    ? "bg-sky-100 text-sky-700"
                    : "bg-amber-100 text-amber-700"
              }`}
            >
              {marcadoseConnection.isConnected
                ? `Connected${marcadoseConnection.schemaName ? ` (${marcadoseConnection.schemaName})` : ""}`
                : marcadoseConnection.isConfigured
                  ? "Credentials saved"
                  : "Setup needed"}
            </span>
          </div>
        </div>
      </div>

      <div className="mx-auto mb-6 max-w-5xl px-4">
        <section className="rounded-lg border border-amber-200 bg-amber-50 p-4">
          <h3 className="text-sm font-semibold text-amber-900">Global emergency proxy settings</h3>
          <p className="mt-1 text-xs text-amber-800">Used by Drive upload/download advanced settings defaults.</p>
          <div className="mt-3 grid gap-2 sm:grid-cols-4">
            <label className="col-span-4 flex items-center gap-2 text-sm text-amber-900">
              <input type="checkbox" checked={emergencyProxyEnabled} onChange={(e) => setEmergencyProxyEnabled(e.target.checked)} /> Enable emergency proxy by default
            </label>
            <input className="rounded border px-2 py-2 text-sm" value={emergencyProxyHost} onChange={(e) => setEmergencyProxyHost(e.target.value)} placeholder="Proxy host" />
            <input className="rounded border px-2 py-2 text-sm" value={emergencyProxyPort} onChange={(e) => setEmergencyProxyPort(e.target.value)} placeholder="Proxy port" />
            <button type="button" onClick={saveEmergencyProxySettings} className="rounded bg-amber-600 px-3 py-2 text-sm font-semibold text-white">Save proxy settings</button>
          </div>
        </section>
      </div>

      <PathInput
        value={dbPath}
        onChange={setDbPath}
        onConnect={connect}
        isConnecting={isConnecting}
        error={error}
      />

      {tableActionMessage && (
        <div className="mx-auto mt-4 max-w-6xl rounded border border-slate-200 bg-white px-4 py-2 text-sm text-slate-700">
          {tableActionMessage}
        </div>
      )}

      {isConnected && <TableList tables={tables} onDeleteTable={handleDeleteTable} />}
    </div>
  );
};
