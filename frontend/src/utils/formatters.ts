/**
 * formatters.ts — Data display helper functions.
 *
 * Provides formatting utilities for numbers (locale-aware), dates,
 * and string truncation used across the dashboard UI.
 */

/** Format a number with locale-aware thousand separators. */
export function formatNumber(value: number): string {
  // TODO: Implement with Intl.NumberFormat
  return String(value);
}

/** Format a date string or Date object into a readable format. */
export function formatDate(value: string | Date): string {
  // TODO: Implement with Intl.DateTimeFormat
  return String(value);
}

/** Truncate a string to maxLength, appending "…" if truncated. */
export function truncateText(text: string, maxLength: number = 50): string {
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength) + "...";
}
