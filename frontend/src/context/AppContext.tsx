/**
 * AppContext.tsx â€” Global application state provider.
 */

import React, { createContext, useContext, useState } from "react";
import type {
  DuckdbConnectionState,
  MarcadoseConnectionState,
  MarcadoseCredentials,
} from "../types/connection.types";
import type { TableMetadata } from "../types/schema.types";

const MARCADOSE_STORAGE_KEY = "marcadose_credentials";

const EMPTY_MARCADOSE_CREDENTIALS: MarcadoseCredentials = {
  host: "",
  port: "1521",
  sid: "",
  username: "",
  password: "",
};

function hasMarcadoseCredentials(credentials: MarcadoseCredentials): boolean {
  return Object.values(credentials).every((value) => value.trim() !== "");
}

function loadMarcadoseCredentials(): MarcadoseCredentials {
  const raw = localStorage.getItem(MARCADOSE_STORAGE_KEY);
  if (!raw) return EMPTY_MARCADOSE_CREDENTIALS;

  try {
    const parsed = JSON.parse(raw) as Partial<MarcadoseCredentials>;
    return {
      host: parsed.host ?? "",
      port: parsed.port ?? "1521",
      sid: parsed.sid ?? "",
      username: parsed.username ?? "",
      password: parsed.password ?? "",
    };
  } catch {
    return EMPTY_MARCADOSE_CREDENTIALS;
  }
}

export interface AppState {
  duckdbConnection: DuckdbConnectionState;
  marcadoseConnection: MarcadoseConnectionState;
  setDuckdbPath: (path: string) => void;
  setDuckdbConnected: (connected: boolean, tables: TableMetadata[]) => void;
  setMarcadoseCredentials: (credentials: MarcadoseCredentials) => void;
  setMarcadoseConnected: (connected: boolean, tables: TableMetadata[], schemaName: string) => void;
  clearMarcadoseCredentials: () => void;
}

export const AppContext = createContext<AppState | undefined>(undefined);

export function useAppContext(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) {
    throw new Error("useAppContext must be used within an AppProvider");
  }
  return ctx;
}

export function AppProvider({ children }: { children: React.ReactNode }): JSX.Element {
  const [duckdbConnection, setDuckdbConnection] = useState<DuckdbConnectionState>(() => ({
    dbPath: localStorage.getItem("duckdb_path") || "",
    isConnected: false,
    tables: [],
  }));
  const [marcadoseConnection, setMarcadoseConnection] = useState<MarcadoseConnectionState>(() => {
    const credentials = loadMarcadoseCredentials();
    return {
      credentials,
      isConfigured: hasMarcadoseCredentials(credentials),
      isConnected: false,
      tables: [],
      schemaName: "",
    };
  });

  const setDuckdbPath = (path: string) => {
    setDuckdbConnection((prev) => ({ ...prev, dbPath: path }));
    if (path) {
      localStorage.setItem("duckdb_path", path);
    } else {
      localStorage.removeItem("duckdb_path");
    }
  };

  const setDuckdbConnected = (connected: boolean, tables: TableMetadata[]) => {
    setDuckdbConnection((prev) => ({ ...prev, isConnected: connected, tables }));
  };

  const setMarcadoseCredentials = (credentials: MarcadoseCredentials) => {
    const normalized = {
      host: credentials.host.trim(),
      port: credentials.port.trim(),
      sid: credentials.sid.trim(),
      username: credentials.username.trim(),
      password: credentials.password,
    };

    setMarcadoseConnection((prev) => ({
      ...prev,
      credentials: normalized,
      isConfigured: hasMarcadoseCredentials(normalized),
    }));
    localStorage.setItem(MARCADOSE_STORAGE_KEY, JSON.stringify(normalized));
  };

  const setMarcadoseConnected = (connected: boolean, tables: TableMetadata[], schemaName: string) => {
    setMarcadoseConnection((prev) => ({
      ...prev,
      isConnected: connected,
      tables,
      schemaName,
    }));
  };

  const clearMarcadoseCredentials = () => {
    setMarcadoseConnection({
      credentials: EMPTY_MARCADOSE_CREDENTIALS,
      isConfigured: false,
      isConnected: false,
      tables: [],
      schemaName: "",
    });
    localStorage.removeItem(MARCADOSE_STORAGE_KEY);
  };

  return (
    <AppContext.Provider
      value={{
        duckdbConnection,
        marcadoseConnection,
        setDuckdbPath,
        setDuckdbConnected,
        setMarcadoseCredentials,
        setMarcadoseConnected,
        clearMarcadoseCredentials,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}
