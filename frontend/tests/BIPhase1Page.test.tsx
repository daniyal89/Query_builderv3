import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { rest } from "msw";
import { BIPhase1Page } from "../src/pages/BIPhase1Page";
import { server } from "./testServer";
import { renderWithAppContext } from "./testUtils";
import type { BIPhase1State } from "../src/types/biPhase1.types";

function createEmptyState(): BIPhase1State {
  return {
    workspaces: [],
    data_sources: [],
    datasets: [],
    tables: [],
    fields: [],
    metrics: [],
    charts: [],
    dashboards: [],
    source_insights: [],
    audits: [],
  };
}

describe("BIPhase1Page", () => {
  it("creates a workspace and registers a source", async () => {
    const state = createEmptyState();

    server.use(
      rest.get("*/api/bi-phase1/state", (_req, res, ctx) => res(ctx.json(state))),
      rest.post("*/api/bi-phase1/workspaces", async (req, res, ctx) => {
        const body = req.body as { name: string; description: string };
        const workspace = {
          id: "ws_1",
          name: body.name,
          description: body.description,
        };
        state.workspaces = [workspace];
        state.audits = [
          {
            at: new Date("2026-05-08T10:59:41Z").toISOString(),
            actor: "bi-phase1-ui",
            action: "workspace.create",
            target: "ws_1",
          },
        ];
        return res(ctx.status(201), ctx.json(workspace));
      }),
      rest.post("*/api/bi-phase1/data-sources", async (req, res, ctx) => {
        const body = req.body as {
          workspace_id: string;
          name: string;
          location: string;
          source_type: string;
        };
        const source = {
          id: "src_1",
          workspace_id: body.workspace_id,
          name: body.name,
          location: body.location,
          source_type: "csv" as const,
          status: "active" as const,
        };
        state.data_sources = [source];
        state.source_insights = [
          {
            source_id: "src_1",
            detected_type: "csv",
            capabilities: {
              preview: true,
              schema_inference: true,
              incremental: true,
            },
            schema: [
              { name: "region", type: "VARCHAR" },
              { name: "amount", type: "BIGINT" },
            ],
            preview_rows: [{ region: "North", amount: 25 }],
            status: "active",
            last_sync: new Date("2026-05-08T11:00:00Z").toISOString(),
            load_strategy: "create or replace view phase1_source as select * from read_csv_auto('sales.csv')",
          },
        ];
        state.audits = [
          ...state.audits,
          {
            at: new Date("2026-05-08T11:00:00Z").toISOString(),
            actor: "bi-phase1-ui",
            action: "source.register",
            target: "src_1",
          },
        ];
        return res(ctx.status(201), ctx.json(source));
      }),
    );

    const user = userEvent.setup();
    renderWithAppContext(<BIPhase1Page />, {
      duckdbConnection: {
        dbPath: "D:\\Data\\sales.csv",
        isConnected: false,
      },
    });

    expect(await screen.findByText(/bi workspace builder/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /create workspace/i }));

    expect(await screen.findByText(/workspace created\./i)).toBeInTheDocument();
    expect(screen.getAllByText("BI Phase 1 Workspace").length).toBeGreaterThan(0);

    await waitFor(() => {
      expect(screen.getAllByRole("option", { name: /bi phase 1 workspace/i }).length).toBeGreaterThan(0);
    });

    await user.clear(screen.getByLabelText(/^Source name$/i));
    await user.type(screen.getByLabelText(/^Source name$/i), "Sales CSV");
    await user.clear(screen.getByLabelText(/File path/i));
    await user.type(screen.getByLabelText(/File path/i), "D:\\Data\\sales.csv");
    await user.click(screen.getByRole("button", { name: /register source/i }));

    expect(await screen.findByText(/source registered and previewed\./i)).toBeInTheDocument();
    expect(screen.getAllByText("Sales CSV").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/sample rows/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText("amount").length).toBeGreaterThan(0);
  });
});
