import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { describe, expect, it } from "vitest";

import type { ResultsResponse } from "@/lib/api-client";
import type { MockRun } from "@/types/extraction";
import { ResultWorkspace } from "./result-workspace";

const run: MockRun = {
  id: "job-real-results",
  state: "completed" as const,
  sourceUrl: "Connected source",
  outputFormats: ["json"],
  events: [],
};

const results: ResultsResponse = {
  job_id: "job-real-results",
  page: 1,
  page_size: 50,
  total: 1,
  validation_available: true,
  validation_summary: { records: 1, passed: 1, warnings: 0, failed: 0, unresolved: 0 },
  items: [{ record_id: "record-real", data: { name: "Persisted name", price: 12 }, validation: { status: "PASS", quality: "HIGH", summary: { pass: 1 } } }],
};

describe("ResultWorkspace", () => {
  it("renders durable API records and validation rather than production sample rows", () => {
    const markup = renderToStaticMarkup(<ResultWorkspace run={run} results={results} loading={false} error={null} onPageChange={() => undefined} />);
    expect(markup).toContain("Persisted name");
    expect(markup).toContain("PASS · HIGH");
    expect(markup).not.toContain("Aster Canvas Carryall");
    expect(markup).not.toContain("Completed mock run");
  });

  it("renders a real empty state and a safe API failure state", () => {
    const empty = renderToStaticMarkup(<ResultWorkspace run={run} results={{ ...results, total: 0, items: [] }} loading={false} error={null} onPageChange={() => undefined} />);
    const failed = renderToStaticMarkup(<ResultWorkspace run={run} results={null} loading={false} error="Results could not be loaded safely." onPageChange={() => undefined} />);
    expect(empty).toContain("no persisted records");
    expect(failed).toContain("Results could not be loaded safely.");
  });
});
