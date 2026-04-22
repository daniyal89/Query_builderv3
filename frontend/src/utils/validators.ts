/**
 * validators.ts — Input validation utility functions.
 *
 * Provides client-side validation for file paths, required fields,
 * and CSV file type verification.
 */

/** Check if a path string looks like a valid .duckdb file path. */
export function isValidDuckDBPath(path: string): boolean {
  return path.trim().length > 0 && path.endsWith(".duckdb");
}

export function isRequired(value: string): boolean {
  return value.trim().length > 0;
}

export function isCSVFile(file: File): boolean {
  return file.type.includes("csv") || file.name.endsWith(".csv");
}
