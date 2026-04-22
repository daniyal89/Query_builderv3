/**
 * DataImporterPage.tsx — CSV upload and multi-sheet import wizard page.
 */

import React from "react";
import { MergeWizard } from "../components/importer/MergeWizard";

export const DataImporterPage: React.FC = () => {
  return (
    <div className="w-full h-full bg-slate-50 py-8">
      <MergeWizard />
    </div>
  );
};
