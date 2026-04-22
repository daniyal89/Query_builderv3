/**
 * MappingTable.tsx — CSV-to-DuckDB column mapping interface.
 *
 * Two-column table: CSV header → DuckDB column dropdown for each field.
 * Includes a "skip" checkbox per row to exclude columns from import.
 *
 * Props:
 *   csvHeaders: string[]                        — Headers from the CSV file.
 *   dbColumns: ColumnDetail[]                   — Available columns in the target table.
 *   mappings: ColumnMapping[]                   — Current column mapping state.
 *   onUpdate: (index, mapping) => void          — Update a mapping row.
 */

// TODO: Render mapping rows with CSV header label + DB column dropdown + skip checkbox
