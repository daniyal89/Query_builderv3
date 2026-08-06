/**
 * useViewRowCounts.ts — exact row counts for objects that cannot report their own.
 *
 * `GET /api/tables` returns the catalog's row estimate, which is exact for a
 * materialised table and always 0 for a view (counting one means running it). A
 * month stored as a view would therefore read as empty, so its real count is
 * fetched per object afterwards.
 *
 * That same request doubles as the health check: a view whose parquet folder moved
 * still answers from the catalog — columns and all — and only reading through it
 * fails, with a 424 naming the unreachable files. One request answers both
 * "how many rows" and "is this month still readable".
 */
import { useEffect, useState } from "react";
import axios from "axios";
import { getRowCount } from "../api/schemaApi";
import type { TableMetadata } from "../types/schema.types";

export type ViewRowCount =
  | { status: "loading" }
  /** Exact, not an estimate — render it without the "~". */
  | { status: "ready"; rows: number }
  /** 424: the object is fine, its files are not. Actionable, so do not retry. */
  | { status: "unavailable"; detail: string }
  /** Network or server fault. Transient, but retrying costs a directory walk. */
  | { status: "error"; detail: string };

/**
 * Counts survive navigating away and back. Keyed by database path as well as
 * name, so connecting to a different file cannot show the previous one's numbers.
 */
const cache = new Map<string, ViewRowCount>();

function cacheKey(dbPath: string, tableName: string): string {
  return `${dbPath}::${tableName}`;
}

export function useViewRowCounts(
  tables: TableMetadata[],
  dbPath: string | null | undefined,
): Record<string, ViewRowCount> {
  const [counts, setCounts] = useState<Record<string, ViewRowCount>>({});

  const viewNames = tables
    .filter((table) => table.object_type === "VIEW")
    .map((table) => table.table_name)
    .sort();
  // Depend on a stable string, never the array: `refreshTables` hands back a new
  // array every call, so depending on its identity is an infinite refetch loop.
  const key = viewNames.join("|");
  const scope = dbPath ?? "";

  useEffect(() => {
    if (!key) {
      setCounts({});
      return;
    }
    const names = key.split("|");
    const controller = new AbortController();
    let cancelled = false;

    const seeded: Record<string, ViewRowCount> = {};
    for (const name of names) {
      seeded[name] = cache.get(cacheKey(scope, name)) ?? { status: "loading" };
    }
    setCounts(seeded);

    void (async () => {
      // Sequential on purpose: each count binds the same parquet tree, so running
      // them together thrashes one disk instead of finishing the first one sooner.
      for (const name of names) {
        if (cancelled) return;
        if (cache.has(cacheKey(scope, name))) continue;

        let result: ViewRowCount;
        try {
          const { row_count } = await getRowCount(name, controller.signal);
          result = { status: "ready", rows: row_count };
        } catch (error) {
          if (axios.isCancel(error) || cancelled) return;
          const status = axios.isAxiosError(error) ? error.response?.status : undefined;
          const detail =
            (axios.isAxiosError(error)
              ? (error.response?.data as { detail?: string } | undefined)?.detail
              : undefined) ?? "The row count could not be read.";
          result =
            status === 424
              ? { status: "unavailable", detail }
              : { status: "error", detail };
        }

        // Only cache settled answers: a transient failure must not be remembered
        // as this month's permanent state.
        if (result.status !== "error") {
          cache.set(cacheKey(scope, name), result);
        }
        if (cancelled) return;
        setCounts((previous) => ({ ...previous, [name]: result }));
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [key, scope]);

  return counts;
}

/** Test seam: drops the memoised counts. */
export function clearViewRowCountCache(): void {
  cache.clear();
}
