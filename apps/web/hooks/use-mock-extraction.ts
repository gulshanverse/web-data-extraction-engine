/** Data Loom mock lifecycle hook: UI state transitions are timed locally and prepared for a future event-stream adapter. */
"use client";
import { useEffect, useMemo, useState } from "react";
import { createMockRun, progressMockRun } from "@/lib/mock-extraction";
import type { ExtractionRequest, MockRun } from "@/types/extraction";
export function useMockExtraction() { const [run, setRun] = useState<MockRun | null>(null); const [stageIndex, setStageIndex] = useState(0); useEffect(() => { if (!run || run.state !== "running") return; const timer = window.setTimeout(() => { setStageIndex((current) => { const next = Math.min(current + 1, 5); setRun((currentRun) => currentRun ? progressMockRun(currentRun, next) : currentRun); return next; }); }, 850); return () => window.clearTimeout(timer); }, [run, stageIndex]); const start = (request: ExtractionRequest) => { setStageIndex(0); setRun(progressMockRun(createMockRun(request), 0)); }; const reset = () => { setRun(null); setStageIndex(0); }; const progress = useMemo(() => !run ? 0 : run.state === "completed" ? 100 : Math.round(((stageIndex + 1) / run.events.length) * 100), [run, stageIndex]); return { run, start, reset, progress }; }
