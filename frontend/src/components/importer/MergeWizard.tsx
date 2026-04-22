import React from "react";
import { useMergeWizard } from "../../hooks/useMergeWizard";
import { ConflictResolver } from "./ConflictResolver";
import { EnrichmentConfig } from "./EnrichmentConfig";
import { MultiFileDropZone } from "./MultiFileDropZone";

export const MergeWizard: React.FC = () => {
  const { state, handleUpload, handleResolveConflicts, handleEnrich, resetWizard } = useMergeWizard();

  return (
    <div className="merge-wizard mx-auto w-full max-w-5xl p-4">
      <h2 className="mb-2 text-2xl font-bold">Merge & Enrichment Pipeline</h2>
      <p className="mb-6 font-medium text-gray-600">
        Reconcile multiple datasets and enrich with the Master Table.
      </p>

      {state.error && (
        <div className="relative mb-6 rounded border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <strong className="mb-1 block font-semibold">Error:</strong>
          {state.error}
          <button
            title="Reset"
            className="absolute right-2 top-2 rounded-full border border-red-200 bg-white px-2 text-2xl font-bold leading-none text-red-500 hover:text-red-700"
            onClick={resetWizard}
          >
            x
          </button>
        </div>
      )}

      {state.step === "upload" && (
        <MultiFileDropZone onUpload={handleUpload} isLoading={state.isLoading} />
      )}

      {state.step === "resolve" && state.uploadResult && (
        <ConflictResolver
          uploadResult={state.uploadResult}
          onSubmit={handleResolveConflicts}
          isLoading={state.isLoading}
        />
      )}

      {state.step === "enrich" && state.uploadResult && (
        <EnrichmentConfig
          uploadResult={state.uploadResult}
          uploadedFile={state.uploadedFile}
          onSubmit={handleEnrich}
          isLoading={state.isLoading}
        />
      )}

      {state.step === "download" && state.enrichResult && (
        <div className="rounded-lg border-2 border-indigo-200 bg-indigo-50 p-8 text-center shadow-lg transition hover:scale-[1.01]">
          <div className="mb-4 text-4xl text-indigo-600">Done</div>
          <h3 className="mb-2 text-xl font-bold text-indigo-900">Data Enriched Successfully!</h3>
          <p className="mb-6 text-indigo-800">
            Total records processed: <strong>{state.enrichResult.total_rows}</strong>
            <br />
            Matches found: {state.enrichResult.matched_rows} | Unmatched: {state.enrichResult.unmatched_rows}
          </p>
          <a
            href={state.enrichResult.download_url}
            className="relative inline-block rounded-full bg-indigo-600 px-8 py-3 text-lg text-white shadow-md transition hover:bg-indigo-700"
            download
            onClick={() => setTimeout(() => resetWizard(), 3000)}
          >
            Download Export
          </a>
        </div>
      )}
    </div>
  );
};
