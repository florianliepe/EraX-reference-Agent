import { useRef, useState } from "react";
import {
  ArrowRight,
  Check,
  Download,
  FileText,
  LockKeyhole,
  ShieldCheck,
  UploadCloud,
  X,
} from "lucide-react";

const configuredApi = (import.meta.env.VITE_API_URL || "")
  .trim()
  .replace(/\/$/, "");
const isLocalPage = ["localhost", "127.0.0.1"].includes(
  window.location.hostname,
);
const configuredLoopback =
  /^https?:\/\/(?:localhost|127\.0\.0\.1)(?::|\/|$)/i.test(configuredApi);
const API =
  configuredApi && !(configuredLoopback && !isLocalPage)
    ? configuredApi
    : isLocalPage
      ? "http://localhost:8000"
      : "";
const apiConfigurationMessage =
  configuredLoopback && !isLocalPage
    ? "The configured backend URL points to localhost and cannot work from GitHub Pages."
    : "Backend configuration is missing.";
type StatusFile = {
  id: string;
  name: string;
  size: number;
  status: string;
  error?: string;
};
type Evidence = {
  source_file: string;
  snippet: string;
  page_or_sheet?: string;
};
type Section = {
  value: string;
  confidence: "strong" | "weak" | "missing";
  evidence: Evidence[];
  edited: boolean;
};
type Kpi = {
  id?: string;
  name: string;
  value: string;
  confidence: "strong" | "weak" | "missing";
  evidence: Evidence[];
  edited: boolean;
};
type Fields = Record<string, Section>;
const labels: Record<string, string> = {
  title: "Reference title",
  client: "Client",
  date: "Date",
  industry: "Industry",
  service: "Service",
  situation_challenge: "Situation & challenge",
  approach: "Our approach",
  outcome_impact: "Outcome & impact",
};

