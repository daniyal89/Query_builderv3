/**
 * App.tsx — Top-level route definitions.
 *
 * Maps:
 *   /        → HomePage
 *   /query   → QueryBuilderPage
 *   /import  → DataImporterPage
 *
 * All routes are wrapped in the PageShell layout component.
 */

import { Routes, Route } from "react-router-dom";
import PageShell from "./components/layout/PageShell";
import { HomePage } from "./pages/HomePage";
import { QueryBuilderPage } from "./pages/QueryBuilderPage";
import { DataImporterPage } from "./pages/DataImporterPage";

function App() {
  return (
    <PageShell>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/query" element={<QueryBuilderPage />} />
        <Route path="/import" element={<DataImporterPage />} />
      </Routes>
    </PageShell>
  );
}

export default App;
