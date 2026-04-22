import React, { useCallback, useState } from "react";

interface MultiFileDropZoneProps {
  onUpload: (files: File[]) => void;
  isLoading: boolean;
}

export const MultiFileDropZone: React.FC<MultiFileDropZoneProps> = ({ onUpload, isLoading }) => {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setSelectedFiles(Array.from(e.target.files));
    }
  };

  const handleDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      setSelectedFiles(Array.from(e.dataTransfer.files));
    }
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  }, []);

  const handleSubmit = () => {
    if (selectedFiles.length > 0) {
      onUpload(selectedFiles);
    }
  };

  return (
    <div className="multi-file-dropzone p-6 border-2 border-dashed border-gray-300 rounded-lg text-center"
         onDrop={handleDrop}
         onDragOver={handleDragOver}>
      
      <div className="mb-4">
        <label className="block text-lg font-medium text-gray-700 mb-2">
          Upload Excel / CSV files
        </label>
        <p className="text-gray-500 text-sm mb-4">
          Drag and drop multiple files here, or click to select files.
        </p>
        <input
          type="file"
          multiple
          accept=".csv, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, application/vnd.ms-excel"
          onChange={handleFileChange}
          className="hidden"
          id="file-upload"
        />
        <label
          htmlFor="file-upload"
          className="cursor-pointer bg-blue-600 text-white px-4 py-2 rounded shadow hover:bg-blue-700 transition"
        >
          Select Files
        </label>
      </div>

      {selectedFiles.length > 0 && (
        <div className="mt-6 text-left">
          <h4 className="font-medium text-gray-900 mb-2">Selected Files:</h4>
          <ul className="list-disc pl-5 mb-4 text-sm text-gray-600">
            {selectedFiles.map((file, i) => (
              <li key={i}>{file.name} ({(file.size / 1024 / 1024).toFixed(2)} MB)</li>
            ))}
          </ul>
          <button
            onClick={handleSubmit}
            disabled={isLoading}
            className="w-full bg-green-600 text-white px-4 py-2 rounded shadow hover:bg-green-700 disabled:opacity-50 transition"
          >
            {isLoading ? "Uploading..." : "Upload & Analyze Sheets"}
          </button>
        </div>
      )}
    </div>
  );
};
