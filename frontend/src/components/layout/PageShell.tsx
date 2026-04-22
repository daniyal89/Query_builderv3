/**
 * PageShell.tsx — Root layout wrapper.
 *
 * Composes Sidebar + Header into a consistent page frame. All route
 * page components render inside this shell's content area.
 */

import React from "react";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";

const PageShell: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <div className="flex h-screen bg-gray-100 font-sans overflow-hidden">
      <Sidebar />
      <div className="flex flex-col flex-1 overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 bg-gray-50">
          {children}
        </main>
      </div>
    </div>
  );
};

export default PageShell;
