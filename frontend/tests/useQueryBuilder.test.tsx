import { act, renderHook } from "@testing-library/react";
import { rest } from "msw";
import { server } from "./testServer";
import { useQueryBuilder } from "../src/hooks/useQueryBuilder";

describe("useQueryBuilder join aliasing", () => {
  it("keeps natural references for unique joins and renames stateful references on alias changes", () => {
    server.use(
      rest.post("*/api/query/preview", async (req, res, ctx) => {
        return res(
          ctx.json({
            sql: "SELECT 1",
            source_mode: "builder",
            can_sync_builder: true,
          })
        );
      })
    );

    const { result } = renderHook(() => useQueryBuilder("duckdb"));

    act(() => {
      result.current.setTable("master");
      result.current.addJoin();
    });

    const firstJoinId = result.current.state.joins[0].id;
    const firstConditionId = result.current.state.joins[0].conditions[0].id;

    act(() => {
      result.current.updateJoin(firstJoinId, { table: "detail" });
      result.current.updateJoinCondition(firstJoinId, firstConditionId, {
        leftColumn: "master.ACCT_ID",
        rightColumn: "detail.ACCT_ID",
      });
      result.current.addJoin();
    });

    const secondJoinId = result.current.state.joins[1].id;

    act(() => {
      result.current.updateJoin(secondJoinId, { table: "detail" });
    });

    const configuredSecondConditionId = result.current.state.joins[1].conditions[0].id;

    expect(result.current.state.joins[0].alias).toBe("");
    expect(result.current.state.joins[1].alias).toBe("detail_2");

    act(() => {
      result.current.updateJoinCondition(secondJoinId, configuredSecondConditionId, {
        leftColumn: "detail.ACCT_ID",
        rightColumn: "detail_2.RELATED_ID",
      });
      result.current.toggleColumn("detail_2.STATUS");
      result.current.addFilter();
      result.current.setSort([{ column: "detail_2.STATUS", direction: "ASC" }]);
    });

    const filterId = result.current.state.filters[0].id;

    act(() => {
      result.current.updateFilter(filterId, {
        column: "detail_2.STATUS",
        operator: "=",
        value: "ACTIVE",
      });
      result.current.updateJoin(secondJoinId, { alias: "detail_archive" });
    });

    expect(result.current.state.selectedColumns).toContain("detail_archive.STATUS");
    expect(result.current.state.filters[0]?.column).toBe("detail_archive.STATUS");
    expect(result.current.state.sort[0]?.column).toBe("detail_archive.STATUS");
    expect(result.current.state.joins[1].conditions[0]?.rightColumn).toBe("detail_archive.RELATED_ID");
  });
});
