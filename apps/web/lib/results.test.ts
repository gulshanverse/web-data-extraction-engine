import { describe, expect, it } from "vitest";

import type { ResultsResponse } from "./api-client";
import { displayValue, resultColumns, resultMetrics } from "./results";

const results: ResultsResponse = {
  job_id: "job-1",
  page: 1,
  page_size: 50,
  total: 2,
  validation_available: true,
  validation_summary: { records: 2, passed: 1, warnings: 1, failed: 0, unresolved: 0 },
  items: [
    { record_id: "record-1", data: { name: "Real record", price: 12 }, validation: { status: "PASS", quality: "HIGH", summary: { pass: 1 } } },
    { record_id: "record-2", data: { name: "Review record", url: "https://example.test" }, validation: { status: "WARN", quality: "MEDIUM", summary: { warn: 1 } } },
  ],
};

describe("real results view model", () => {
  it("derives columns from backend records rather than sample rows", () => {
    expect(resultColumns(results.items)).toEqual(["name", "price", "url"]);
  });

  it("derives job-wide metrics from the backend validation summary", () => {
    expect(resultMetrics(results)).toEqual({ total: 2, passed: 1, warnings: 1, failed: 0, unresolved: 0 });
  });

  it("renders untrusted values as inert display text", () => {
    expect(displayValue("<script>alert(1)</script>")).toBe("<script>alert(1)</script>");
    expect(displayValue(null)).toBe("—");
  });
});
