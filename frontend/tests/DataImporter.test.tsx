import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { rest } from "msw";
import FolderMergePage from "../src/pages/FolderMergePage";
import { server } from "./testServer";
import { renderWithAppContext } from "./testUtils";

describe("FolderMergePage", () => {
  it("submits a merge request and shows the returned summary", async () => {
    let mergePayload: Record<string, unknown> | null = null;

    server.use(
      rest.post("*/api/merge-folder", async (req, res, ctx) => {
        mergePayload = req.body as Record<string, unknown>;

        return res(
          ctx.json({
            output_path: "D:\\Output\\merged_output.csv",
            output_format: "csv",
            total_files: 4,
            merged_items: 4,
            total_rows: 120,
            total_columns: 18,
          }),
        );
      }),
    );

    const user = userEvent.setup();
    renderWithAppContext(<FolderMergePage />, { route: "/folder-merge" });

    const textboxes = screen.getAllByRole("textbox");
    await user.type(textboxes[0], "D:\\Input\\Monthly");
    await user.type(textboxes[1], "D:\\Output\\merged_output.csv");
    await user.click(screen.getByRole("button", { name: /start merge/i }));

    expect(await screen.findByText(/merged file saved successfully/i)).toBeInTheDocument();
    expect(screen.getByText("120")).toBeInTheDocument();
    expect(screen.getByText("18")).toBeInTheDocument();
    expect(screen.getByText("D:\\Output\\merged_output.csv")).toBeInTheDocument();

    expect(mergePayload).toEqual({
      source_folder: "D:\\Input\\Monthly",
      output_path: "D:\\Output\\merged_output.csv",
      include_subfolders: true,
    });
  });

  it("shows the returned API error when the merge fails", async () => {
    server.use(
      rest.post("*/api/merge-folder", (_req, res, ctx) =>
        res(ctx.status(400), ctx.json({ detail: "No supported files were found." })),
      ),
    );

    const user = userEvent.setup();
    renderWithAppContext(<FolderMergePage />, { route: "/folder-merge" });

    const textboxes = screen.getAllByRole("textbox");
    await user.type(textboxes[0], "D:\\Input\\Empty");
    await user.type(textboxes[1], "D:\\Output\\merged_output.csv");
    await user.click(screen.getByRole("button", { name: /start merge/i }));

    expect(await screen.findByText(/no supported files were found\./i)).toBeInTheDocument();
  });
});
