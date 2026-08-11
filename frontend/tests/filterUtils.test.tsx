import { describe, expect, it } from "vitest";
import { getColumnFamily, getOperatorsForColumn } from "../src/utils/filterUtils";
import type { QueryColumnOption } from "../src/types/query.types";

const column = (columnName: string, dtype: string): QueryColumnOption => ({
  key: `t.${columnName}`,
  label: columnName,
  tableName: "t",
  sourceTableName: "t",
  referenceName: "t",
  columnName,
  dtype,
  nullable: true,
});

describe("getOperatorsForColumn", () => {
  it("offers CONTAINS on a date column", () => {
    // Marcadose keeps most dates in VARCHAR2, so substring matching on them is
    // how operators find "every bill in 07/2026". This regressed to range-only.
    const operators = getOperatorsForColumn(column("BILL_DATE", "VARCHAR2"));
    expect(operators).toContain("CONTAINS");
    expect(operators).toContain("NOT CONTAINS");
    expect(operators).toContain("STARTS WITH");
    expect(operators).toContain("ENDS WITH");
  });

  it("keeps the range operators on a date column", () => {
    const operators = getOperatorsForColumn(column("BILL_DATE", "VARCHAR2"));
    expect(operators).toContain("BETWEEN");
    expect(operators).toContain(">=");
    expect(operators).toContain("IN");
  });

  it("withholds LIKE from a date column", () => {
    // The backend sends LIKE on a date-like column through the date-literal
    // path, which demands YYYY-MM-DD and cannot express a pattern. Offering it
    // would only produce an error the operator cannot act on.
    const operators = getOperatorsForColumn(column("BILL_DATE", "VARCHAR2"));
    expect(operators).not.toContain("LIKE");
    expect(operators).not.toContain("NOT LIKE");
  });

  it("applies to a real DATE type as well as a date-shaped name", () => {
    expect(getOperatorsForColumn(column("READING_DT", "DATE"))).toContain("CONTAINS");
  });

  it("leaves text columns as they were", () => {
    const operators = getOperatorsForColumn(column("CONSUMER_NAME", "VARCHAR2"));
    expect(operators).toContain("CONTAINS");
    expect(operators).toContain("LIKE");
    expect(operators).not.toContain("BETWEEN");
  });

  it("does not offer text matching on a numeric column", () => {
    const operators = getOperatorsForColumn(column("TOTAL_AMT", "NUMBER"));
    expect(operators).not.toContain("CONTAINS");
    expect(operators).toContain("BETWEEN");
  });

  it("lists every operator only once", () => {
    // RANGE_OPERATORS and the text sets both carry IN/NOT IN, so a naive
    // concatenation would render duplicate entries in the dropdown.
    const operators = getOperatorsForColumn(column("BILL_DATE", "VARCHAR2"));
    expect(new Set(operators).size).toBe(operators.length);
  });
});

describe("getColumnFamily", () => {
  it("treats a date-shaped name as a date even when the type is text", () => {
    expect(getColumnFamily("VARCHAR2", "BILL_DATE")).toBe("date");
  });

  it("falls back to the declared type when the name says nothing", () => {
    expect(getColumnFamily("VARCHAR2", "CONSUMER_NAME")).toBe("text");
    expect(getColumnFamily("BIGINT", "TOTAL_AMT")).toBe("number");
  });

  it("treats DOC as a date even though its name says nothing", () => {
    // Date of connection, stored as "26-MAR-2025". Kept in step with
    // EXPLICIT_DATE_COLUMNS in query_builder_service.py.
    expect(getColumnFamily("VARCHAR2", "DOC")).toBe("date");
    expect(getColumnFamily("VARCHAR2", "MERCADOS.CM_MASTER_DATA_JUL_2026_DVVNL.DOC")).toBe("date");
    expect(getColumnFamily("VARCHAR2", "BILL_CRE_DTTM")).toBe("date");
  });

  it("offers date and text operators on DOC", () => {
    const operators = getOperatorsForColumn(column("DOC", "VARCHAR2"));
    expect(operators).toContain("BETWEEN");
    expect(operators).toContain(">=");
    expect(operators).toContain("CONTAINS");
  });

  it("keeps DUE_DATE_REBATE numeric despite the DATE in its name", () => {
    // It holds a rupee amount, so it needs numeric comparison, not a date picker.
    expect(getColumnFamily("NUMBER", "DUE_DATE_REBATE")).toBe("number");
    const operators = getOperatorsForColumn(column("DUE_DATE_REBATE", "NUMBER"));
    expect(operators).toContain("BETWEEN");
    expect(operators).toContain("<");
  });

  it("does not recognise Oracle's NUMBER type", () => {
    // Documenting a known gap rather than asserting it is correct: the numeric
    // regex matches NUMERIC but not NUMBER, so every Oracle number column lands
    // in "other". Harmless today because "other" and "number" yield the same
    // operators and no caller distinguishes them -- but it will bite anyone who
    // starts branching on "number".
    expect(getColumnFamily("NUMBER", "TOTAL_AMT")).toBe("other");
    expect(getOperatorsForColumn(column("TOTAL_AMT", "NUMBER"))).toEqual(
      getOperatorsForColumn(column("TOTAL_AMT", "BIGINT"))
    );
  });
});
