/**
 * useMergeWizard.ts - React hook orchestrating the Merge and Enrichment UI state.
 */

// @ts-nocheck
import { useRef, useState } from "react";
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
    enrichProgress: null,
    downloadBlobUrl: null,
  });

  // AbortController ref for cancelling in-flight enrichment requests
  const enrichAbortRef = useRef<AbortController | null>(null);

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
    // Cancel any previous in-flight request
    enrichAbortRef.current?.abort();
    const abortController = new AbortController();
    enrichAbortRef.current = abortController;

    setState((prev) => ({
      ...prev,
      isLoading: true,
      error: null,
      enrichProgress: "Sending data to server for enrichment...",
    }));

    // Simulate progress updates with a timer
    const startMs = Date.now();
    const progressTimer = window.setInterval(() => {
      const elapsedSec = Math.floor((Date.now() - startMs) / 1000);
      if (elapsedSec < 5) {
        setState((prev) => ({ ...prev, enrichProgress: "Processing uploaded file and running JOIN query..." }));
      } else if (elapsedSec < 15) {
        setState((prev) => ({ ...prev, enrichProgress: `Enriching data... (${elapsedSec}s elapsed)` }));
      } else if (elapsedSec < 60) {
        setState((prev) => ({ ...prev, enrichProgress: `Still processing — large files take a while... (${elapsedSec}s elapsed)` }));
      } else {
        const mins = Math.floor(elapsedSec / 60);
        setState((prev) => ({ ...prev, enrichProgress: `Processing ${mins}m ${elapsedSec % 60}s — please be patient for large datasets...` }));
      }
    }, 2000);

    try {
      const { blob, headers } = await enrichData(
        dbPath,
        masterTable,
        fetchColumns,
        joinKeys,
        outputFormat,
        mergedFile,
        abortController.signal
      );

      window.clearInterval(progressTimer);

      // Create a blob URL so the user can download later via Save-As
      const blobUrl = window.URL.createObjectURL(new Blob([blob]));

      const matched = parseInt(headers["x-matched-rows"] || "0", 10);
      const unmatched = parseInt(headers["x-unmatched-rows"] || "0", 10);
      const total = parseInt(headers["x-total-rows"] || "0", 10);

      const mockResult = {
        download_url: blobUrl,
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
        enrichProgress: null,
        downloadBlobUrl: blobUrl,
      }));
    } catch (err: any) {
      window.clearInterval(progressTimer);

      // If user cancelled, don't treat as error
      if (err?.name === "CanceledError" || err?.code === "ERR_CANCELED" || abortController.signal.aborted) {
        setState((prev) => ({
          ...prev,
          isLoading: false,
          enrichProgress: null,
          error: null,
        }));
        return;
      }

      setState((prev) => ({
        ...prev,
        isLoading: false,
        enrichProgress: null,
        error: getRequestErrorMessage(err, "Failed to enrich data", "enrich"),
      }));
    }
  };

  const cancelEnrich = () => {
    enrichAbortRef.current?.abort();
    enrichAbortRef.current = null;
    setState((prev) => ({
      ...prev,
      isLoading: false,
      enrichProgress: null,
      error: "Enrichment cancelled by user.",
    }));
  };

  const resetWizard = () => {
    // Revoke any existing blob URL to free memory
    if (state.downloadBlobUrl) {
      window.URL.revokeObjectURL(state.downloadBlobUrl);
    }
    enrichAbortRef.current?.abort();
    enrichAbortRef.current = null;
    setState({
      step: "upload",
      uploadResult: null,
      enrichResult: null,
      isLoading: false,
      error: null,
      enrichProgress: null,
      downloadBlobUrl: null,
    });
  };

  return {
    state,
    handleUpload,
    handleEnrich,
    cancelEnrich,
    resetWizard,
  };
}
