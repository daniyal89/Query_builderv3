/**
 * Header.tsx — Top application bar.
 */

import React from "react";
import { useLocation } from "react-router-dom";
import { useAppContext } from "../../context/AppContext";
import { useConnection } from "../../hooks/useConnection";
import { useMarcadoseConnection } from "../../hooks/useMarcadoseConnection";

function getPageTitle(pathname: string, dbPath: string): string {
  if (pathname.startsWith("/query/local")) return "Query Builder (Local)";
  if (pathname.startsWith("/query/marcadose")) return "Query Builder (Marcadose)";
  if (pathname.startsWith("/import")) return "Merge & Enrich";
  if (pathname.startsWith("/folder-merge")) return "Folder Merge";
  if (pathname.startsWith("/ftp-download")) return "FTP Download";
  if (pathname.startsWith("/sidebar-6-tools")) return "Sidebar-6 Data Tools";
  return dbPath ? dbPath.split("\\").pop()?.split("/").pop() || "Data Dashboard" : "Data Dashboard";
}

export const Header: React.FC = () => {
  const location = useLocation();
  const { duckdbConnection, marcadoseConnection } = useAppContext();
  const { disconnect } = useConnection();
  const { disconnect: disconnectMarcadose } = useMarcadoseConnection();

  return (
    <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-4 shadow-sm">
      <div className="flex items-center space-x-4">
        <h1
          className="max-w-sm overflow-hidden text-ellipsis whitespace-nowrap text-lg font-semibold text-slate-800"
          title={getPageTitle(location.pathname, duckdbConnection.dbPath)}
        >
          {getPageTitle(location.pathname, duckdbConnection.dbPath)}
        </h1>
      </div>

      <div className="flex flex-wrap items-center justify-end gap-3">
        <span
          className={`inline-flex items-center space-x-2 rounded-full px-3 py-1 text-sm font-medium ${
            duckdbConnection.isConnected ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-600"
          }`}
        >
          <span
            className={`h-2 w-2 rounded-full ${
              duckdbConnection.isConnected ? "animate-pulse bg-emerald-500" : "bg-slate-400"
            }`}
          ></span>
          <span>
            Local {duckdbConnection.isConnected ? `(${duckdbConnection.tables.length} tables)` : "(disconnected)"}
          </span>
        </span>

        <span
          className={`inline-flex items-center space-x-2 rounded-full px-3 py-1 text-sm font-medium ${
            marcadoseConnection.isConnected
              ? "bg-blue-100 text-blue-800"
              : marcadoseConnection.isConfigured
                ? "bg-cyan-100 text-cyan-800"
                : "bg-amber-100 text-amber-700"
          }`}
        >
          <span
            className={`h-2 w-2 rounded-full ${
              marcadoseConnection.isConnected
                ? "bg-blue-500"
                : marcadoseConnection.isConfigured
                  ? "bg-cyan-500"
                  : "bg-amber-500"
            }`}
          ></span>
          <span>
            Marcadose{" "}
            {marcadoseConnection.isConnected
              ? `(${marcadoseConnection.tables.length} objects)`
              : marcadoseConnection.isConfigured
                ? "(saved)"
                : "(setup needed)"}
          </span>
        </span>

        {duckdbConnection.isConnected && (
          <button
            onClick={disconnect}
            className="rounded border border-rose-200 px-2 py-1 text-xs text-rose-600 transition hover:bg-rose-50 hover:text-rose-800"
          >
            Disconnect Local
          </button>
        )}

        {marcadoseConnection.isConnected && (
          <button
            onClick={disconnectMarcadose}
            className="rounded border border-blue-200 px-2 py-1 text-xs text-blue-700 transition hover:bg-blue-50 hover:text-blue-900"
          >
            Disconnect Marcadose
          </button>
        )}
      </div>
    </header>
  );
};
