"""
merge_service.py — Business logic for multi-sheet merge and enrichment.
"""

import duckdb
import pandas as pd


class MergeService:
    """Service to handle the data logic for the multi-sheet merge workflow."""

    @staticmethod
    def process_enrichment(merged_df: pd.DataFrame, db_path: str, fetch_column: str) -> tuple[pd.DataFrame, dict]:
        """
        Executes a SQL LEFT JOIN between the incoming dataframe and the DuckDB master table.
        
        Args:
            merged_df: The Pandas DataFrame containing uploaded/resolved data.
            db_path: Path to the DuckDB master database.
            fetch_column: The column to extract from the master table.
            
        Returns:
            Tuple of (enriched_dataframe, stats_dictionary).
        """
        # Standardize key columns to uppercase exact matches for the SQL query
        col_map = {}
        target_keys = ["DISCOM", "DIV_CODE"]
        acct_id_aliases = ["ACC_ID", "ACCT_ID", "ACCOUNT_ID"]
        
        for c in merged_df.columns:
            u_c = str(c).upper()
            if u_c in target_keys:
                col_map[c] = u_c
            elif u_c in acct_id_aliases:
                col_map[c] = "ACCT_ID"
                
        if col_map:
            merged_df.rename(columns=col_map, inplace=True)

        if "ACCT_ID" not in merged_df.columns:
            raise ValueError("The uploaded data must contain an 'ACCT_ID' or equivalent column.")

        has_discom = "DISCOM" in merged_df.columns
        has_div_code = "DIV_CODE" in merged_df.columns
        
        if not has_discom and not has_div_code:
            raise ValueError("The uploaded data must contain either 'DISCOM' or 'DIV_CODE' to perform the join.")

        # Safely build conditional clauses depending on what exists in the df
        discom_clause = "df.DISCOM = master.DISCOM" if has_discom else "1=0"
        div_code_clause = "df.DIV_CODE = master.DIV_CODE" if has_div_code else "1=0"

        # Open short-lived connection exclusively for this operation
        conn = duckdb.connect(db_path, read_only=True)
        try:
            # Register the pandas dataframe as a virtual table 'df'
            conn.register('df', merged_df)
            
            # Execute LEFT JOIN
            query = f"""
                SELECT df.*, master."{fetch_column}"
                FROM df
                LEFT JOIN master
                ON df.ACCT_ID = master.ACCT_ID
                AND ({discom_clause} OR {div_code_clause})
            """
            result_df = conn.execute(query).df()
            
            # Calculate matching statistics using an INNER JOIN for the matched count
            matched_query = f"""
                SELECT COUNT(*) FROM df
                INNER JOIN master
                ON df.ACCT_ID = master.ACCT_ID
                AND ({discom_clause} OR {div_code_clause})
            """
            matched_rows = int(conn.execute(matched_query).fetchone()[0])
            total_rows = len(result_df)
            unmatched_rows = total_rows - matched_rows
            
            stats = {
                "matched_rows": matched_rows,
                "unmatched_rows": unmatched_rows,
                "total_rows": total_rows
            }
            
            return result_df, stats
            
        except duckdb.CatalogException as e:
            if "master" in str(e):
                raise ValueError("Target database does not contain a 'master' table.")
            raise
        finally:
            # DuckDB cleans up registered dataframes on close
            conn.close()
