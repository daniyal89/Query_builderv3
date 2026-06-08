import React, { useState } from "react";
import { useMergeWizard } from "../../hooks/useMergeWizard";
import { EnrichmentConfig } from "./EnrichmentConfig";
import { MultiFileDropZone } from "./MultiFileDropZone";

export const MergeWizard: React.FC = () => {
  const { state, handleUpload, handleEnrich, cancelEnrich, resetWizard } = useMergeWizard();
  const [saveFileName, setSaveFileName] = useState("enriched_data.xlsx");
  const [downloadStatus, setDownloadStatus] = useState<string | null>(null);

  /** Save using the native file picker (Save As dialog) */
  const handleSaveAs = async () => {
    if (!state.downloadBlobUrl) return;

    try {
      if ("showSaveFilePicker" in window) {
        const response = await fetch(state.downloadBlobUrl);
        const blob = await response.blob();
        // @ts-expect-error showSaveFilePicker is not typed in libdom for all targets
        const handle = await window.showSaveFilePicker({
          suggestedName: saveFileName || "enriched_data.xlsx",
          types: [
            {
              description: "Excel File",
              accept: { "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"] },
            },
          ],
        });
        const writable = await handle.createWritable();
        await writable.write(blob);
        await writable.close();
        setDownloadStatus("File saved successfully!");
        return;
      }
    } catch (err: any) {
      if (err.name === "AbortError") return; // User cancelled dialog
      console.error(err);
    }

    // Fallback: auto-download with custom filename
    handleQuickDownload();
  };

  /** Quick download with the current filename (no Save As dialog) */
  const handleQuickDownload = () => {
    if (!state.downloadBlobUrl) return;
    const a = document.createElement("a");
    a.href = state.downloadBlobUrl;
    a.download = saveFileName || "enriched_data.xlsx";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setDownloadStatus("Download started!");
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
          onCancel={cancelEnrich}
          isLoading={state.isLoading}
          enrichProgress={state.enrichProgress}
        />
      )}

      {state.step === "download" && state.enrichResult && (
        <div className="rounded-lg border-2 border-indigo-200 bg-indigo-50 p-8 shadow-lg">
          <div className="mb-4 text-center text-4xl text-indigo-600">Done</div>
          <h3 className="mb-2 text-center text-xl font-bold text-indigo-900">Data Enriched Successfully!</h3>
          <p className="mb-6 text-center text-indigo-800">
            Total records processed: <strong>{state.enrichResult.total_rows}</strong>
            <br />
            Matches found: {state.enrichResult.matched_rows} | Unmatched: {state.enrichResult.unmatched_rows}
          </p>

          {/* Custom filename input */}
          <div className="mx-auto mb-4 max-w-md">
            <label className="mb-1 block text-sm font-medium text-indigo-800">File Name</label>
            <input
              type="text"
              value={saveFileName}
              onChange={(e) => setSaveFileName(e.target.value)}
              className="w-full rounded border border-indigo-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              placeholder="enriched_data.xlsx"
            />
          </div>

          {/* Download action buttons */}
          <div className="flex flex-col items-center gap-3">
            <div className="flex gap-3">
              <button
                type="button"
                onClick={handleSaveAs}
                className="rounded-full bg-indigo-600 px-8 py-3 text-lg font-semibold text-white shadow-md transition hover:bg-indigo-700"
              >
                Save As...
              </button>
              <button
                type="button"
                onClick={handleQuickDownload}
                className="rounded-full border-2 border-indigo-600 bg-white px-8 py-3 text-lg font-semibold text-indigo-600 shadow-md transition hover:bg-indigo-50"
              >
                Quick Download
              </button>
            </div>
            <p className="text-xs text-indigo-600">
              "Save As" lets you choose where to save. "Quick Download" saves to your default download folder.
            </p>

            {downloadStatus && (
              <div className="mt-2 rounded border border-green-200 bg-green-50 px-4 py-2 text-sm font-medium text-green-700">
                ✓ {downloadStatus}
              </div>
            )}

            <button
              type="button"
              onClick={resetWizard}
              className="mt-4 rounded border border-gray-300 bg-white px-6 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50"
            >
              Start New Enrichment
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
