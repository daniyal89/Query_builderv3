/**
 * App.tsx â€” Top-level route definitions.
 */

import { Navigate, Route, Routes } from "react-router-dom";
import PageShell from "./components/layout/PageShell";
import { DataImporterPage } from "./pages/DataImporterPage";
import { HomePage } from "./pages/HomePage";
import { FtpDownloadPage } from "./pages/FtpDownloadPage";
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
        <Route path="/import" element={<DataImporterPage />} />
        <Route path="/ftp-download" element={<FtpDownloadPage />} />
      </Routes>
    </PageShell>
  );
}

export default App;
