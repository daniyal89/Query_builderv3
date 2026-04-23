/**
 * MarcadoseQueryBuilderPage.tsx â€” Marcadose Oracle builder page.
 */

import React from "react";
import { Link } from "react-router-dom";
import { MarcadoseConnectionForm } from "../components/query/MarcadoseConnectionForm";
import { QueryBuilderWorkspace } from "../components/query/QueryBuilderWorkspace";
import { useMarcadoseConnection } from "../hooks/useMarcadoseConnection";

export const MarcadoseQueryBuilderPage: React.FC = () => {
  const { isConnected, schemaName, tables } = useMarcadoseConnection();

  if (isConnected) {
    return (
      <QueryBuilderWorkspace
        engine="oracle"
        title={`Query Builder (Marcadose${schemaName ? ` - ${schemaName}` : ""})`}
        tables={tables}
      />
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="mx-auto max-w-6xl">
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-gray-900">Query Builder (Marcadose)</h1>
          <p className="mt-2 max-w-3xl text-sm text-gray-500">
            Marcadose uses a read-only Oracle connection. The backend validates Oracle queries server-side before
            execution.
          </p>
        </div>

        <MarcadoseConnectionForm />

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-gray-800">Current Setup</h2>
            <p className="mt-4 text-sm text-gray-500">
              Save Oracle credentials and connect to load Marcadose tables. Once connected, this page will switch into
              the query builder workspace automatically.
            </p>
          </div>

          <div className="rounded-lg border border-dashed border-gray-300 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-gray-800">Read-Only Rules</h2>
            <ul className="mt-4 list-disc space-y-2 pl-5 text-sm text-gray-600">
              <li>Only `SELECT` and `WITH ... SELECT` statements are allowed.</li>
              <li>DML, DDL, and locking statements are rejected server-side.</li>
              <li>Use the local builder for table/view creation or writable prep work.</li>
            </ul>
            <div className="mt-6 rounded border border-blue-100 bg-blue-50 p-4 text-sm text-blue-800">
              If you need local staging or write operations first, use the DuckDB builder.
              <div className="mt-3">
                <Link to="/query/local" className="font-semibold text-blue-700 hover:text-blue-900">
                  Open Query Builder (Local)
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
