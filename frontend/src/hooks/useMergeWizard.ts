/**
 * useMergeWizard.ts — React hook orchestrating the Merge and Enrichment UI state.
 */

// @ts-nocheck
import { useState } from "react";
import { uploadSheets, mergeSheets, enrichData } from "../api/mergeApi";
import type {
  MergeWizardState,
  ColumnResolution,
  CompositeKey,
  ConflictResolutionMap,
  EnrichmentRequest
} from "../types/merge.types";

export function useMergeWizard() {
  const [state, setState] = useState<MergeWizardState>({
    step: "upload",
    uploadResult: null,
    resolutions: [],
    compositeKey: null,
    mergeResult: null,
    enrichResult: null,
    isLoading: false,
    error: null,
  });

  const handleUpload = async (files: File[]) => {
    setState((prev) => ({ ...prev, isLoading: true, error: null }));
    try {
      const result = await uploadSheets(files);
      // Auto-initialize standard action to 'ignore' for all conflicts, or leave empty for user to decide
      const initialResolutions: ColumnResolution[] = [];
      
      setState((prev) => ({
        ...prev,
        step: "resolve",
        uploadResult: result,
        resolutions: initialResolutions,
        isLoading: false,
      }));
    } catch (err: any) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: err?.response?.data?.detail || err.message || "Failed to upload sheets",
      }));
    }
  };

  const handleResolveConflicts = async (resolutions: ColumnResolution[], compositeKey: CompositeKey) => {
    if (!state.uploadResult) return;
    
    setState((prev) => ({ ...prev, isLoading: true, error: null, resolutions, compositeKey }));
    try {
      const payload: ConflictResolutionMap = {
        file_ids: state.uploadResult.file_ids,
        resolutions,
        composite_key: compositeKey,
      };
      const result = await mergeSheets(payload);
      setState((prev) => ({
        ...prev,
        step: "enrich",
        mergeResult: result,
        isLoading: false,
      }));
    } catch (err: any) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: err?.response?.data?.detail || err.message || "Failed to merge sheets",
      }));
    }
  };

  const handleEnrich = async (masterTable: string, fetchColumns: string[], outputFormat: "xlsx" | "csv", dbPath: string, mergedFile: File) => {
    if (!state.compositeKey) return;

    setState((prev) => ({ ...prev, isLoading: true, error: null }));
    try {
      const { blob, headers } = await enrichData(
        dbPath,
        fetchColumns[0], // assume single fetch column for now
        state.compositeKey,
        mergedFile
      );

      // Create blob download link
      const url = window.URL.createObjectURL(new Blob([blob]));
      const link = document.createElement("a");
      link.href = url;
      // You can try to parse filename from the Content-Disposition header if available
      link.setAttribute("download", "enriched_data.xlsx");
      document.body.appendChild(link);
      link.click();
      link.parentNode?.removeChild(link);

      const matched = parseInt(headers["x-matched-rows"] || "0", 10);
      const unmatched = parseInt(headers["x-unmatched-rows"] || "0", 10);
      const total = parseInt(headers["x-total-rows"] || "0", 10);

      // Mock EnrichmentResponse for UI
      const mockResult = {
        download_url: "#", // Handled manually above
        total_rows: total,
        matched_rows: matched,
        unmatched_rows: unmatched,
        output_format: outputFormat
      };

      setState((prev) => ({
        ...prev,
        step: "download",
        enrichResult: mockResult,
        isLoading: false,
      }));
    } catch (err: any) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: err?.response?.data?.detail || err.message || "Failed to enrich data",
      }));
    }
  };

  const resetWizard = () => {
    setState({
      step: "upload",
      uploadResult: null,
      resolutions: [],
      compositeKey: null,
      mergeResult: null,
      enrichResult: null,
      isLoading: false,
      error: null,
    });
  };

  return {
    state,
    handleUpload,
    handleResolveConflicts,
    handleEnrich,
    resetWizard,
  };
}
