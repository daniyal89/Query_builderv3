/**
 * Header.tsx — Top application bar.
 *
 * Displays the app title, a connection-status indicator badge
 * (green = connected, gray = disconnected), and a theme toggle.
 */

import React from "react";
import { useAppContext } from "../../context/AppContext";
import { useConnection } from "../../hooks/useConnection";

export const Header: React.FC = () => {
  const { isConnected, dbPath, tables } = useAppContext();
  const { disconnect } = useConnection();

  return (
    <header className="bg-white shadow flex items-center justify-between px-6 py-4">
      <div className="flex items-center space-x-4">
        <h1 className="text-lg font-semibold text-gray-800 whitespace-nowrap overflow-hidden text-ellipsis max-w-sm" title={dbPath || "Data Dashboard"}>
          {dbPath ? dbPath.split('\\').pop()?.split('/').pop() : "Data Dashboard"}
        </h1>
      </div>
      <div>
        {isConnected ? (
          <div className="flex items-center space-x-3">
            <span className="inline-flex items-center space-x-2 bg-green-100 text-green-800 text-sm font-medium px-3 py-1 rounded-full">
              <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
              <span>Connected ({tables.length} tables)</span>
            </span>
            <button
              onClick={disconnect}
              className="text-xs text-red-600 hover:text-red-800 hover:underline border border-transparent hover:border-red-200 px-2 py-1 rounded transition"
            >
              Disconnect
            </button>
          </div>
        ) : (
          <span className="inline-flex items-center space-x-2 bg-gray-100 text-gray-600 text-sm font-medium px-3 py-1 rounded-full">
            <span className="w-2 h-2 rounded-full bg-gray-400"></span>
            <span>Disconnected</span>
          </span>
        )}
      </div>
    </header>
  );
};
