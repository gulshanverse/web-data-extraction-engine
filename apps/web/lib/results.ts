import type { ResultItem, ResultsResponse } from "@/lib/api-client";

export const resultColumns = (items: ResultItem[]) =>
  [...new Set(items.flatMap((item) => Object.keys(item.data)))];

export const displayValue = (value: unknown) => {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
};

export const resultMetrics = (results: ResultsResponse) => ({
  total: results.total,
  passed: results.validation_summary.passed ?? 0,
  warnings: results.validation_summary.warnings ?? 0,
  failed: results.validation_summary.failed ?? 0,
  unresolved: results.validation_summary.unresolved ?? 0,
});
