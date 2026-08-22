/**
 * Instrument Panel design system: an asymmetric operations bench where source, intent, controls, output, and state form the hierarchy.
 */
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  ArrowRight,
  Braces,
  Check,
  ChevronDown,
  CircleHelp,
  Code2,
  Database,
  FileSpreadsheet,
  FileText,
  Gauge,
  Globe2,
  Layers3,
  Link2,
  ListFilter,
  Loader2,
  Menu,
  MoreHorizontal,
  Play,
  Plus,
  Settings2,
  ShieldCheck,
  Sparkles,
  Table2,
  X,
} from "lucide-react";

type RunState = "idle" | "running" | "complete";

type OutputFormat = {
  id: string;
  name: string;
  detail: string;
  icon: typeof FileSpreadsheet;
};

const workflow = [
  { id: "source", label: "Source", detail: "Source verified", icon: Globe2 },
  { id: "planning", label: "Planning", detail: "Plan compiled", icon: Sparkles },
  { id: "discovery", label: "Discovery", detail: "Pages mapped", icon: Layers3 },
  { id: "extraction", label: "Extraction", detail: "Fields parsed", icon: Database },
  { id: "validation", label: "Validation", detail: "Records checked", icon: ShieldCheck },
  { id: "export", label: "Export", detail: "Files prepared", icon: FileSpreadsheet },
] as const;

const formats: OutputFormat[] = [
  { id: "xlsx", name: "Excel", detail: ".xlsx workbook", icon: FileSpreadsheet },
  { id: "csv", name: "CSV", detail: "flat data table", icon: Table2 },
  { id: "json", name: "JSON", detail: "structured records", icon: Braces },
  { id: "pdf", name: "PDF", detail: "report layout", icon: FileText },
  { id: "docx", name: "DOCX", detail: "document export", icon: FileText },
  { id: "md", name: "Markdown", detail: "portable notes", icon: Code2 },
  { id: "txt", name: "TXT", detail: "plain text", icon: FileText },
];

const resultStats = [
  { label: "Records", value: "438", detail: "structured rows" },
  { label: "Pages", value: "14", detail: "processed" },
  { label: "Duplicates", value: "21", detail: "removed" },
  { label: "Validation", value: "98.7%", detail: "confidence" },
];

function isValidHttpUrl(value: string) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:";
  } catch {
    return false;
  }
}

