import React from "react";
import { render, type RenderOptions } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import {
  AppContext,
  type AppState,
} from "../src/context/AppContext";
import type {
  DuckdbConnectionState,
  MarcadoseConnectionState,
  MarcadoseCredentials,
} from "../src/types/connection.types";
import type { TableMetadata } from "../src/types/schema.types";

type RenderWithAppOptions = {
  route?: string;
  duckdbConnection?: Partial<DuckdbConnectionState>;
  marcadoseConnection?: Partial<MarcadoseConnectionState>;
} & Omit<RenderOptions, "wrapper">;

const defaultMarcadoseCredentials: MarcadoseCredentials = {
  host: "",
  port: "1521",
  sid: "",
  username: "",
  password: "",
};

function createDefaultDuckdbConnection(): DuckdbConnectionState {
  return {
    dbPath: "",
    isConnected: false,
    tables: [],
  };
}

function createDefaultMarcadoseConnection(): MarcadoseConnectionState {
  return {
    credentials: defaultMarcadoseCredentials,
    isConfigured: false,
    isConnected: false,
    tables: [],
    schemaName: "",
  };
}

function TestAppProvider({
  children,
  initialDuckdbConnection,
  initialMarcadoseConnection,
}: {
  children: React.ReactNode;
  initialDuckdbConnection?: Partial<DuckdbConnectionState>;
  initialMarcadoseConnection?: Partial<MarcadoseConnectionState>;
}) {
  const [duckdbConnection, setDuckdbConnection] = React.useState<DuckdbConnectionState>({
    ...createDefaultDuckdbConnection(),
    ...initialDuckdbConnection,
  });
  const [marcadoseConnection, setMarcadoseConnection] = React.useState<MarcadoseConnectionState>({
    ...createDefaultMarcadoseConnection(),
    ...initialMarcadoseConnection,
    credentials: {
      ...defaultMarcadoseCredentials,
      ...(initialMarcadoseConnection?.credentials ?? {}),
    },
  });

  const contextValue = React.useMemo<AppState>(
    () => ({
      duckdbConnection,
      marcadoseConnection,
      setDuckdbPath: (path: string) => {
        setDuckdbConnection((prev) => ({ ...prev, dbPath: path }));
      },
      setDuckdbConnected: (connected: boolean, tables: TableMetadata[]) => {
        setDuckdbConnection((prev) => ({ ...prev, isConnected: connected, tables }));
      },
      setMarcadoseCredentials: (credentials) => {
        setMarcadoseConnection((prev) => ({
          ...prev,
          credentials,
          isConfigured: Object.values(credentials).every((value) => value.trim() !== ""),
        }));
      },
      setMarcadoseConnected: (connected: boolean, tables: TableMetadata[], schemaName: string) => {
        setMarcadoseConnection((prev) => ({
          ...prev,
          isConnected: connected,
          tables,
          schemaName,
        }));
      },
      clearMarcadoseCredentials: () => {
        setMarcadoseConnection(createDefaultMarcadoseConnection());
      },
    }),
    [duckdbConnection, marcadoseConnection],
  );

  return <AppContext.Provider value={contextValue}>{children}</AppContext.Provider>;
}

export function renderWithAppContext(
  ui: React.ReactElement,
  {
    route = "/",
    duckdbConnection,
    marcadoseConnection,
    ...renderOptions
  }: RenderWithAppOptions = {},
) {
  return render(ui, {
    wrapper: ({ children }) => (
      <MemoryRouter initialEntries={[route]}>
        <TestAppProvider
          initialDuckdbConnection={duckdbConnection}
          initialMarcadoseConnection={marcadoseConnection}
        >
          {children}
        </TestAppProvider>
      </MemoryRouter>
    ),
    ...renderOptions,
  });
}
