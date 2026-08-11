import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { FilterRow } from "../src/components/query/FilterRow";
import type { FilterCondition, FilterOperator, QueryColumnOption } from "../src/types/query.types";

const dateColumn: QueryColumnOption = {
  key: "t0.LAST_BILL_DATE",
  label: "LAST_BILL_DATE",
  tableName: "t0",
  sourceTableName: "MERCADOS.CM_MASTER_DATA_JUL_2026_DVVNL",
  referenceName: "t0",
  columnName: "LAST_BILL_DATE",
  dtype: "VARCHAR2",
  nullable: true,
};

function renderRow(operator: FilterOperator, value = "") {
  const condition: FilterCondition = {
    id: "f1",
    column: dateColumn.key,
    operator,
    value,
  };
  render(
    <FilterRow condition={condition} columns={[dateColumn]} onChange={vi.fn()} onRemove={vi.fn()} />
  );
  // The operator <select> is the only combobox; the value box is the textbox.
  return { operatorSelect: screen.getByRole("combobox") as HTMLSelectElement };
}

describe("FilterRow on a date column", () => {
  it("lists the text-matching operators", () => {
    const { operatorSelect } = renderRow("=");
    const offered = Array.from(operatorSelect.options).map((option) => option.value);
    expect(offered).toContain("CONTAINS");
    expect(offered).toContain("STARTS WITH");
    expect(offered).toContain("BETWEEN");
    expect(offered).not.toContain("LIKE");
  });

  it.each(["CONTAINS", "NOT CONTAINS", "STARTS WITH", "ENDS WITH"] as FilterOperator[])(
    "gives %s a typeable text box, not a date picker",
    (operator) => {
      renderRow(operator);
      const input = document.querySelector("input:not([type='date'])") as HTMLInputElement | null;
      expect(input).not.toBeNull();
      expect(input?.type).toBe("text");
      // A date picker here would make a partial value like "07/2026" impossible
      // to enter, which is the whole point of these operators.
      expect(document.querySelector("input[type='date']")).toBeNull();
    }
  );

  it("still uses date pickers for an equality filter", () => {
    renderRow("=");
    expect(document.querySelector("input[type='date']")).not.toBeNull();
  });

  it("still uses two date pickers for BETWEEN", () => {
    renderRow("BETWEEN", "2026-07-01, 2026-07-31");
    expect(document.querySelectorAll("input[type='date']").length).toBe(2);
  });
});
