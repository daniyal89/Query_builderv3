import { useState } from "react";
import type { ImporterState, ColumnMapping, ImportResult } from "../types/importer.types";
import { uploadCSV, submitMapping } from "../api/importerApi";

export interface UseImporterReturn {
  state: ImporterState;
  handleFileUpload: (file: File) => Promise<void>;
  updateMapping: (index: number, mapping: Partial<ColumnMapping>) => void;
  executeImport: (targetTable: string, createTableIfMissing: boolean) => Promise<ImportResult | undefined>;
  reset: () => void;
}

export function useImporter(): UseImporterReturn {
  const [state, setState] = useState<ImporterState>({
    step: "upload",
    preview: null,
    mappings: [],
    result: null,
    isLoading: false,
    error: null,
  });

  const [fileId, setFileId] = useState<string>("");

  const handleFileUpload = async (file: File) => {
    setState((prev) => ({ ...prev, isLoading: true, error: null }));
    try {
      const data = await uploadCSV(file);
      setFileId(data.file_id);
      
      const mappings: ColumnMapping[] = data.headers.map((h) => ({
        csvColumn: h,
        dbColumn: h.toUpperCase().replace(/[^A-Z0-9_]/g, "_").replace(/^_+|_+$/g, ""),
        skip: false,
      }));

      setState((prev) => ({
        ...prev,
        step: "mapping",
        preview: {
          fileName: file.name,
          headers: data.headers,
          rows: data.preview,
          totalRows: data.preview.length, // approximation
        },
        mappings,
        isLoading: false,
      }));
    } catch (err: any) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: err?.response?.data?.detail || err.message || "Upload failed",
      }));
    }
  };

  const updateMapping = (index: number, updates: Partial<ColumnMapping>) => {
    setState((prev) => {
      const newMappings = [...prev.mappings];
      newMappings[index] = { ...newMappings[index], ...updates };
      return { ...prev, mappings: newMappings };
    });
  };

  const executeImport = async (targetTable: string, createTableIfMissing: boolean) => {
    setState((prev) => ({ ...prev, step: "importing", isLoading: true, error: null }));
    try {
      const result = await submitMapping({
        fileId: fileId,
        targetTable,
        columnMap: state.mappings,
        createTableIfMissing,
      });

      setState((prev) => ({
        ...prev,
        step: "done",
        result,
        isLoading: false,
      }));
      return result;
    } catch (err: any) {
      setState((prev) => ({
        ...prev,
        step: "mapping", // revert
        isLoading: false,
        error: err?.response?.data?.detail || err.message || "Import failed",
      }));
    }
  };

  const reset = () => {
    setFileId("");
    setState({
      step: "upload",
      preview: null,
      mappings: [],
      result: null,
      isLoading: false,
      error: null,
    });
  };

  return { state, handleFileUpload, updateMapping, executeImport, reset };
}
