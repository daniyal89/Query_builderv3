/**
 * Sidebar.tsx — Primary navigation sidebar.
 */

import React, { useEffect } from "react";
import { NavLink } from "react-router-dom";
import { prefetchRoute, scheduleRoutePrefetch } from "../../app/routePrefetch";

const linkClassName = ({ isActive }: { isActive: boolean }) =>
  `block rounded-md px-4 py-2 text-sm transition ${
    isActive ? "bg-blue-700 font-semibold text-white" : "text-slate-200 hover:bg-slate-800"
  }`;

const navigationSections = [
  {
    title: "Data",
    links: [
      { to: "/", label: "Dashboard" },
      { to: "/import", label: "Merge & Enrich" },
      { to: "/folder-merge", label: "Folder Merge" },
    ],
  },
  {
    title: "Querying",
    links: [
      { to: "/query/local", label: "Query Builder (Local)" },
      { to: "/query/marcadose", label: "Query Builder (Marcadose)" },
    ],
  },
  {
    title: "Operations",
    links: [
      { to: "/ftp-download", label: "FTP Download" },
      { to: "/sidebar-6-tools", label: "Data Tools" },
      { to: "/drive-upload-master", label: "Upload master in Drive" },
      { to: "/drive-download", label: "Drive Download" },
    ],
  },
] as const;

export const Sidebar: React.FC = () => {
  useEffect(() => {
    return scheduleRoutePrefetch(["/query/local", "/import", "/sidebar-6-tools"]);
  }, []);

  const handlePrefetch = (path: string) => {
    void prefetchRoute(path);
  };

  return (
    <aside className="flex h-full w-72 flex-col overflow-y-auto border-r border-slate-800 bg-slate-900 text-white shadow-lg transition-colors dark:border-slate-950 dark:bg-slate-950">
      <div className="p-6">
        <h2 className="text-2xl font-extrabold tracking-tight">Query Builder</h2>
        <p className="mt-2 text-sm text-slate-400 dark:text-slate-500">Local DuckDB plus Marcadose workspace shell.</p>
      </div>
      <nav className="flex-1 space-y-4 px-4 pb-4">
        {navigationSections.map((section) => (
          <div key={section.title} className="space-y-2">
            <p className="px-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{section.title}</p>
            {section.links.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                className={linkClassName}
                onMouseEnter={() => handlePrefetch(link.to)}
                onFocus={() => handlePrefetch(link.to)}
                onTouchStart={() => handlePrefetch(link.to)}
              >
                {link.label}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
    </aside>
  );
};
