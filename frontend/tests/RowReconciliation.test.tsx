import { render, screen } from "@testing-library/react";
import { RowReconciliation } from "../src/components/sidebar/RowReconciliation";
import type { FileRowAudit, RowReconciliation as Reconciliation } from "../src/api/sidebarToolsApi";

function reconciliation(overrides: Partial<Reconciliation> = {}): Reconciliation {
  return {
    source_rows: 0,
    written_rows: 0,
    reused_rows: 0,
    quarantined_rows: 0,
    unaccounted_rows: 0,
    balanced: true,
    discrepancies: [],
    ...overrides,
  };
}

function audit(overrides: Partial<FileRowAudit> = {}): FileRowAudit {
  return {
    source_file: "DIV1.csv.gz",
    outcome: "written",
    reason: "",
    source_rows: 0,
    written_rows: 0,
    quarantined_rows: 0,
    quarantine_reasons: {},
    ...overrides,
  };
}

/** Digit grouping follows the runtime locale (Indian grouping in this app), so
 *  never hardcode "103,074" — format the expectation the same way the UI does. */
function n(value: number): string {
  return value.toLocaleString();
}

/** The summary line is assembled from several JSX nodes, so match on textContent. */
function hasText(pattern: RegExp) {
  return (_content: string, element: Element | null) => {
    if (!element) return false;
    const own = element.textContent ?? "";
    const childMatches = Array.from(element.children).some((child) =>
      pattern.test(child.textContent ?? ""),
    );
    return pattern.test(own) && !childMatches;
  };
}

describe("RowReconciliation", () => {
  it("renders nothing before any rows have been read", () => {
    const { container } = render(<RowReconciliation reconciliation={reconciliation()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("confirms a clean run balances", () => {
    render(
      <RowReconciliation
        reconciliation={reconciliation({ source_rows: 103074, written_rows: 103074 })}
        dataQuality="ok"
      />,
    );

    expect(
      screen.getByText(hasText(new RegExp(`Source ${n(103074)}.*Written ${n(103074)}`))),
    ).toBeInTheDocument();
    expect(screen.getByText(/every source row is accounted for/i)).toBeInTheDocument();
  });

  it("shouts when rows are unaccounted for", () => {
    render(
      <RowReconciliation
        reconciliation={reconciliation({
          source_rows: 1000,
          written_rows: 800,
          unaccounted_rows: 200,
          balanced: false,
          discrepancies: ["DIV1.csv.gz: source 1,000, written 800, quarantined 0 -> 200 unaccounted"],
        })}
        dataQuality="loss"
      />,
    );

    expect(screen.getByText(/row loss: 200 row\(s\) unaccounted for/i)).toBeInTheDocument();
    expect(screen.getByText(/200 unaccounted/)).toBeInTheDocument();
  });

  it("breaks quarantined rows down by reason", () => {
    render(
      <RowReconciliation
        reconciliation={reconciliation({
          source_rows: 1000,
          written_rows: 978,
          quarantined_rows: 22,
        })}
        dataQuality="warning"
        rowAudit={[
          audit({
            quarantined_rows: 22,
            quarantine_reasons: { ACCT_ID_NON_NUMERIC: 20, ACCT_ID_BLANK: 2 },
            quarantine_file: "out/_quarantine/DIV1.ACCT_ID_INVALID.parquet",
          }),
        ]}
      />,
    );

    expect(screen.getByText(hasText(/Quarantined 22/))).toBeInTheDocument();
    expect(screen.getByText(hasText(/ACCT_ID_NON_NUMERIC: 20/))).toBeInTheDocument();
    expect(screen.getByText(hasText(/ACCT_ID_BLANK: 2/))).toBeInTheDocument();
    // The rejected rows are kept, not discarded.
    expect(screen.getByText(/DIV1\.ACCT_ID_INVALID\.parquet/)).toBeInTheDocument();
  });

  it("lists files that failed outright", () => {
    render(
      <RowReconciliation
        reconciliation={reconciliation({ source_rows: 500, written_rows: 0, unaccounted_rows: 500 })}
        dataQuality="loss"
        rowAudit={[
          audit({
            source_file: "DIV293313.csv.gz",
            outcome: "failed",
            reason: "MISSING_ACCT_ID_COLUMN",
            source_rows: 500,
          }),
        ]}
      />,
    );

    expect(screen.getByText(/1 file\(s\) failed/)).toBeInTheDocument();
    expect(screen.getByText(/MISSING_ACCT_ID_COLUMN/)).toBeInTheDocument();
  });

  it("counts empty sources separately from files that failed", () => {
    render(
      <RowReconciliation
        reconciliation={reconciliation({ source_rows: 1000, written_rows: 1000 })}
        dataQuality="warning"
        rowAudit={[
          audit({ source_file: "ok.csv.gz", source_rows: 1000, written_rows: 1000 }),
          ...Array.from({ length: 93 }, (_, i) =>
            audit({ source_file: `empty${i}.csv.gz`, outcome: "failed", reason: "EMPTY_FILE" }),
          ),
        ]}
      />,
    );

    // 93 empty divisions are not 93 failures — that framing buried the real ones.
    expect(screen.queryByText(/file\(s\) failed/)).not.toBeInTheDocument();
    expect(screen.getByText(/93 source file\(s\) held no rows/)).toBeInTheDocument();
  });

  it("still lists a real failure that arrives alongside empty sources", () => {
    render(
      <RowReconciliation
        reconciliation={reconciliation({ source_rows: 500, written_rows: 0, unaccounted_rows: 500 })}
        dataQuality="loss"
        rowAudit={[
          audit({ source_file: "empty.csv.gz", outcome: "failed", reason: "EMPTY_FILE" }),
          audit({
            source_file: "truncated.csv.gz",
            outcome: "failed",
            reason: "TRUNCATED_EOF",
            source_rows: 500,
          }),
        ]}
      />,
    );

    expect(screen.getByText(/1 file\(s\) failed/)).toBeInTheDocument();
    expect(screen.getByText(/TRUNCATED_EOF/)).toBeInTheDocument();
    expect(screen.getByText(/1 source file\(s\) held no rows/)).toBeInTheDocument();
  });
});