function App() {
  const [password, setPassword] = useState(
    sessionStorage.getItem("erax-auth") || "",
  );
  const [unlocked, setUnlocked] = useState(false);
  const [files, setFiles] = useState<File[]>([]),
    [statuses, setStatuses] = useState<StatusFile[]>([]);
  const [job, setJob] = useState(""),
    [progress, setProgress] = useState(0),
    [busy, setBusy] = useState(false);
  const [fields, setFields] = useState<Fields | null>(null),
    [kpis, setKpis] = useState<Kpi[]>([]),
    [classification, setClassification] = useState("public"),
    [error, setError] = useState("");
  const [reviewer, setReviewer] = useState(""),
    [reuseAllowed, setReuseAllowed] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const headers = { "X-Pilot-Password": password };
  const choose = (incoming: FileList | File[]) => {
    setFiles((prev) => [...prev, ...Array.from(incoming)]);
    setError("");
  };
  const unlock = async () => {
    if (!API) {
      setError(
        "This pilot deployment is not connected to a backend yet. Configure the VITE_API_URL repository variable with the public HTTPS API URL.",
      );
      return;
    }
    if (!password) {
      setError("Enter the pilot password.");
      return;
    }
    try {
      const r = await fetch(`${API}/auth/check`, { headers });
      if (r.status === 401) {
        setError("That pilot password is not valid.");
        return;
      }
      if (!r.ok) {
        setError(
          `The processing service returned ${r.status}. Try again or contact the pilot owner.`,
        );
        return;
      }
      sessionStorage.setItem("erax-auth", password);
      setUnlocked(true);
      setError("");
    } catch {
      setError(
        `The processing service at ${API} is unavailable. Ask the pilot owner to verify the backend deployment.`,
      );
    }
  };
  async function poll(id: string) {
    const r = await fetch(`${API}/status/${id}`, { headers });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "Could not read job status");
    setStatuses(data.files);
    setProgress(data.progress);
    if (data.status === "completed") {
      const result = await fetch(`${API}/result/${id}`, { headers }).then((x) =>
        x.json(),
      );
      const { kpis: resultKpis = [], ...resultFields } = result.fields;
      setFields(resultFields);
      setKpis(resultKpis);
      setClassification(result.classification);
      setBusy(false);
      return;
    }
    if (data.status === "failed")
      throw new Error(data.error || "Generation failed");
    setTimeout(
      () =>
        poll(id).catch((e) => {
          setError(e.message);
          setBusy(false);
        }),
      800,
    );
  }
  const generate = async () => {
    try {
      setBusy(true);
      setError("");
      setFields(null);
      const form = new FormData();
      files.forEach((file) => form.append("files", file));
      const uploaded = await fetch(`${API}/upload`, {
        method: "POST",
        headers,
        body: form,
      });
      const u = await uploaded.json();
      if (!uploaded.ok) throw new Error(u.detail || "Upload failed");
      setStatuses(u.files);
      const started = await fetch(`${API}/generate/${u.session_id}`, {
        method: "POST",
        headers,
      });
      const s = await started.json();
      if (!started.ok)
        throw new Error(s.detail || "Could not start generation");
      setJob(s.job_id);
      poll(s.job_id).catch((e) => {
        setError(e.message);
        setBusy(false);
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unexpected error");
      setBusy(false);
    }
  };
  const save = async () => {
    if (!fields) return false;
    setBusy(true);
    const values = Object.fromEntries(
      Object.entries(fields).map(([k, v]) => [k, v.value]),
    );
    const r = await fetch(`${API}/result/${job}`, {
      method: "PATCH",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify({
        values,
        kpis: kpis.map(({ id, name, value }) => ({ id, name, value })),
      }),
    });
    if (!r.ok) {
      setError("Could not save edits");
      setBusy(false);
      return false;
    }
    setBusy(false);
    return true;
  };
  const download = async () => {
    if (!reviewer.trim()) {
      setError("Enter the authorized reviewer name before approval.");
      return;
    }
    if (!(await save())) return;
    setBusy(true);
    const approved = await fetch(`${API}/approve/${job}`, {
      method: "POST",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify({
        approved_by: reviewer.trim(),
        reuse_allowed: reuseAllowed,
      }),
    });
    const approval = await approved.json();
    if (!approved.ok) {
      setError(approval.detail || "Approval and knowledge publication failed");
      setBusy(false);
      return;
    }
    const r = await fetch(`${API}/download/${job}`, { headers });
    if (!r.ok) {
      setError("PowerPoint is not ready");
      setBusy(false);
      return;
    }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "Eraneos-client-reference.pptx";
    a.click();
    URL.revokeObjectURL(url);
    setBusy(false);
    if (approval.publication?.error)
      setError(
        `PowerPoint approved, but knowledge publication needs attention: ${approval.publication.error}`,
      );
  };
  if (!unlocked)
    return (
      <main className="gate">
        <div className="gate-card">
          <div className="brand">
            eraneos<span>×</span>
          </div>
          <p className="eyebrow">EraX reference agent</p>
          <h1>Turn project evidence into a client-ready story.</h1>
          <p className="lede">
            A private pilot for creating concise, traceable one-page references.
          </p>
          <label>
            Pilot password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && unlock()}
              autoFocus
            />
          </label>
          <button onClick={unlock} disabled={!API || !password}>
            Enter workspace <ArrowRight size={18} />
          </button>
          {!API && (
            <p className="error">
              {apiConfigurationMessage} The pilot owner must deploy the API and
              set <code>VITE_API_URL</code> to its public HTTPS address.
            </p>
          )}
          {error && <p className="error">{error}</p>}
          <p className="secure">
            <LockKeyhole size={14} /> Shared pilot access · 10 users
          </p>
        </div>
      </main>
    );
  return (
    <div className="shell">
      <header>
        <div className="brand">
          eraneos<span>×</span>
        </div>
        <div className="header-meta">
          <span>Reference agent</span>
          <span className="secure">
            <ShieldCheck size={14} /> Evidence grounded
          </span>
        </div>
      </header>
      <main>
        <section className="hero">
          <div>
            <p className="eyebrow">01 · Build a reference</p>
            <h1>From raw project files to one sharp slide.</h1>
          </div>
          <p>
            Upload your source material. EraX extracts the story, shows its
            evidence, and creates a polished PowerPoint one-pager.
          </p>
        </section>
        <nav className="steps" aria-label="Workflow">
          <span className={files.length ? "done" : "active"}>01 Upload</span>
          <span className={busy ? "active" : fields ? "done" : ""}>
            02 Generate
          </span>
          <span className={fields ? "active" : ""}>03 Review</span>
          <span>04 Download</span>
        </nav>
        {!fields && (
          <section className="workspace">
            <div
              className={`drop ${files.length ? "has-files" : ""}`}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                choose(e.dataTransfer.files);
              }}
              onClick={() => input.current?.click()}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && input.current?.click()}
            >
              <input
                ref={input}
                hidden
                multiple
                type="file"
                accept=".ppt,.pptx,.doc,.docx,.xls,.xlsx,.pdf,.png,.jpg,.jpeg"
                onChange={(e) => e.target.files && choose(e.target.files)}
              />
              <UploadCloud size={34} />
              <h2>Drop project material here</h2>
              <p>
                or choose files · PPTX, DOCX, XLSX, PDF, PNG, JPG · max 25 MB
                each
              </p>
            </div>
            {files.length > 0 && (
              <div className="file-panel">
                <div className="panel-title">
                  <div>
                    <p className="eyebrow">Source set</p>
                    <h2>
                      {files.length} file{files.length > 1 ? "s" : ""} ready
                    </h2>
                  </div>
                  <button
                    className="quiet"
                    onClick={() => {
                      setFiles([]);
                      setStatuses([]);
                    }}
                  >
                    Clear all
                  </button>
                </div>
                <div className="file-list">
                  {files.map((file, i) => {
                    const status = statuses[i]?.status || "uploaded";
                    return (
                      <div className="file" key={`${file.name}-${i}`}>
                        <FileText />
                        <div>
                          <strong>{file.name}</strong>
                          <small>
                            {(file.size / 1024 / 1024).toFixed(1)} MB
                          </small>
                        </div>
                        <span className={`status ${status}`}>
                          {status === "parsed" ? (
                            <Check size={13} />
                          ) : status === "failed" ? (
                            <X size={13} />
                          ) : null}
                          {status}
                        </span>
                      </div>
                    );
                  })}
                </div>
                {busy && (
                  <div className="progress">
                    <div style={{ width: `${progress}%` }} />
                    <span>
                      {progress}% ·{" "}
                      {progress < 50
                        ? "Reading source evidence"
                        : progress < 84
                          ? "Structuring the story"
                          : "Rendering the slide"}
                    </span>
                  </div>
                )}
                <button className="primary" disabled={busy} onClick={generate}>
                  {busy ? "Building your reference…" : "Generate one-pager"}{" "}
                  <ArrowRight size={18} />
                </button>
              </div>
            )}
          </section>
        )}
        {fields && (
          <section className="review">
            <div className="review-head">
              <div>
                <p className="eyebrow">03 · Review the story</p>
                <h2>Every claim stays connected to its source.</h2>
              </div>
              <span className={`classification ${classification}`}>
                {classification}
              </span>
            </div>
            <div className="review-grid">
              <div>
                <div className="fields">
                  {Object.entries(fields).map(([key, section]) => (
                    <article className="field" key={key}>
                      <div className="field-head">
                        <label htmlFor={key}>{labels[key]}</label>
                        <span className={`confidence ${section.confidence}`}>
                          {section.confidence}
                        </span>
                      </div>
                      <textarea
                        id={key}
                        rows={
                          [
                            "title",
                            "client",
                            "date",
                            "industry",
                            "service",
                          ].includes(key)
                            ? 2
                            : 5
                        }
                        value={section.value}
                        onChange={(e) =>
                          setFields({
                            ...fields,
                            [key]: {
                              ...section,
                              value: e.target.value,
                              edited: true,
                            },
                          })
                        }
                      />
                    </article>
                  ))}
                </div>
                <section className="kpi-editor">
                  <div className="kpi-title">
                    <div>
                      <p className="eyebrow">Project KPIs</p>
                      <h3>Verified metrics included in the Impact summary</h3>
                    </div>
                    <button
                      className="quiet"
                      onClick={() =>
                        setKpis([
                          ...kpis,
                          {
                            name: "",
                            value: "",
                            confidence: "weak",
                            evidence: [],
                            edited: true,
                          },
                        ])
                      }
                    >
                      Add KPI
                    </button>
                  </div>
                  {kpis.length === 0 ? (
                    <p className="missing-copy">
                      No quantified KPI was found in the uploaded evidence.
                      Nothing will be invented.
                    </p>
                  ) : (
                    kpis.map((kpi, index) => (
                      <article className="kpi-row" key={index}>
                        <input
                          aria-label={`KPI ${index + 1} name`}
                          placeholder="KPI name"
                          value={kpi.name}
                          onChange={(e) =>
                            setKpis(
                              kpis.map((item, i) =>
                                i === index
                                  ? {
                                      ...item,
                                      name: e.target.value,
                                      edited: true,
                                    }
                                  : item,
                              ),
                            )
                          }
                        />
                        <input
                          aria-label={`KPI ${index + 1} value`}
                          placeholder="Value"
                          value={kpi.value}
                          onChange={(e) =>
                            setKpis(
                              kpis.map((item, i) =>
                                i === index
                                  ? {
                                      ...item,
                                      value: e.target.value,
                                      edited: true,
                                    }
                                  : item,
                              ),
                            )
                          }
                        />
                        <span className={`confidence ${kpi.confidence}`}>
                          {kpi.confidence}
                        </span>
                        <button
                          className="remove-kpi"
                          aria-label={`Remove KPI ${index + 1}`}
                          onClick={() =>
                            setKpis(kpis.filter((_, i) => i !== index))
                          }
                        >
                          ×
                        </button>
                        {kpi.evidence.length > 0 && (
                          <small>
                            {kpi.evidence[0].source_file}
                            {kpi.evidence[0].page_or_sheet
                              ? ` · ${kpi.evidence[0].page_or_sheet}`
                              : ""}
                          </small>
                        )}
                      </article>
                    ))
                  )}
                </section>
                <section className="approval-panel">
                  <p className="eyebrow">Human approval</p>
                  <label>
                    Authorized reviewer
                    <input
                      value={reviewer}
                      onChange={(event) => setReviewer(event.target.value)}
                      placeholder="Name"
                    />
                  </label>
                  <label className="reuse">
                    <input
                      type="checkbox"
                      checked={reuseAllowed}
                      onChange={(event) => setReuseAllowed(event.target.checked)}
                    />
                    Allow these approved claims to be reused across authorized
                    projects
                  </label>
                  <p>
                    Approval publishes an auditable JSON-LD knowledge bundle.
                    Cross-project reuse remains opt-in.
                  </p>
                </section>
              </div>
              <aside>
                <p className="eyebrow">Why this text</p>
                {Object.entries(fields).map(([key, section]) => (
                  <details key={key} open={key === "outcome_impact"}>
                    <summary>
                      <span className={`dot ${section.confidence}`} />
                      {labels[key]}
                      <span>{section.evidence.length}</span>
                    </summary>
                    {section.evidence.length ? (
                      section.evidence.map((ev, i) => (
                        <blockquote key={i}>
                          <p>“{ev.snippet}”</p>
                          <cite>
                            {ev.source_file}
                            {ev.page_or_sheet ? ` · ${ev.page_or_sheet}` : ""}
                          </cite>
                        </blockquote>
                      ))
                    ) : (
                      <p className="missing-copy">
                        No supporting source was found. Add verified wording or
                        leave the evidence warning in place.
                      </p>
                    )}
                  </details>
                ))}
                {kpis.map((kpi, index) => (
                  <details key={`kpi-${index}`}>
                    <summary>
                      <span className={`dot ${kpi.confidence}`} />
                      {kpi.name || `KPI ${index + 1}`}
                      <span>{kpi.evidence.length}</span>
                    </summary>
                    {kpi.evidence.map((ev, i) => (
                      <blockquote key={i}>
                        <p>“{ev.snippet}”</p>
                        <cite>
                          {ev.source_file}
                          {ev.page_or_sheet ? ` · ${ev.page_or_sheet}` : ""}
                        </cite>
                      </blockquote>
                    ))}
                  </details>
                ))}
              </aside>
            </div>
            <div className="actions">
              <button
                className="quiet"
                onClick={() => {
                  setFields(null);
                  setKpis([]);
                  setFiles([]);
                  setStatuses([]);
                  setProgress(0);
                  setReviewer("");
                  setReuseAllowed(false);
                }}
              >
                Start another
              </button>
              <button
                className="primary"
                onClick={download}
                disabled={busy || !reviewer.trim()}
              >
                <Download size={18} /> Approve & download PPT
              </button>
            </div>
          </section>
        )}
        {error && (
          <div className="toast">
            <X size={17} />
            <span>{error}</span>
            <button onClick={() => setError("")}>Dismiss</button>
          </div>
        )}
      </main>
      <footer>
        <span>EraX · Reference intelligence</span>
        <span>Pilot workspace · Files are processed server-side</span>
      </footer>
    </div>
  );
}
export default App;
