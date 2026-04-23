/**
 * useConnection.ts â€” Custom hook for local DuckDB connection state management.
 */

import { useState } from "react";
import { connectDuckdb } from "../api/connectionApi";
import { getTables } from "../api/schemaApi";
import { useAppContext } from "../context/AppContext";
import type { TableMetadata } from "../types/schema.types";

export interface UseConnectionReturn {
  dbPath: string;
  setDbPath: (path: string) => void;
  isConnected: boolean;
  isConnecting: boolean;
  tables: TableMetadata[];
  error: string | null;
  connect: () => Promise<void>;
  disconnect: () => void;
  refreshTables: () => Promise<TableMetadata[]>;
}

export function useConnection(): UseConnectionReturn {
  const appCtx = useAppContext();
  const [dbPath, setDbPathLocal] = useState<string>(appCtx.duckdbConnection.dbPath || "");
  const [isConnecting, setIsConnecting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const isConnected = appCtx.duckdbConnection.isConnected;
  const tables = appCtx.duckdbConnection.tables;

  const setDbPath = (path: string) => {
    setDbPathLocal(path);
    appCtx.setDuckdbPath(path);
  };

  const connect = async () => {
    const path = dbPath || appCtx.duckdbConnection.dbPath;
    if (!path) {
      setError("Please enter a valid DuckDB file path.");
      return;
    }

    setIsConnecting(true);
    setError(null);
    try {
      await connectDuckdb({ db_path: path });
      const tablesData = await getTables("duckdb");
      appCtx.setDuckdbConnected(true, tablesData);
      appCtx.setDuckdbPath(path);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || "Failed to connect to DuckDB");
      appCtx.setDuckdbConnected(false, []);
    } finally {
      setIsConnecting(false);
    }
  };

  const refreshTables = async () => {
    const tablesData = await getTables("duckdb");
    appCtx.setDuckdbConnected(true, tablesData);
    return tablesData;
  };

  const disconnect = () => {
    appCtx.setDuckdbConnected(false, []);
    setError(null);
  };

  return {
    dbPath,
    setDbPath,
    isConnected,
    isConnecting,
    tables,
    error,
    connect,
    disconnect,
    refreshTables,
  };
}
