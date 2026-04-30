import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, vi } from "vitest";
import { HighlightedSqlEditor } from "../src/components/query/HighlightedSqlEditor";

function StatefulEditor({
  initialValue,
  suggestions = [],
}: {
  initialValue: string;
  suggestions?: Array<{ value: string; kind?: "table" | "column" }>;
}) {
  const [value, setValue] = useState(initialValue);

  return (
    <HighlightedSqlEditor
      value={value}
      onChange={setValue}
      suggestions={suggestions}
      placeholder="Write SQL directly here."
    />
  );
}

describe("HighlightedSqlEditor", () => {
  beforeEach(() => {
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback: FrameRequestCallback) => {
      callback(0);
      return 0;
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders highlighted SQL tokens and supports tab indentation", async () => {
    render(<StatefulEditor initialValue={"SELECT city\nFROM customers\nWHERE state = 'UP'"} />);

    const editor = screen.getByLabelText(/sql editor/i) as HTMLTextAreaElement;
    expect(editor).toHaveDisplayValue("SELECT city\nFROM customers\nWHERE state = 'UP'");

    const highlightedTokens = Array.from(
      document.querySelectorAll('[data-token-type="sql-token"]'),
    ).map((node) => node.textContent);

    expect(highlightedTokens).toContain("SELECT");
    expect(highlightedTokens).toContain("FROM");
    expect(highlightedTokens).toContain("'UP'");

    editor.focus();
    editor.setSelectionRange(6, 6);
    fireEvent.keyDown(editor, { key: "Tab" });

    await waitFor(() => {
      expect(editor).toHaveDisplayValue("SELECT   city\nFROM customers\nWHERE state = 'UP'");
    });
  });

  it("keeps manual SQL horizontally scrollable for long queries", () => {
    render(<StatefulEditor initialValue={"SELECT some_really_long_column_name FROM very_long_table_name"} />);

    const editor = screen.getByLabelText(/sql editor/i) as HTMLTextAreaElement;

    expect(editor.getAttribute("wrap")).toBe("off");
    expect(editor.className).toContain("overflow-auto");
    expect(editor.className).toContain("whitespace-pre");
  });

  it("offers table and column suggestions while typing", async () => {
    render(
      <StatefulEditor
        initialValue="SEL"
        suggestions={[
          { value: "SELECT", kind: "column" },
          { value: "Master_0326", kind: "table" },
          { value: "DIV_CODE", kind: "column" },
        ]}
      />,
    );

    const editor = screen.getByLabelText(/sql editor/i) as HTMLTextAreaElement;
    editor.focus();
    editor.setSelectionRange(3, 3);
    fireEvent.keyUp(editor, { key: "L" });

    const suggestion = await screen.findByRole("button", { name: /select/i });
    fireEvent.mouseDown(suggestion);

    await waitFor(() => {
      expect(editor).toHaveDisplayValue("SELECT");
    });
  });
});
