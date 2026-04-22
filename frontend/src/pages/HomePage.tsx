/**
 * HomePage.tsx — Landing page with DuckDB path input and table overview.
 *
 * Contains the PathInput component for entering a .duckdb file path,
 * a connect button, and after connection, the TableList showing all
 * discovered tables with their metadata.
 */
import React, { useEffect } from "react";
import { PathInput } from "../components/home/PathInput";
import { TableList } from "../components/home/TableList";
import { useConnection } from "../hooks/useConnection";

export const HomePage: React.FC = () => {
  const { dbPath, setDbPath, connect, isConnecting, isConnected, tables, error } = useConnection();

  // Auto-connect if there's a cached path in localStorage
  useEffect(() => {
    if (dbPath && !isConnected && !isConnecting && !error) {
      connect();
    }
  }, [dbPath, isConnected, isConnecting, error, connect]);

  return (
    <div className="min-h-screen bg-gray-50 py-12">
      <div className="text-center max-w-3xl mx-auto mb-10 px-4">
        <h1 className="text-4xl font-extrabold text-gray-900 tracking-tight sm:text-5xl">
          DuckDB <span className="text-indigo-600">Reconciliation Dashboard</span>
        </h1>
        <p className="mt-4 text-lg text-gray-500">
          Connect locally to your data warehouse engine to query tables, combine schemas, and run fast reporting.
        </p>
      </div>

      <PathInput
        value={dbPath}
        onChange={setDbPath}
        onConnect={connect}
        isConnecting={isConnecting}
        error={error}
      />

      {isConnected && (
        <TableList tables={tables} />
      )}
    </div>
  );
};
