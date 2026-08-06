import { render, screen } from "@testing-library/react";
import { ResultsGrid } from "../src/components/query/ResultsGrid";
import type { QueryResult } from "../src/types/query.types";

function buildResult(rowCount: number): QueryResult {
  return {
    columns: ["customer_name"],
    rows: Array.from({ length: rowCount }, (_, index) => [`Customer ${index}`]),
    total: rowCount,
    truncated: false,
    executed_sql: "SELECT customer_name FROM customers",
    source_mode: "builder",
    message: "Query complete",
  };
}

describe("ResultsGrid", () => {
  it("caps the rendered rows and tells the user CSV still exports everything", () => {
    render(<ResultsGrid result={buildResult(300)} isLoading={false} />);

    // Only the first 50 rows reach the DOM.
    expect(screen.getByText("Customer 0")).toBeInTheDocument();
    expect(screen.getByText("Customer 49")).toBeInTheDocument();
    expect(screen.queryByText("Customer 50")).not.toBeInTheDocument();
    expect(screen.queryByText("Customer 150")).not.toBeInTheDocument();

    expect(screen.getByText(/showing 50 of 300 rows/i)).toBeInTheDocument();
    expect(screen.getByText(/csv will export all 300 rows/i)).toBeInTheDocument();
  });

  it("renders every row when the result is below the display cap", () => {
    render(<ResultsGrid result={buildResult(3)} isLoading={false} />);

    expect(screen.getByText("Customer 0")).toBeInTheDocument();
    expect(screen.getByText("Customer 2")).toBeInTheDocument();
    expect(screen.getByText(/showing 3 of 3 rows/i)).toBeInTheDocument();
    expect(screen.queryByText(/csv will export all/i)).not.toBeInTheDocument();
  });
});
