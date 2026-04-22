/**
 * useMarcadoseConnection.ts â€” Marcadose credential and Oracle connection management.
 */

import { useState } from "react";
import { connectOracle } from "../api/connectionApi";
import { getTables } from "../api/schemaApi";
import { useAppContext } from "../context/AppContext";
import type { MarcadoseCredentials } from "../types/connection.types";
import type { TableMetadata } from "../types/schema.types";

export interface UseMarcadoseConnectionReturn {
  credentials: MarcadoseCredentials;
  isConfigured: boolean;
  isConnected: boolean;
  isConnecting: boolean;
  schemaName: string;
  tables: TableMetadata[];
  error: string | null;
  saveCredentials: () => boolean;
  connect: () => Promise<void>;
  disconnect: () => void;
  updateCredential: (field: keyof MarcadoseCredentials, value: string) => void;
  clearCredentials: () => void;
}

function emptyCredentials(): MarcadoseCredentials {
  return {
    host: "",
    port: "1521",
    sid: "",
    username: "",
    password: "",
  };
}

export function useMarcadoseConnection(): UseMarcadoseConnectionReturn {
  const appCtx = useAppContext();
  const [credentials, setCredentials] = useState<MarcadoseCredentials>(appCtx.marcadoseConnection.credentials);
  const [error, setError] = useState<string | null>(null);
  const [isConnecting, setIsConnecting] = useState<boolean>(false);

  const validate = (): boolean => {
    if (Object.values(credentials).some((value) => value.trim() === "")) {
      setError("Please fill in host, port, SID, username, and password.");
      return false;
    }

    if (!/^\d+$/.test(credentials.port.trim())) {
      setError("Port must be numeric.");
      return false;
    }
    return true;
  };

  const updateCredential = (field: keyof MarcadoseCredentials, value: string) => {
    setCredentials((prev) => ({ ...prev, [field]: value }));
  };

  const saveCredentials = () => {
    if (!validate()) return false;
    appCtx.setMarcadoseCredentials(credentials);
    setError(null);
    return true;
  };

  const connect = async () => {
    if (!saveCredentials()) return;

    setIsConnecting(true);
    try {
      const response = await connectOracle({
        host: credentials.host.trim(),
        port: Number(credentials.port),
        sid: credentials.sid.trim(),
        username: credentials.username.trim(),
        password: credentials.password,
      });
      const tables = await getTables("oracle");
      appCtx.setMarcadoseConnected(true, tables, response.schema_name);
      setError(null);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || "Failed to connect to Marcadose");
      appCtx.setMarcadoseConnected(false, [], "");
    } finally {
      setIsConnecting(false);
    }
  };

  const disconnect = () => {
    appCtx.setMarcadoseConnected(false, [], "");
    setError(null);
  };

  const clearCredentials = () => {
    setCredentials(emptyCredentials());
    appCtx.clearMarcadoseCredentials();
    setError(null);
  };

  return {
    credentials,
    isConfigured: appCtx.marcadoseConnection.isConfigured,
    isConnected: appCtx.marcadoseConnection.isConnected,
    isConnecting,
    schemaName: appCtx.marcadoseConnection.schemaName,
    tables: appCtx.marcadoseConnection.tables,
    error,
    saveCredentials,
    connect,
    disconnect,
    updateCredential,
    clearCredentials,
  };
}
