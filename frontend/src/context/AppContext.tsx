/**
 * AppContext.tsx — Global application state provider.
 *
 * Provides cross-component access to: active database path, connection
 * status, and the current table list via React Context.
 */

import React, { createContext, useContext, useState } from "react";
import type { TableMetadata } from "../types/schema.types";

/** Shape of the global application state. */
export interface AppState {
  /** Active DuckDB file path, or empty string if not connected. */
  dbPath: string;
  /** Whether a database connection is currently active. */
  isConnected: boolean;
  /** List of tables from the connected database. */
  tables: TableMetadata[];
  /** Update the active database path. */
  setDbPath: (path: string) => void;
  /** Update the connection status and table list. */
  setConnected: (connected: boolean, tables: TableMetadata[]) => void;
}

/** React Context for global application state. */
export const AppContext = createContext<AppState | undefined>(undefined);

/** Hook to consume AppContext; throws if used outside AppProvider. */
export function useAppContext(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) {
    throw new Error("useAppContext must be used within an AppProvider");
  }
  return ctx;
}

/**
 * AppProvider component.
 *
 * Wraps the application tree and provides global state via AppContext.
 */
export function AppProvider({ children }: { children: React.ReactNode }): JSX.Element {
  const [dbPath, setDbPathState] = useState<string>(() => {
    return localStorage.getItem("duckdb_path") || "";
  });
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [tables, setTables] = useState<TableMetadata[]>([]);

  const setDbPath = (path: string) => {
    setDbPathState(path);
    if (path) {
      localStorage.setItem("duckdb_path", path);
    } else {
      localStorage.removeItem("duckdb_path");
    }
  };

  const setConnected = (connected: boolean, tablesList: TableMetadata[]) => {
    setIsConnected(connected);
    setTables(tablesList);
  };

  return (
    <AppContext.Provider value={{ dbPath, isConnected, tables, setDbPath, setConnected }}>
      {children}
    </AppContext.Provider>
  );
}
