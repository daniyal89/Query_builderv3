/**
 * Sidebar.tsx — Primary navigation sidebar.
 *
 * Renders navigation links to Home (/), Query Builder (/query),
 * and Data Importer (/import). Highlights the active route.
 */

import React from "react";
import { NavLink } from "react-router-dom";

export const Sidebar: React.FC = () => {
  return (
    <aside className="w-64 bg-gray-900 text-white flex flex-col h-full shadow-lg">
      <div className="p-6">
        <h2 className="text-2xl font-extrabold tracking-tight">DuckDB Admin</h2>
      </div>
      <nav className="flex-1 px-4 space-y-2">
        <NavLink to="/" className={({ isActive }) => `block px-4 py-2 rounded-md ${isActive ? "bg-indigo-600" : "hover:bg-gray-800"}`}>
          Dashboard
        </NavLink>
        <NavLink to="/query" className={({ isActive }) => `block px-4 py-2 rounded-md ${isActive ? "bg-indigo-600" : "hover:bg-gray-800"}`}>
          Query Builder
        </NavLink>
        <NavLink to="/import" className={({ isActive }) => `block px-4 py-2 rounded-md ${isActive ? "bg-indigo-600" : "hover:bg-gray-800"}`}>
          Merge & Enrich
        </NavLink>
      </nav>
    </aside>
  );
};
