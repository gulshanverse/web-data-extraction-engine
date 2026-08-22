"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { jobsApi, type GeneratedFile, type JobStatusResponse, type ResultsResponse } from "@/lib/api-client";
import type { ExtractionRequest, MockRun, RunEvent } from "@/types/extraction";

const stageMap: Record<string, RunEvent["stage"]> = {
  PLANNING: "planning",
  DISCOVERING: "discovery",
  EXTRACTING: "extraction",
  VALIDATING: "validation",
  READY_FOR_EXPORT: "export",
  EXPORTING: "export",
};

const mapStage = (status: string): RunEvent["stage"] => stageMap[status] ?? "source";

const mapRun = (job: JobStatusResponse, formats: MockRun["outputFormats"] = []): MockRun => ({
  id: job.job_id,
  sourceUrl: "Connected source",
  outputFormats: formats,
  state: job.status === "COMPLETED" ? "completed" : job.status === "FAILED" ? "failed" : "running",
  startedAt: job.created_at,
  events: [
    {
      stage: mapStage(job.status),
      status: job.status === "FAILED" ? "failed" : job.status === "COMPLETED" ? "completed" : "active",
      message: job.error?.message ?? `Current stage: ${job.status.replaceAll("_", " ")}`,
    },
  ],
});

export function useJobWorkspace() {
  const [job, setJob] = useState<JobStatusResponse | null>(null);
  const [run, setRun] = useState<MockRun | null>(null);
  const [files, setFiles] = useState<GeneratedFile[]>([]);
  const [results, setResults] = useState<ResultsResponse | null>(null);
  const [resultsLoading, setResultsLoading] = useState(false);
  const [resultsError, setResultsError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (id: string) => {
    try {
      const next = await jobsApi.status(id);
      setJob(next);
      setRun(mapRun(next));
      if (next.status === "COMPLETED") {
        setResultsLoading(true);
        setResultsError(null);
        const [nextFiles, nextResults] = await Promise.all([jobsApi.files(id), jobsApi.results(id)]);
        setFiles(nextFiles.files);
        setResults(nextResults);
        setResultsLoading(false);
      }
      return next;
    } catch {
      setResultsLoading(false);
      setError("The workspace could not be refreshed safely.");
      throw new Error("Workspace refresh failed.");
    }
  }, []);

  const selectResultsPage = useCallback(async (page: number) => {
    if (!job || job.status !== "COMPLETED") return;
    try {
      setResultsLoading(true);
      setResultsError(null);
      setResults(await jobsApi.results(job.job_id, page));
    } catch {
      setResultsError("Results could not be loaded safely.");
    } finally {
      setResultsLoading(false);
    }
  }, [job]);

  const start = useCallback(
    async (request: ExtractionRequest) => {
      setError(null);
      setFiles([]);
      setResults(null);
      setResultsError(null);
      const created = await jobsApi.create(
        {
          project_id: "00000000-0000-0000-0000-000000000000",
          source_url: request.sourceUrl,
          task: request.intent,
          fields: [],
          output_formats: request.outputFormats,
          options: {
            max_pages: request.maxPages,
            max_records: request.maxRecords,
            follow_pagination: request.followPagination,
            follow_relevant_links: request.followLinks,
            extract_images: false,
            deduplicate: request.removeDuplicates,
            validate: request.validateResults,
          },
        },
        crypto.randomUUID(),
      );
      await refresh(created.job_id);
      window.history.replaceState(null, "", `?job=${created.job_id}`);
    },
    [refresh],
  );

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("job");
    if (id) void refresh(id);
  }, [refresh]);

  useEffect(() => {
    if (!job || ["COMPLETED", "FAILED", "CANCELLED"].includes(job.status)) return;
    const stream = new EventSource(jobsApi.eventsUrl(job.job_id));
    stream.onmessage = () => void refresh(job.job_id);
    stream.onerror = () => {
      stream.close();
      window.setTimeout(() => void refresh(job.job_id), 1500);
    };
    return () => stream.close();
  }, [job, refresh]);

  const progress = useMemo(() => job?.progress.percent ?? 0, [job]);
  return {
    run,
    progress,
    job,
    files,
    results,
    resultsLoading,
    resultsError,
    error,
    start,
    selectResultsPage,
    cancel: async () => job && refresh((await jobsApi.cancel(job.job_id)).job_id),
  };
}
