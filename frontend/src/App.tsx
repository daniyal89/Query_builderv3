/**
 * App.tsx - Top-level route definitions with lazy page loading.
 */

import { Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import {
  DriveDownloadPage,
  FolderMergePage,
  FtpDownloadPage,
  HomePage,
  MarcadoseQueryBuilderPage,
  MergeEnrichPage,
  QueryBuilderPage,
  SidebarToolsPage,
  UploadMasterDrivePage,
} from "./app/lazyPages";
import PageShell from "./components/layout/PageShell";

function PageLoadingFallback() {
  return (
    <div className="flex min-h-[260px] items-center justify-center rounded-xl border border-slate-200 bg-white transition-colors dark:border-slate-800 dark:bg-slate-900">
      <div className="text-center">
        <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-b-2 border-indigo-600" />
        <p className="text-sm font-medium text-slate-700 dark:text-slate-200">Loading page...</p>
      </div>
    </div>
  );
}

function App() {
  return (
    <PageShell>
      <Suspense fallback={<PageLoadingFallback />}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/query" element={<Navigate to="/query/local" replace />} />
          <Route path="/query/local" element={<QueryBuilderPage />} />
          <Route path="/query/marcadose" element={<MarcadoseQueryBuilderPage />} />
          <Route path="/import" element={<MergeEnrichPage />} />
          <Route path="/folder-merge" element={<FolderMergePage />} />
          <Route path="/ftp-download" element={<FtpDownloadPage />} />
          <Route path="/drive-upload-master" element={<UploadMasterDrivePage />} />
          <Route path="/drive-download" element={<DriveDownloadPage />} />
          <Route path="/sidebar-6-tools" element={<SidebarToolsPage />} />
        </Routes>
      </Suspense>
    </PageShell>
  );
}

export default App;
