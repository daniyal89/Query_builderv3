/**
 * MarcadoseConnectionForm.tsx â€” Credential form plus Oracle connect action.
 */

import React from "react";
import { useMarcadoseConnection } from "../../hooks/useMarcadoseConnection";

const FIELDS = [
  { key: "host", label: "Host", placeholder: "oracle.example.com", type: "text" },
  { key: "port", label: "Port", placeholder: "1521", type: "text" },
  { key: "sid", label: "SID", placeholder: "ORCL", type: "text" },
  { key: "username", label: "Username", placeholder: "Read-only username", type: "text" },
  { key: "password", label: "Password", placeholder: "Password", type: "password" },
] as const;

export const MarcadoseConnectionForm: React.FC = () => {
  const {
    credentials,
    isConfigured,
    isConnected,
    isConnecting,
    schemaName,
    error,
    saveCredentials,
    connect,
    disconnect,
    updateCredential,
    clearCredentials,
  } = useMarcadoseConnection();

  return (
    <div className="mb-6 rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-gray-800">Marcadose Credentials</h2>
          <p className="mt-1 text-sm text-gray-500">
            Saved only in this browser for autofill. Oracle execution is read-only and uses the backend thin-mode
            connection.
          </p>
        </div>
        <span
          className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${
            isConnected
              ? "bg-emerald-100 text-emerald-700"
              : isConfigured
                ? "bg-blue-100 text-blue-700"
                : "bg-amber-100 text-amber-700"
          }`}
        >
          {isConnected ? `Connected${schemaName ? ` (${schemaName})` : ""}` : isConfigured ? "Saved locally" : "Setup needed"}
        </span>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {FIELDS.map((field) => (
          <label key={field.key} className="block">
            <span className="mb-1 block text-sm font-medium text-gray-700">{field.label}</span>
            <input
              type={field.type}
              value={credentials[field.key]}
              onChange={(e) => updateCredential(field.key, e.target.value)}
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              placeholder={field.placeholder}
            />
          </label>
        ))}
      </div>

      {error && (
        <div className="mt-4 rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-3">
        <button
          onClick={saveCredentials}
          className="rounded border border-indigo-200 px-4 py-2 text-sm font-medium text-indigo-700 transition hover:bg-indigo-50"
        >
          Save Credentials
        </button>
        <button
          onClick={connect}
          disabled={isConnecting}
          className="rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-700 disabled:opacity-50"
        >
          {isConnecting ? "Connecting..." : isConnected ? "Reconnect" : "Connect to Marcadose"}
        </button>
        {isConnected && (
          <button
            onClick={disconnect}
            className="rounded border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50"
          >
            Disconnect
          </button>
        )}
        <button
          onClick={clearCredentials}
          className="rounded border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50"
        >
          Clear Saved Values
        </button>
      </div>
    </div>
  );
};
