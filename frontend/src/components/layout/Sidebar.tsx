/**
 * Sidebar.tsx — Primary navigation sidebar.
 */

import React from "react";
import { NavLink } from "react-router-dom";

const linkClassName = ({ isActive }: { isActive: boolean }) =>
  `block rounded-md px-4 py-2 text-sm transition ${
    isActive ? "bg-blue-700 font-semibold text-white" : "text-slate-200 hover:bg-slate-800"
  }`;

export const Sidebar: React.FC = () => {
  return (
    <aside className="flex h-full w-72 flex-col overflow-y-auto border-r border-slate-800 bg-slate-900 text-white shadow-lg">
      <div className="p-6">
        <h2 className="text-2xl font-extrabold tracking-tight">Query Builder</h2>
        <p className="mt-2 text-sm text-slate-400">Local DuckDB plus Marcadose workspace shell.</p>
      </div>
      <nav className="flex-1 space-y-4 px-4 pb-4">
        <div className="space-y-2">
          <p className="px-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Data</p>
          <NavLink to="/" className={linkClassName}>
            Dashboard
          </NavLink>
          <NavLink to="/import" className={linkClassName}>
            Merge & Enrich
          </NavLink>
          <NavLink to="/folder-merge" className={linkClassName}>
            Folder Merge
          </NavLink>
        </div>
        <div className="space-y-2">
          <p className="px-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Querying</p>
          <NavLink to="/query/local" className={linkClassName}>
            Query Builder (Local)
          </NavLink>
          <NavLink to="/query/marcadose" className={linkClassName}>
            Query Builder (Marcadose)
          </NavLink>
        </div>
        <div className="space-y-2">
          <p className="px-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Operations</p>
          <NavLink to="/ftp-download" className={linkClassName}>
            FTP Download
          </NavLink>
          <NavLink to="/sidebar-6-tools" className={linkClassName}>
            Data Tools
          </NavLink>
          <NavLink to="/drive-upload-master" className={linkClassName}>
            Upload master in Drive
          </NavLink>
          <NavLink to="/drive-download" className={linkClassName}>
            Drive Download
          </NavLink>
        </div>
      </nav>
    </aside>
  );
};
