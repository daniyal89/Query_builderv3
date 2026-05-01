/**
 * PageShell.tsx — Root layout wrapper.
 *
 * Composes Sidebar + Header into a consistent page frame. All route
 * page components render inside this shell's content area.
 */

import React from "react";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";
import { useThemeMode } from "../../hooks/useThemeMode";

const PageShell: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { theme, toggleTheme } = useThemeMode();

  return (
    <div className="flex h-screen overflow-hidden bg-gray-100 font-sans text-slate-900 transition-colors dark:bg-slate-950 dark:text-slate-100">
      <Sidebar />
      <div className="flex flex-col flex-1 overflow-hidden">
        <Header theme={theme} onToggleTheme={toggleTheme} />
        <main className="flex-1 overflow-y-auto bg-gray-50 p-4 transition-colors dark:bg-slate-950 sm:p-6 lg:p-8">
          {children}
        </main>
      </div>
    </div>
  );
};

export default PageShell;
