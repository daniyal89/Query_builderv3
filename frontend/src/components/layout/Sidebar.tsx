/**
 * Sidebar.tsx — Primary navigation sidebar.
 */

import React from "react";
import { NavLink } from "react-router-dom";

const linkClassName = ({ isActive }: { isActive: boolean }) =>
  `block rounded-md px-4 py-2 ${isActive ? "bg-indigo-600" : "hover:bg-gray-800"}`;

export const Sidebar: React.FC = () => {
  return (
    <aside className="flex h-full w-72 flex-col bg-gray-900 text-white shadow-lg">
      <div className="p-6">
        <h2 className="text-2xl font-extrabold tracking-tight">Query Builder</h2>
        <p className="mt-2 text-sm text-gray-400">Local DuckDB plus Marcadose workspace shell.</p>
      </div>
      <nav className="flex-1 space-y-2 px-4">
        <NavLink to="/" className={linkClassName}>
          Dashboard
        </NavLink>
        <NavLink to="/query/local" className={linkClassName}>
          Query Builder (Local)
        </NavLink>
        <NavLink to="/query/marcadose" className={linkClassName}>
          Query Builder (Marcadose)
        </NavLink>
        <NavLink to="/import" className={linkClassName}>
          Merge & Enrich
        </NavLink>
        <NavLink to="/folder-merge" className={linkClassName}>
          Folder Merge
        </NavLink>
        <NavLink to="/ftp-download" className={linkClassName}>
          FTP Download
        </NavLink>
        <NavLink to="/drive-upload-master" className={linkClassName}>
          Upload master in Drive
        </NavLink>
        <NavLink to="/drive-download" className={linkClassName}>
          Drive Download
        </NavLink>
      </nav>
    </aside>
  );
};
