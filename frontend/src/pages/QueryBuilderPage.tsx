/**
 * QueryBuilderPage.tsx â€” Local DuckDB query builder page.
 */

import React from "react";
import { QueryBuilderWorkspace } from "../components/query/QueryBuilderWorkspace";
import { useConnection } from "../hooks/useConnection";

export const QueryBuilderPage: React.FC = () => {
  const { tables, refreshTables } = useConnection();

  return (
    <QueryBuilderWorkspace
      engine="duckdb"
      title="Query Builder (Local)"
      tables={tables}
      onLocalSchemaChanged={refreshTables}
    />
  );
};
