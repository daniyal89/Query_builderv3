/**
 * useMergeWizard.ts - React hook orchestrating the Merge and Enrichment UI state.
 */

// @ts-nocheck
import { useState } from "react";
import { enrichData, uploadSheets } from "../api/mergeApi";
import type {
  JoinKeyMapping,
  MergeWizardState,
} from "../types/merge.types";

function getRequestErrorMessage(err: any, fallback: string, operation: "upload" | "merge" | "enrich"): string {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }

  const message = typeof err?.message === "string" ? err.message : "";
  const isTimeout = err?.code === "ECONNABORTED" || /timeout/i.test(message);
  if (isTimeout) {
    if (operation === "enrich") {
      return "Enrichment is taking longer than expected. Large files and Excel output can take a few minutes, so please retry and wait for the export to finish.";
    }
    if (operation === "upload") {
      return "Upload analysis is taking longer than expected. Please retry and give the file more time to process.";
    }
    return "This request is taking longer than expected. Please retry and allow more time for processing.";
  }

  return message || fallback;
}

export function useMergeWizard() {
  const [state, setState] = useState<MergeWizardState>({
    step: "upload",
    uploadResult: null,
    enrichResult: null,
    isLoading: false,
    error: null,
  });

  const handleUpload = async (files: File[]) => {
    setState((prev) => ({ ...prev, isLoading: true, error: null }));
    try {
      const result = await uploadSheets(files);
      setState((prev) => ({
        ...prev,
        step: "enrich",
        uploadResult: result,
        isLoading: false,
        uploadedFile: files[0],
      }));
    } catch (err: any) {
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: getRequestErrorMessage(err, "Failed to upload sheets", "upload"),
      }));
    }
  };



  const handleEnrich = async (
    masterTable: string,
    fetchColumns: string[],
    outputFormat: "xlsx" | "csv",
    dbPath: string,
    mergedFile: File,
    joinKeys: JoinKeyMapping[]
  ) => {
    setState((prev) => ({ ...prev, isLoading: true, error: null }));
    try {
      const { blob, headers } = await enrichData(
        dbPath,
        masterTable,
        fetchColumns,
        joinKeys,
        mergedFile
      );

      const url = window.URL.createObjectURL(new Blob([blob]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", "enriched_data.xlsx");
      document.body.appendChild(link);
      link.click();
      link.parentNode?.removeChild(link);

      const matched = parseInt(headers["x-matched-rows"] || "0", 10);
      const unmatched = parseInt(headers["x-unmatched-rows"] || "0", 10);
      const total = parseInt(headers["x-total-rows"] || "0", 10);

      const mockResult = {
        download_url: "#",
        total_rows: total,
        matched_rows: matched,
        unmatched_rows: unmatched,
        output_format: outputFormat,
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
        error: getRequestErrorMessage(err, "Failed to enrich data", "enrich"),
      }));
    }
  };

  const resetWizard = () => {
    setState({
      step: "upload",
      uploadResult: null,
      enrichResult: null,
      isLoading: false,
      error: null,
    });
  };

  return {
    state,
    handleUpload,
    handleEnrich,
    resetWizard,
  };
}
