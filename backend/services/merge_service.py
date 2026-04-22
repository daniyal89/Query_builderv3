"""
merge_service.py - Business logic for multi-sheet merge and enrichment.
"""

import duckdb
import pandas as pd


class MergeService:
    """Service to handle the data logic for the multi-sheet merge workflow."""

    @staticmethod
    def process_enrichment(
        merged_df: pd.DataFrame,
        conn: duckdb.DuckDBPyConnection,
        fetch_columns: list[str],
        mapped_acct_id_col: str,
        mapped_secondary_col: str,
        secondary_key_type: str,
    ) -> tuple[pd.DataFrame, dict]:
        """
        Execute a SQL LEFT JOIN between the incoming dataframe and the DuckDB master table.
        """
        if mapped_acct_id_col not in merged_df.columns:
            raise ValueError(
                f"Mapped ACCT_ID column '{mapped_acct_id_col}' not found in uploaded file."
            )

        if mapped_secondary_col not in merged_df.columns:
            raise ValueError(
                f"Mapped Secondary Key column '{mapped_secondary_col}' not found in uploaded file."
            )

        join_clause = (
            f'df."{mapped_acct_id_col}" = master.ACCT_ID AND '
            f'df."{mapped_secondary_col}" = master.{secondary_key_type}'
        )
        fetch_cols_str = ", ".join([f'master."{column}"' for column in fetch_columns])

        try:
            conn.register("df", merged_df)

            query = f"""
                SELECT df.*, {fetch_cols_str}
                FROM df
                LEFT JOIN master
                ON {join_clause}
            """
            result_df = conn.execute(query).df()

            matched_query = f"""
                SELECT COUNT(*) FROM df
                INNER JOIN master
                ON {join_clause}
            """
            matched_rows = int(conn.execute(matched_query).fetchone()[0])
            total_rows = len(result_df)
            unmatched_rows = total_rows - matched_rows

            stats = {
                "matched_rows": matched_rows,
                "unmatched_rows": unmatched_rows,
                "total_rows": total_rows,
            }

            return result_df, stats
        except duckdb.CatalogException as exc:
            if "master" in str(exc):
                raise ValueError("Target database does not contain a 'master' table.") from exc
            raise
        finally:
            try:
                conn.unregister("df")
            except Exception:
                pass
