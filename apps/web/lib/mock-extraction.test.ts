import { describe, expect, it } from "vitest";
import { createMockRun, progressMockRun } from "./mock-extraction";
import type { ExtractionRequest } from "@/types/extraction";

const request: ExtractionRequest = { sourceUrl: "https://example.com/products", intent: "Extract product name, category, price and source URL.", outputFormats: ["xlsx", "csv"], followPagination: true, followLinks: false, removeDuplicates: true, validateResults: true, maxPages: 20, maxRecords: 1000 };

describe("mock extraction lifecycle", () => {
  it("starts with typed pending Phase 0 lifecycle events", () => { const run = createMockRun(request); expect(run.state).toBe("running"); expect(run.events.map((event) => event.stage)).toEqual(["source", "planning", "discovery", "extraction", "validation", "export"]); expect(run.events.every((event) => event.status === "pending")).toBe(true); });
  it("promotes the active stage and completes preceding stages", () => { const started = progressMockRun(createMockRun(request), 0); const progressed = progressMockRun(started, 2); expect(progressed.events.slice(0, 2).every((event) => event.status === "completed")).toBe(true); expect(progressed.events[2].status).toBe("active"); });
  it("completes the run only after export", () => { const finished = progressMockRun(createMockRun(request), 5); expect(finished.state).toBe("completed"); expect(finished.events.every((event) => event.status === "completed" || event.status === "active")).toBe(true); });
});
