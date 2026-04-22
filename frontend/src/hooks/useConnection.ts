/**
 * useConnection.ts — Custom hook for DuckDB connection state management.
 *
 * Encapsulates the connection lifecycle: path input, connect action,
 * status tracking, and table list retrieval.
 */

import { useState } from "react";
import type { TableMetadata } from "../types/schema.types";
import { connect as connectApi } from "../api/connectionApi";
import { getTables } from "../api/schemaApi";
import { useAppContext } from "../context/AppContext";

export interface UseConnectionReturn {
  dbPath: string;
  setDbPath: (path: string) => void;
  isConnected: boolean;
  isConnecting: boolean;
  tables: TableMetadata[];
  error: string | null;
  connect: () => Promise<void>;
  disconnect: () => void;
}

export function useConnection(): UseConnectionReturn {
  const appCtx = useAppContext();
  const [dbPath, setDbPathLocal] = useState<string>(appCtx.dbPath || "");
  const [isConnecting, setIsConnecting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Read live connection state from global context
  const isConnected = appCtx.isConnected;
  const tables = appCtx.tables;

  const setDbPath = (path: string) => {
    setDbPathLocal(path);
    appCtx.setDbPath(path);
  };

  const connect = async () => {
    const path = dbPath || appCtx.dbPath;
    if (!path) {
      setError("Please enter a valid DuckDB file path.");
      return;
    }
    setIsConnecting(true);
    setError(null);
    try {
      await connectApi({ db_path: path });
      const tablesData = await getTables();
      // Update global context so all pages see the connection
      appCtx.setConnected(true, tablesData);
      appCtx.setDbPath(path);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || "Failed to connect to DuckDB");
      appCtx.setConnected(false, []);
    } finally {
      setIsConnecting(false);
    }
  };

  const disconnect = () => {
    setDbPathLocal("");
    appCtx.setConnected(false, []);
    appCtx.setDbPath("");
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
  };
}
