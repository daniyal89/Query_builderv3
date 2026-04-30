/**
 * formatters.ts — Data display helper functions.
 *
 * Provides formatting utilities for numbers (locale-aware), dates,
 * and string truncation used across the dashboard UI.
 */

/** Format a number with locale-aware thousand separators. */
export function formatNumber(value: number): string {
  if (value == null) return "";
  return new Intl.NumberFormat().format(value);
}

/** Format a date string or Date object into a readable format. */
export function formatDate(value: string | Date): string {
  if (!value) return "";
  const date = typeof value === "string" ? new Date(value) : value;
  if (isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

/** Truncate a string to maxLength, appending "…" if truncated. */
export function truncateText(text: string, maxLength: number = 50): string {
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength) + "...";
}
