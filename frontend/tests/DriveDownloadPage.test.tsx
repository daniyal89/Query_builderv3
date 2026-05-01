import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { rest } from "msw";
import { DriveDownloadPage } from "../src/pages/DriveDownloadPage";
import { server } from "./testServer";
import { renderWithAppContext } from "./testUtils";

describe("DriveDownloadPage", () => {
  it("signs out of Google Drive and refreshes the auth card", async () => {
    let logoutCount = 0;

    server.use(
      rest.get("*/api/drive/auth/status", (_req, res, ctx) =>
        res(
          ctx.json({
            configured: true,
            token_exists: true,
            token_valid: true,
            message: "Google login is ready.",
          }),
        ),
      ),
      rest.post("*/api/drive/auth/logout", (_req, res, ctx) => {
        logoutCount += 1;
        return res(
          ctx.json({
            configured: true,
            token_exists: false,
            token_valid: false,
            message: "Signed out from Google Drive and cleared the cached login token.",
          }),
        );
      }),
    );

    const user = userEvent.setup();
    renderWithAppContext(<DriveDownloadPage />, { route: "/drive-download" });

    expect(await screen.findByText(/google login is ready\./i)).toBeInTheDocument();

    await user.click(await screen.findByRole("button", { name: /sign out/i }));

    expect(await screen.findByText(/signed out from google drive and cleared the cached login token\./i)).toBeInTheDocument();
    expect(logoutCount).toBe(1);
    expect(screen.queryByRole("button", { name: /sign out/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in with google/i })).toBeInTheDocument();
  });
});
