import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SkippedFiles } from "../src/components/sidebar/SkippedFiles";

describe("SkippedFiles", () => {
  it("renders nothing when no files were skipped", () => {
    const { container } = render(<SkippedFiles details={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("groups by reason and shows the count", () => {
    render(
      <SkippedFiles
        details={[
          "D:/m/A.csv.gz (ALREADY_EXISTS)",
          "D:/m/B.csv.gz (ALREADY_EXISTS)",
          "D:/m/C.csv.gz (EMPTY_FILE)",
        ]}
      />,
    );

    expect(screen.getByText(/ALREADY_EXISTS/)).toBeInTheDocument();
    expect(screen.getByText(/EMPTY_FILE/)).toBeInTheDocument();
  });

  it("lists the actual file paths when a reason is expanded", async () => {
    const user = userEvent.setup();
    render(
      <SkippedFiles
        details={["D:/m/DVVNL_DIV211321.csv.gz (EMPTY_FILE)", "D:/m/DVVNL_DIV211322.csv.gz (EMPTY_FILE)"]}
      />,
    );

    // Collapsed by default — a count alone is not actionable, but nor is a 600-line list.
    expect(screen.queryByText("D:/m/DVVNL_DIV211321.csv.gz")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /EMPTY_FILE/ }));

    expect(screen.getByText("D:/m/DVVNL_DIV211321.csv.gz")).toBeInTheDocument();
    expect(screen.getByText("D:/m/DVVNL_DIV211322.csv.gz")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /copy 2 path/i })).toBeInTheDocument();
  });

  it("puts real problems above benign skips regardless of count", () => {
    render(
      <SkippedFiles
        details={[
          ...Array.from({ length: 50 }, (_, i) => `D:/m/ok${i}.csv.gz (ALREADY_EXISTS)`),
          "D:/m/bad.csv.gz (MISSING_ACCT_ID_COLUMN)",
        ]}
      />,
    );

    const buttons = screen.getAllByRole("button");
    // A single real fault must not sit below 50 benign entries.
    expect(buttons[0]).toHaveTextContent("MISSING_ACCT_ID_COLUMN");
  });

  it("explains what a reason means", () => {
    render(<SkippedFiles details={["D:/m/A.csv.gz (EMPTY_FILE)"]} />);
    expect(screen.getByText(/zero rows.*no data lost/i)).toBeInTheDocument();
  });
});
