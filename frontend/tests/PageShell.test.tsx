import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PageShell from "../src/components/layout/PageShell";
import { renderWithAppContext } from "./testUtils";

describe("PageShell", () => {
  it("toggles dark mode and persists the selected theme", async () => {
    const user = userEvent.setup();

    renderWithAppContext(
      <PageShell>
        <div>Workspace content</div>
      </PageShell>,
    );

    const toggle = screen.getByRole("button", { name: /switch to dark mode/i });
    expect(document.documentElement.classList.contains("dark")).toBe(false);

    await user.click(toggle);

    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(window.localStorage.getItem("qb:theme:v1")).toBe("dark");
    expect(screen.getByRole("button", { name: /switch to light mode/i })).toBeInTheDocument();
  });
});
