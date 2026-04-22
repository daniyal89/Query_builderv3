import React from "react";
import { useMergeWizard } from "../../hooks/useMergeWizard";
import { MultiFileDropZone } from "./MultiFileDropZone";
import { ConflictResolver } from "./ConflictResolver";
import { EnrichmentConfig } from "./EnrichmentConfig";

export const MergeWizard: React.FC = () => {
  const { state, handleUpload, handleResolveConflicts, handleEnrich, resetWizard } = useMergeWizard();

  return (
    <div className="merge-wizard w-full max-w-5xl mx-auto p-4">
      <h2 className="text-2xl font-bold mb-2">Merge & Enrichment Pipeline</h2>
      <p className="text-gray-600 mb-6 font-medium">Reconcile multiple datasets and enrich with the Master Table.</p>
      
      {state.error && (
        <div className="mb-6 p-4 bg-red-50 text-red-800 border border-red-200 rounded text-sm relative">
          <strong className="font-semibold block mb-1">Error:</strong>
          {state.error}
          <button 
            title="Reset"
            className="absolute top-2 right-2 text-2xl leading-none text-red-500 hover:text-red-700 font-bold px-2 rounded-full border border-red-200 bg-white"
            onClick={resetWizard}
          >
             ↺
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

      {state.step === "enrich" && state.mergeResult && (
        <EnrichmentConfig 
          mergeResult={state.mergeResult} 
          onSubmit={handleEnrich} 
          isLoading={state.isLoading} 
        />
      )}

      {state.step === "download" && state.enrichResult && (
        <div className="p-8 border-2 border-indigo-200 bg-indigo-50 rounded-lg text-center shadow-lg transform transition hover:scale-[1.01]">
          <div className="text-4xl mb-4 text-indigo-600 animate-bounce">🎉</div>
          <h3 className="text-xl font-bold text-indigo-900 mb-2">Data Enriched Successfully!</h3>
          <p className="text-indigo-800 mb-6">
            Total records processed: <strong>{state.enrichResult.total_rows}</strong><br />
            Matches found: {state.enrichResult.matched_rows} | Unmatched: {state.enrichResult.unmatched_rows}
          </p>
          <a
            href={state.enrichResult.download_url}
            className="inline-block bg-indigo-600 text-white px-8 py-3 rounded-full text-lg shadow-md hover:bg-indigo-700 transition relative"
            download
            onClick={() => setTimeout(() => resetWizard(), 3000)}
          >
            ⏬ Download Export
          </a>
        </div>
      )}
    </div>
  );
};
