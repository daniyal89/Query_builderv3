import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { rest } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { TableList } from "../src/components/home/TableList";
import { clearViewRowCountCache } from "../src/hooks/useViewRowCounts";
import type { TableMetadata } from "../src/types/schema.types";
import { server } from "./testServer";

function table(overrides: Partial<TableMetadata> = {}): TableMetadata {
  return {
    table_name: "Master_0526",
    columns: [
      { name: "ACCT_ID", dtype: "VARCHAR", nullable: true },
      { name: "TOTAL_AMT", dtype: "VARCHAR", nullable: true },
    ],
    row_count: 0,
    object_type: "TABLE",
    ...overrides,
  };
}

/** Digit grouping follows the runtime locale (Indian grouping here), so never
 *  hardcode "46,123,456" — format the expectation the way the UI does. */
function n(value: number): string {
  return value.toLocaleString();
}

function renderList(tables: TableMetadata[]) {
  return render(
    <MemoryRouter>
      <TableList tables={tables} dbPath="C:/db/uppcl.duckdb" />
    </MemoryRouter>,
  );
}

describe("TableList", () => {
  beforeEach(() => {
    clearViewRowCountCache();
  });

  it("shows a materialised month's estimate with a tilde and no extra request", () => {
    renderList([table({ row_count: 250 })]);

    expect(screen.getByText("~250")).toBeInTheDocument();
    expect(screen.getByText("TABLE")).toBeInTheDocument();
  });

  it("counts a view and renders the exact number without a tilde", async () => {
    server.use(
      rest.get("*/api/tables/Master_0526/row-count", (_req, res, ctx) =>
        res(ctx.json({ table_name: "Master_0526", row_count: 46123456 })),
      ),
    );
    renderList([table({ object_type: "VIEW" })]);

    // A view reports 0 rows in the catalog, so it must not read as empty.
    expect(screen.getByText(/counting rows/i)).toBeInTheDocument();

    expect(await screen.findByText(n(46123456))).toBeInTheDocument();
    expect(screen.getByText("VIEW")).toBeInTheDocument();
    expect(screen.queryByText(`~${n(46123456)}`)).not.toBeInTheDocument();
  });

  it("reports a view whose parquet has moved instead of showing a number", async () => {
    server.use(
      rest.get("*/api/tables/Master_0526/row-count", (_req, res, ctx) =>
        res(ctx.status(424), ctx.json({ detail: "'Master_0526' reads its rows from parquet files that could not be opened." })),
      ),
    );
    renderList([table({ object_type: "VIEW" })]);

    expect(await screen.findByText(/source parquet files not found/i)).toBeInTheDocument();
  });

  it("distinguishes a transient failure from unreachable sources", async () => {
    server.use(
      rest.get("*/api/tables/Master_0526/row-count", (_req, res, ctx) =>
        res(ctx.status(500), ctx.json({ detail: "boom" })),
      ),
    );
    renderList([table({ object_type: "VIEW" })]);

    expect(await screen.findByText(/row count unavailable/i)).toBeInTheDocument();
    expect(screen.queryByText(/source parquet files not found/i)).not.toBeInTheDocument();
  });

  it("requests each view's count exactly once", async () => {
    const calls: string[] = [];
    server.use(
      rest.get("*/api/tables/:name/row-count", (req, res, ctx) => {
        const name = String(req.params.name);
        calls.push(name);
        return res(ctx.json({ table_name: name, row_count: 5 }));
      }),
    );

    const { rerender } = renderList([
      table({ table_name: "Master_0426", object_type: "VIEW" }),
      table({ table_name: "Master_0526", object_type: "VIEW" }),
    ]);

    await waitFor(() => expect(calls).toHaveLength(2));

    // A fresh array with identical contents — what refreshTables hands back. If the
    // effect depended on array identity this would refetch forever.
    rerender(
      <MemoryRouter>
        <TableList
          tables={[
            table({ table_name: "Master_0426", object_type: "VIEW" }),
            table({ table_name: "Master_0526", object_type: "VIEW" }),
          ]}
          dbPath="C:/db/uppcl.duckdb"
        />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getAllByText("5")).toHaveLength(2));
    expect(calls).toEqual(["Master_0426", "Master_0526"]);
  });

  it("does not count tables, only views", async () => {
    const calls: string[] = [];
    server.use(
      rest.get("*/api/tables/:name/row-count", (req, res, ctx) => {
        const name = String(req.params.name);
        calls.push(name);
        return res(ctx.json({ table_name: name, row_count: 5 }));
      }),
    );

    renderList([
      table({ table_name: "Master_0426", object_type: "TABLE", row_count: 99 }),
      table({ table_name: "Master_0526", object_type: "VIEW" }),
    ]);

    await waitFor(() => expect(calls).toEqual(["Master_0526"]));
  });

  it("renders the whole month name, not a truncated one", () => {
    // Every month is "Master_MMYY", so a card clipped to "Master_0..." makes the
    // one thing this list exists for — telling the months apart — impossible.
    renderList([
      table({ table_name: "Master_0326", object_type: "TABLE", row_count: 45752482 }),
      table({ table_name: "Master_0426", object_type: "VIEW" }),
    ]);

    expect(screen.getByRole("link", { name: "Master_0326" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Master_0426" })).toBeInTheDocument();
    expect(screen.queryByText(/Master_0\.\.\./)).not.toBeInTheDocument();
  });

  it("keeps names readable next to a wide column-count badge", () => {
    // 164 cols + a kind badge is what squeezed the name out of the shared row.
    renderList([
      table({
        table_name: "Master_0626",
        object_type: "TABLE",
        columns: Array.from({ length: 164 }, (_, i) => ({
          name: `C${i}`,
          dtype: "VARCHAR",
          nullable: true,
        })),
        row_count: 46236650,
      }),
    ]);

    expect(screen.getByRole("link", { name: "Master_0626" })).toBeInTheDocument();
    expect(screen.getByText("164 cols")).toBeInTheDocument();
    expect(screen.getByText("TABLE")).toBeInTheDocument();
  });

  it("omits the badge when the engine does not report a kind", () => {
    renderList([table({ object_type: undefined, row_count: 7 })]);

    expect(screen.queryByText("TABLE")).not.toBeInTheDocument();
    expect(screen.queryByText("VIEW")).not.toBeInTheDocument();
    expect(screen.getByText("~7")).toBeInTheDocument();
  });
});
