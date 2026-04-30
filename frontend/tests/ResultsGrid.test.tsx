import { fireEvent, render, screen } from "@testing-library/react";
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
  it("window-renders large result sets and swaps visible rows while scrolling", () => {
    render(<ResultsGrid result={buildResult(300)} isLoading={false} />);

    expect(screen.getByText("Customer 0")).toBeInTheDocument();
    expect(screen.queryByText("Customer 150")).not.toBeInTheDocument();
    expect(screen.getByText(/windowed rendering/i)).toBeInTheDocument();

    fireEvent.scroll(screen.getByTestId("results-grid-scroll"), {
      target: { scrollTop: 150 * 40 },
    });

    expect(screen.getByText("Customer 150")).toBeInTheDocument();
    expect(screen.queryByText("Customer 0")).not.toBeInTheDocument();
  });
});
