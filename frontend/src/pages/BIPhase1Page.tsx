import { useMemo } from "react";

const steps = [
  "1.1 Product and Architecture Baseline",
  "1.2 Connector Framework",
  "1.3 Initial Connectors",
  "1.4 Semantic Model v1",
  "1.5 Visualization Builder v1",
  "1.6 Dashboard Builder v1",
  "1.7 MVP Delivery Hardening",
];

export function BIPhase1Page() {
  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);

  return (
    <section className="space-y-6">
      <header className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600 dark:text-indigo-400">New</p>
        <h1 className="mt-1 text-2xl font-bold text-slate-900 dark:text-slate-100">BI Phase 1 Workspace</h1>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
          Frontend entry point for the new Phase 1 implementation. Use this page as the sub-header navigation target
          to access connector + semantic + dashboard baseline workflows.
        </p>
        <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">Last loaded: {today}</p>
      </header>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {steps.map((step) => (
          <article
            key={step}
            className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:shadow-md dark:border-slate-800 dark:bg-slate-900"
          >
            <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-100">{step}</h2>
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
              Implemented baseline is available in backend services/models; API integration can now be incrementally
              enabled per module.
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}
