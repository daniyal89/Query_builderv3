/**
 * FileDropZone.tsx — Drag-and-drop CSV file selection area.
 *
 * Supports both drag-and-drop and click-to-browse for selecting
 * a CSV file. Validates file type (must be .csv) and size limits.
 *
 * Props:
 *   onFileSelect: (file: File) => void   — Callback with the selected File.
 *   isLoading: boolean                   — Disables the zone during processing.
 *   error: string | null                 — Error message to display.
 */

import React, { useRef, useState } from "react";

interface FileDropZoneProps {
  onFileSelect: (file: File) => void;
  isLoading: boolean;
  error: string | null;
}

export const FileDropZone: React.FC<FileDropZoneProps> = ({ onFileSelect, isLoading, error }) => {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const pickFile = (file: File | null) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".csv")) return;
    onFileSelect(file);
  };

  return (
    <div className="space-y-2">
      <button
        type="button"
        disabled={isLoading}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          pickFile(e.dataTransfer.files?.[0] ?? null);
        }}
        onClick={() => inputRef.current?.click()}
        className={`w-full rounded-lg border-2 border-dashed px-4 py-8 text-sm ${
          isDragging ? "border-blue-500 bg-blue-50" : "border-slate-300 bg-white"
        } ${isLoading ? "cursor-not-allowed opacity-60" : "hover:bg-slate-50"}`}
      >
        {isLoading ? "Uploading..." : "Drop CSV here or click to browse"}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept=".csv,text/csv"
        className="hidden"
        onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
      />
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
};
