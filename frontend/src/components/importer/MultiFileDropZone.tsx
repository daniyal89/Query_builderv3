import React, { useCallback, useState } from "react";

interface MultiFileDropZoneProps {
  onUpload: (files: File[]) => void;
  isLoading: boolean;
}

const ACCEPTED_EXTENSIONS = [".csv", ".xlsx", ".xls"];
const ACCEPT_ATTRIBUTE = [
  ".csv",
  ".xlsx",
  ".xls",
  "text/csv",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.ms-excel",
].join(", ");

function isSupportedFile(file: File): boolean {
  const lowerName = file.name.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((extension) => lowerName.endsWith(extension));
}

export const MultiFileDropZone: React.FC<MultiFileDropZoneProps> = ({ onUpload, isLoading }) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  const setValidatedFile = (file: File) => {
    if (!isSupportedFile(file)) {
      setSelectedFile(null);
      setError("Only .csv, .xlsx, and .xls files are supported.");
      return;
    }

    setSelectedFile(file);
    setError(null);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setValidatedFile(e.target.files[0]);
    }
  };

  const handleDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      setValidatedFile(e.dataTransfer.files[0]);
    }
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  }, []);

  const handleSubmit = () => {
    if (selectedFile) {
      onUpload([selectedFile]);
    }
  };

  return (
    <div className="multi-file-dropzone p-6 border-2 border-dashed border-gray-300 rounded-lg text-center"
         onDrop={handleDrop}
         onDragOver={handleDragOver}>
      
      <div className="mb-4">
        <label className="block text-lg font-medium text-gray-700 mb-2">
          Upload Excel / CSV file
        </label>
        <p className="text-gray-500 text-sm mb-4">
          Drag and drop one `.csv`, `.xlsx`, or `.xls` file here, or click to select a file.
        </p>
        <input
          type="file"
          accept={ACCEPT_ATTRIBUTE}
          onChange={handleFileChange}
          className="hidden"
          id="file-upload"
        />
        <label
          htmlFor="file-upload"
          className="cursor-pointer bg-blue-600 text-white px-4 py-2 rounded shadow hover:bg-blue-700 transition"
        >
          Select File
        </label>
      </div>

      {error && (
        <div className="mb-4 rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {selectedFile && (
        <div className="mt-6 text-left">
          <h4 className="font-medium text-gray-900 mb-2">Selected File:</h4>
          <div className="mb-4 rounded border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-600">
            {selectedFile.name} ({(selectedFile.size / 1024 / 1024).toFixed(2)} MB)
          </div>
          <button
            onClick={handleSubmit}
            disabled={isLoading}
            className="w-full bg-green-600 text-white px-4 py-2 rounded shadow hover:bg-green-700 disabled:opacity-50 transition"
          >
            {isLoading ? "Uploading..." : "Upload & Analyze File"}
          </button>
        </div>
      )}
    </div>
  );
};
