/**
 * schema.types.ts — TypeScript interfaces for DuckDB schema introspection.
 *
 * Mirrors the backend's TableMetadata, ColumnDetail, and MasterTable Pydantic models.
 */

/** Descriptor for a single column within a DuckDB table. */
export interface ColumnDetail {
  /** Column name as defined in the schema. */
  name: string;
  /** DuckDB data type string (e.g., 'VARCHAR', 'INTEGER', 'TIMESTAMP'). */
  dtype: string;
  /** Whether the column accepts NULL values. */
  nullable: boolean;
}

/** Summary metadata for a single DuckDB table. */
export interface TableMetadata {
  /** Fully qualified table name. */
  table_name: string;
  /** Ordered list of column descriptors. */
  columns: ColumnDetail[];
  /** Total number of rows in the table. */
  row_count: number;
}

/**
 * Generic representation of a data record from any DuckDB table.
 *
 * Schema-agnostic model that holds a single row of data with column
 * names as keys and their corresponding values. Used for data preview,
 * query results, and CSV import staging.
 */
export interface MasterTable {
  /** Name of the originating DuckDB table. */
  source_table: string;
  /** Zero-based position of this row in the result set. */
  row_index: number;
  /** Column-name → value mapping for this row. */
  data: Record<string, unknown>;
}
