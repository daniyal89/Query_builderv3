import React from "react";
import { useMergeWizard } from "../../hooks/useMergeWizard";
import { EnrichmentConfig } from "./EnrichmentConfig";
import { MultiFileDropZone } from "./MultiFileDropZone";

export const MergeWizard: React.FC = () => {
  const { state, handleUpload, handleEnrich, resetWizard } = useMergeWizard();

  const handleDownload = async (e: React.MouseEvent<HTMLAnchorElement>) => {
    e.preventDefault();
    if (!state.enrichResult) return;

    try {
      if ("showSaveFilePicker" in window) {
        const response = await fetch(state.enrichResult.download_url);
        const blob = await response.blob();
        // @ts-expect-error showSaveFilePicker is not typed in libdom for all targets
        const handle = await window.showSaveFilePicker({
          suggestedName: "enriched_data.xlsx",
          types: [{ description: "Excel File", accept: { "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"] } }]
        });
        const writable = await handle.createWritable();
        await writable.write(blob);
        await writable.close();
        setTimeout(() => resetWizard(), 1000);
        return;
      }
    } catch (err: any) {
      if (err.name !== "AbortError") console.error(err);
      if (err.name === "AbortError") return;
    }

    // Fallback
    const a = document.createElement("a");
    a.href = state.enrichResult.download_url;
    a.download = "enriched_data.xlsx";
    a.click();
    setTimeout(() => resetWizard(), 3000);
  };

  const steps = [
    { key: "upload", label: "Upload" },
    { key: "enrich", label: "Enrich" },
    { key: "download", label: "Download" },
  ] as const;
  const activeIdx = steps.findIndex((s) => s.key === state.step);

  return (
    <div className="merge-wizard mx-auto w-full max-w-5xl p-4">
      <h2 className="mb-2 text-2xl font-bold">Merge & Enrichment Pipeline</h2>
      <p className="mb-4 font-medium text-gray-600">
        Reconcile multiple datasets and enrich with the Master Table.
      </p>

      {/* Step indicator */}
      <div className="mb-6 flex items-center gap-1">
        {steps.map((s, i) => (
          <React.Fragment key={s.key}>
            <div className="flex items-center gap-2">
              <span
                className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold ${
                  i < activeIdx
                    ? "bg-emerald-600 text-white"
                    : i === activeIdx
                      ? "bg-blue-600 text-white"
                      : "bg-slate-200 text-slate-500"
                }`}
              >
                {i < activeIdx ? "✓" : i + 1}
              </span>
              <span
                className={`text-sm font-medium ${
                  i === activeIdx ? "text-blue-700" : i < activeIdx ? "text-emerald-700" : "text-slate-400"
                }`}
              >
                {s.label}
              </span>
            </div>
            {i < steps.length - 1 && (
              <div
                className={`mx-1 h-0.5 flex-1 ${i < activeIdx ? "bg-emerald-400" : "bg-slate-200"}`}
              />
            )}
          </React.Fragment>
        ))}
      </div>

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
            className="relative inline-block rounded-full bg-indigo-600 px-8 py-3 text-lg text-white shadow-md transition hover:bg-indigo-700 cursor-pointer"
            onClick={handleDownload}
          >
            Download Export
          </a>
        </div>
      )}
    </div>
  );
};