export default function Home() {
  const [sourceUrl, setSourceUrl] = useState("https://example.com/catalog");
  const [task, setTask] = useState(
    "Extract all products with name, price, rating, category and product URL.",
  );
  const [selectedFormats, setSelectedFormats] = useState<string[]>(["xlsx", "csv", "json"]);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [followPagination, setFollowPagination] = useState(true);
  const [followLinks, setFollowLinks] = useState(false);
  const [removeDuplicates, setRemoveDuplicates] = useState(true);
  const [validateResults, setValidateResults] = useState(true);
  const [runState, setRunState] = useState<RunState>("idle");
  const [stageIndex, setStageIndex] = useState(0);
  const [urlError, setUrlError] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);

  const activeStage = workflow[stageIndex];
  const progress = runState === "idle" ? 0 : runState === "complete" ? 100 : Math.round(((stageIndex + 1) / workflow.length) * 100);

  const selectedFormatNames = useMemo(
    () => formats.filter((format) => selectedFormats.includes(format.id)).map((format) => format.name),
    [selectedFormats],
  );

  useEffect(() => {
    if (runState !== "running") return;

    const timeout = window.setTimeout(() => {
      setStageIndex((current) => {
        if (current >= workflow.length - 1) {
          setRunState("complete");
          return current;
        }
        return current + 1;
      });
    }, 820);

    return () => window.clearTimeout(timeout);
  }, [runState, stageIndex]);

  const toggleFormat = (id: string) => {
    setSelectedFormats((current) =>
      current.includes(id) ? current.filter((format) => format !== id) : [...current, id],
    );
  };

  const startExtraction = () => {
    if (!isValidHttpUrl(sourceUrl)) {
      setUrlError("Enter an http or https source URL before queueing an extraction.");
      return;
    }
    if (!task.trim()) return;
    setUrlError("");
    setStageIndex(0);
    setRunState("running");
  };

  const resetRun = () => {
    setRunState("idle");
    setStageIndex(0);
  };

  return (
    <div className="app-shell">
      <aside className={`side-rail ${menuOpen ? "is-open" : ""}`} aria-label="Primary navigation">
        <div className="rail-brand">
          <img className="brand-mark" src="/manus-storage/wdre-mark_25146774.png" alt="Web Data Extraction Engine extraction bracket" />
          <div className="wordmark">
            <span className="brand-name">web/data</span>
            <span className="brand-subtitle">extraction engine</span>
          </div>
          <button className="rail-close" type="button" onClick={() => setMenuOpen(false)} aria-label="Close navigation">
            <X size={18} />
          </button>
        </div>

        <div className="rail-project">
          <span className="eyebrow">Active project</span>
          <strong>Catalog Audit</strong>
          <span className="rail-project-meta">01 / Data operations</span>
        </div>

        <nav className="rail-nav">
          <button className="rail-link is-active" type="button"><Gauge size={17} /> Workspace</button>
          <button className="rail-link" type="button"><Layers3 size={17} /> Runs <span className="rail-count">01</span></button>
          <button className="rail-link" type="button"><Database size={17} /> Datasets</button>
          <button className="rail-link" type="button"><FileText size={17} /> Exports</button>
        </nav>

        <div className="rail-footer">
          <div className="policy-note">
            <ShieldCheck size={16} />
            <span>Public-source policy active</span>
          </div>
          <button className="rail-link" type="button"><Settings2 size={17} /> Settings</button>
        </div>
      </aside>

      <main className="workspace-main">
        <header className="topbar">
          <div className="topbar-left">
            <button className="menu-button" type="button" onClick={() => setMenuOpen(true)} aria-label="Open navigation"><Menu size={20} /></button>
            <div className="breadcrumb"><span>Workspace</span><ArrowRight size={13} /><strong>New extraction</strong></div>
          </div>
          <div className="topbar-actions">
            <span className="environment-pill"><span className="live-dot" /> mock environment</span>
            <button className="icon-button" type="button" aria-label="Help"><CircleHelp size={18} /></button>
            <button className="avatar-button" type="button" aria-label="Account menu">GK</button>
          </div>
        </header>

        <div className="workspace-grid">
          <section className="command-sheet" aria-labelledby="workspace-heading">
            <div className="section-lede">
              <div>
                <p className="eyebrow">New operation <span>— 001</span></p>
                <h1 id="workspace-heading">Define the source.<br />Describe the signal.</h1>
              </div>
              <div className="lede-meta">
                <span>Phase 1 interface</span>
                <span className="calibration-line" />
                <span>Event-ready</span>
              </div>
            </div>

            <form onSubmit={(event) => { event.preventDefault(); startExtraction(); }}>
              <div className="form-section source-section">
                <div className="section-marker"><span>01</span><div><h2>Source</h2><p>Public, permitted target. Policy checks run before browser allocation.</p></div></div>
                <label className="field-label" htmlFor="source-url">Website URL</label>
                <div className={`source-input ${urlError ? "has-error" : ""}`}>
                  <Globe2 size={19} aria-hidden="true" />
                  <Input id="source-url" type="url" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} aria-invalid={Boolean(urlError)} aria-describedby={urlError ? "source-error" : undefined} />
                  <span className="source-state">HTTPS</span>
                </div>
                {urlError && <p id="source-error" className="field-error" role="alert">{urlError}</p>}
              </div>

              <div className="form-section intent-section">
                <div className="section-marker"><span>02</span><div><h2>Extraction intent</h2><p>Specify fields, record definition, and result rule in operational language.</p></div></div>
                <label className="field-label" htmlFor="extraction-intent">Natural-language task</label>
                <Textarea id="extraction-intent" value={task} onChange={(event) => setTask(event.target.value)} rows={5} />
                <div className="intent-footer">
                  <span><Sparkles size={14} /> Plan gate: schema and policy validation precede browser work.</span>
                  <span>{task.length} / 1,500</span>
                </div>
              </div>

              <div className="form-section controls-section">
                <div className="section-marker"><span>03</span><div><h2>Guardrails</h2><p>Policy-bound controls. You can narrow a run; system ceilings still apply.</p></div></div>
                <div className="control-grid">
                  <Control label="Follow pagination" description="Traverse documented next-page routes" checked={followPagination} onChange={setFollowPagination} />
                  <Control label="Relevant links" description="Open permitted detail references" checked={followLinks} onChange={setFollowLinks} />
                  <Control label="Remove duplicates" description="Collapse canonical record matches" checked={removeDuplicates} onChange={setRemoveDuplicates} />
                  <Control label="Validate results" description="Apply field and source-URL checks" checked={validateResults} onChange={setValidateResults} />
                </div>
                <button className="advanced-toggle" type="button" onClick={() => setShowAdvanced((current) => !current)} aria-expanded={showAdvanced}>
                  <ListFilter size={16} /> Inspect limits <ChevronDown size={16} className={showAdvanced ? "is-rotated" : ""} />
                </button>
                {showAdvanced && (
                  <div className="advanced-panel">
                    <label><span>Maximum pages</span><Input type="number" min="1" max="100" defaultValue="20" /></label>
                    <label><span>Maximum records</span><Input type="number" min="1" max="10000" defaultValue="1000" /></label>
                    <p><ShieldCheck size={15} /> Browser-policy ceilings remain enforced beyond these requested limits.</p>
                  </div>
                )}
              </div>

              <div className="form-section output-section">
                <div className="section-marker"><span>04</span><div><h2>Output package</h2><p>Select the serialized artifacts to assemble after validation.</p></div></div>
                <div className="format-grid" role="group" aria-label="Output formats">
                  {formats.map((format) => {
                    const selected = selectedFormats.includes(format.id);
                    const Icon = format.icon;
                    return (
                      <button key={format.id} className={`format-tile ${selected ? "is-selected" : ""}`} type="button" onClick={() => toggleFormat(format.id)} aria-pressed={selected}>
                        <Icon size={19} aria-hidden="true" />
                        <span className="format-copy"><strong>{format.name}</strong><small>{format.detail}</small></span>
                        <span className="format-check" aria-hidden="true">{selected ? <Check size={14} /> : null}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="command-bar">
                <div className="command-summary"><span className="eyebrow">Command staged</span><p>{selectedFormatNames.length ? `${selectedFormatNames.join(", ")} selected` : "Select at least one output format"}</p></div>
                <Button className="run-button" type="submit" disabled={runState === "running" || selectedFormats.length === 0}>
                  {runState === "running" ? <><Loader2 size={18} className="spin-icon" /> Executing {progress}%</> : <><Play size={17} fill="currentColor" /> Start extraction</>}
                </Button>
              </div>
            </form>
          </section>

          <aside className="operations-panel" aria-label="Operation state and extraction report">
            <div className="ops-header">
              <div><p className="eyebrow">Live operation</p><h2>{runState === "idle" ? "Awaiting command" : runState === "complete" ? "Run completed" : activeStage.label}</h2></div>
              <button className="icon-button" type="button" aria-label="More operation options"><MoreHorizontal size={19} /></button>
            </div>

            <div className={`operation-visual ${runState !== "idle" ? "is-active" : ""}`}>
              <div className="evidence-header"><span>STATE TRACE // 00:00</span><span>POLICY: BOUNDED</span></div>
              <img src="/manus-storage/wdre-live-operation_2b749371.png" alt="Schematic extraction pipeline trace" />
              <div className="evidence-grid" aria-hidden="true"><span>URL <b>--</b></span><span>PLAN <b>--</b></span><span>PAGES <b>--</b></span><span>ROWS <b>--</b></span></div>
              <div className="operation-visual-label"><span>{runState === "idle" ? "INITIAL STATE" : runState === "complete" ? "OPERATION CLOSED" : "PIPELINE ACTIVE"}</span></div>
            </div>

            <div className="workflow-list" aria-live="polite">
              {workflow.map((stage, index) => {
                const Icon = stage.icon;
                const complete = runState === "complete" || (runState === "running" && index < stageIndex);
                const active = runState === "running" && index === stageIndex;
                return (
                  <div key={stage.id} className={`workflow-step ${complete ? "is-complete" : ""} ${active ? "is-active" : ""}`}>
                    <div className="workflow-node">{complete ? <Check size={14} /> : <Icon size={15} />}</div>
                    <div><strong>{stage.label}</strong><span>{complete ? stage.detail : active ? "In progress" : "Pending"}</span></div>
                    {active && <span className="active-pulse" aria-label="Current stage" />}
                  </div>
                );
              })}
            </div>

            <div className="progress-block">
              <div><span>Pipeline completion</span><strong>{progress}%</strong></div>
              <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
            </div>

            {runState === "idle" ? (
              <div className="empty-report">
                <img src="/manus-storage/wdre-source-capture_e5311d2d.png" alt="Abstract source capture illustration" />
                <div><span className="eyebrow">No command issued</span><p>Source, extraction schema, and output package are required before queueing.</p></div>
              </div>
            ) : runState === "complete" ? (
              <div className="result-report">
                <div className="report-heading"><div><span className="eyebrow">Extraction report</span><h3>Validated dataset</h3></div><button className="reset-link" type="button" onClick={resetRun}>New run <Plus size={14} /></button></div>
                <div className="stats-grid">
                  {resultStats.map((stat) => <div className="stat-cell" key={stat.label}><span>{stat.label}</span><strong>{stat.value}</strong><small>{stat.detail}</small></div>)}
                </div>
                <div className="export-ready">
                  <img src="/manus-storage/wdre-export-artifact_a10c7fc4.png" alt="Abstract data export artifact" />
                  <div><span className="eyebrow">Files ready</span><p>{selectedFormatNames.join(" · ")}</p><button type="button">Review outputs <ArrowRight size={14} /></button></div>
                </div>
              </div>
            ) : (
              <div className="running-note"><Loader2 size={17} className="spin-icon" /><span>Mock progress is advancing through the Phase 0 event model.</span></div>
            )}
          </aside>
        </div>
      </main>
    </div>
  );
}

function Control({ label, description, checked, onChange }: { label: string; description: string; checked: boolean; onChange: (checked: boolean) => void }) {
  return (
    <div className="control-row">
      <div><strong>{label}</strong><span>{description}</span></div>
      <Switch checked={checked} onCheckedChange={onChange} aria-label={label} />
    </div>
  );
}
