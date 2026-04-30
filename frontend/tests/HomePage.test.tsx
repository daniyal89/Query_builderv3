import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { rest } from "msw";
import { HomePage } from "../src/pages/HomePage";
import { server } from "./testServer";
import { renderWithAppContext } from "./testUtils";

describe("HomePage", () => {
  it("connects to DuckDB and renders the returned tables", async () => {
    let receivedPath = "";

    server.use(
      rest.post("*/api/duckdb/connect", async (req, res, ctx) => {
        const body = req.body as { db_path: string };
        receivedPath = body.db_path;

        return res(
          ctx.json({
            status: "connected",
            db_path: body.db_path,
            tables_count: 1,
            message: "Connected",
          }),
        );
      }),
      rest.get("*/api/tables", (_req, res, ctx) =>
        res(
          ctx.json([
            {
              table_name: "customer_master",
              columns: [
                { name: "ACCT_ID", dtype: "VARCHAR", nullable: false },
                { name: "NAME", dtype: "VARCHAR", nullable: true },
              ],
              row_count: 250,
            },
          ]),
        ),
      ),
    );

    const user = userEvent.setup();
    renderWithAppContext(<HomePage />);

    await user.type(
      screen.getByPlaceholderText(/database\.duckdb/i),
      "D:\\Data\\monthly.duckdb",
    );
    await user.click(screen.getByRole("button", { name: /^connect$/i }));

    expect(await screen.findByText(/available tables \(1\)/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "customer_master" })).toBeInTheDocument();
    expect(screen.getByText(/250/)).toBeInTheDocument();
    expect(receivedPath).toBe("D:\\Data\\monthly.duckdb");
  });

  it("shows the backend error when the connection fails", async () => {
    server.use(
      rest.post("*/api/duckdb/connect", (_req, res, ctx) =>
        res(ctx.status(400), ctx.json({ detail: "DuckDB file was not found." })),
      ),
    );

    const user = userEvent.setup();
    renderWithAppContext(<HomePage />);

    await user.type(
      screen.getByPlaceholderText(/database\.duckdb/i),
      "D:\\Missing\\broken.duckdb",
    );
    await user.click(screen.getByRole("button", { name: /^connect$/i }));

    await waitFor(() => {
      expect(screen.getByText(/connection failed:/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/duckdb file was not found\./i)).toBeInTheDocument();
  });
});
