/** Data Loom frontend contracts: small UI-facing types that mirror Phase 0 terminology without implementing backend behavior. */
export const operationStages = ["source", "planning", "discovery", "extraction", "validation", "export"] as const;
export type OperationStage = (typeof operationStages)[number];
export type OperationState = "idle" | "running" | "completed" | "failed";
export type OutputFormat = "xlsx" | "csv" | "json" | "pdf" | "docx" | "md" | "txt" | "html";
export type ExtractionRequest = { sourceUrl: string; intent: string; outputFormats: OutputFormat[]; followPagination: boolean; followLinks: boolean; removeDuplicates: boolean; validateResults: boolean; maxPages: number; maxRecords: number; };
export type RunEvent = { stage: OperationStage; status: "pending" | "active" | "completed" | "failed"; timestamp?: string; message: string; };
export type MockRun = { id: string; state: OperationState; sourceUrl: string; outputFormats: OutputFormat[]; events: RunEvent[]; startedAt?: string; };
export type ValidationErrors = Partial<Record<"sourceUrl" | "intent" | "outputFormats" | "maxPages" | "maxRecords", string>>;
