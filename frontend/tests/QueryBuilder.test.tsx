import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { rest } from "msw";
import { QueryBuilderPage } from "../src/pages/QueryBuilderPage";
import type { TableMetadata } from "../src/types/schema.types";
import { server } from "./testServer";
import { renderWithAppContext } from "./testUtils";

describe("QueryBuilderPage", () => {
  it("selects a table, previews SQL, and renders query results", async () => {
    const previewPayloads: Array<Record<string, unknown>> = [];
    let executePayload: Record<string, unknown> | null = null;

    const tables: TableMetadata[] = [
      {
        table_name: "customers",
        columns: [
          { name: "customer_name", dtype: "VARCHAR", nullable: false },
          { name: "city", dtype: "VARCHAR", nullable: true },
        ],
        row_count: 2,
      },
    ];

    server.use(
      rest.post("*/api/query/preview", async (req, res, ctx) => {
        const body = req.body as Record<string, unknown>;
        previewPayloads.push(body);

        return res(
          ctx.json({
            sql: "SELECT customers.customer_name FROM customers LIMIT 1000",
            source_mode: "builder",
            can_sync_builder: true,
          }),
        );
      }),
      rest.post("*/api/query", async (req, res, ctx) => {
        executePayload = req.body as Record<string, unknown>;

        return res(
          ctx.json({
            columns: ["customer_name"],
            rows: [["Alice"], ["Bob"]],
            total: 2,
            truncated: false,
            executed_sql: "SELECT customers.customer_name FROM customers LIMIT 1000",
            source_mode: "builder",
            message: "Query complete",
          }),
        );
      }),
    );

    const user = userEvent.setup();
    renderWithAppContext(<QueryBuilderPage />, {
      route: "/query/local",
      duckdbConnection: {
        isConnected: true,
        tables,
      },
    });

    await user.click(screen.getByRole("button", { name: /select a table/i }));
    await user.click(screen.getByRole("button", { name: /customers/i }));

    expect(await screen.findByRole("checkbox", { name: /customers\.customer_name/i })).toBeInTheDocument();

    await user.click(screen.getByRole("checkbox", { name: /customers\.customer_name/i }));

    await waitFor(() => {
      expect(screen.getByDisplayValue(/select customers\.customer_name from customers limit 1000/i)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /run builder sql/i })).toBeEnabled();
    });

    await user.click(screen.getByRole("button", { name: /run builder sql/i }));

    expect(await screen.findByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("Bob")).toBeInTheDocument();

    expect(previewPayloads.some((payload) => Array.isArray(payload.select))).toBe(true);
    expect(executePayload?.table).toBe("customers");
    expect(executePayload?.mode).toBe("LIST");
    expect(executePayload?.select).toEqual(["customers.customer_name"]);
  });
});
