/**
 * App.tsx — Top-level route definitions.
 */

import { Navigate, Route, Routes } from "react-router-dom";
import PageShell from "./components/layout/PageShell";
import FolderMergePage from "./pages/FolderMergePage";
import { MergeEnrichPage } from "./pages/MergeEnrichPage";
import { HomePage } from "./pages/HomePage";
import { FtpDownloadPage } from "./pages/FtpDownloadPage";
import { UploadMasterDrivePage } from "./pages/UploadMasterDrivePage";
import { DriveDownloadPage } from "./pages/DriveDownloadPage";
import { MarcadoseQueryBuilderPage } from "./pages/MarcadoseQueryBuilderPage";
import { QueryBuilderPage } from "./pages/QueryBuilderPage";

function App() {
  return (
    <PageShell>
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
      </Routes>
    </PageShell>
  );
}

export default App;
