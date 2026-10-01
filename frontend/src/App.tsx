import { useEffect, useState } from "react";
import { api, type Answer, type Doc, type DocState, type Requirement, type ReviewedRequirement } from "./api";

type Tab = "ask" | "insights" | "requirements" | "ground-truth";
type Runner = <T>(label: string, fn: () => Promise<T>) => Promise<T | undefined>;

const STAGES: [string, string][] = [
  ["insights.json", "Insights"],
  ["requirements.json", "Extracted"],
  ["review.json", "Council reviewed"],
  ["highlighted.pdf", "Highlighted"],
  ["comparison.json", "Compared"],
];

export default function App() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [state, setState] = useState<DocState | null>(null);
  const [tab, setTab] = useState<Tab>("ask");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = () => api.listDocuments().then(setDocs).catch((e) => setError(e.message));
  useEffect(() => void refresh(), []);

  // Restore everything previously produced for the selected document.
  const reload = (docId = selected) => (docId ? api.state(docId).then(setState) : Promise.resolve(setState(null)));
  useEffect(() => {
    reload().catch((e) => setError(e.message));
  }, [selected]);

  const run: Runner = async (label, fn) => {
    setBusy(label);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  async function upload(file: File) {
    const doc = await run(`Indexing ${file.name}…`, () => api.upload(file));
    if (doc) {
      await refresh();
      setSelected(doc.doc_id);
    }
  }

  async function remove(docId: string) {
    await run("Deleting…", () => api.remove(docId));
    if (selected === docId) setSelected("");
    await refresh();
  }

  async function stage(label: string, fn: () => Promise<unknown>) {
    await run(label, fn);
    await reload();
  }

  const doc = docs.find((d) => d.doc_id === selected);

  return (
    <div className="layout">
      <aside>
        <h1>Document Intelligence</h1>
        <label className="upload">
          Upload PDF
          <input
            type="file"
            accept="application/pdf"
            hidden
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) upload(file);
              e.target.value = "";
            }}
          />
        </label>
        <ul className="docs">
          <li className={selected === "" ? "active" : ""} onClick={() => setSelected("")}>
            All documents
          </li>
          {docs.map((d) => (
            <li key={d.doc_id} className={selected === d.doc_id ? "active" : ""} onClick={() => setSelected(d.doc_id)}>
              <span>{d.name}</span>
              <button
                className="icon"
                title="Delete"
                onClick={(e) => {
                  e.stopPropagation();
                  remove(d.doc_id);
                }}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <main>
        {doc && state && (
          <div className="pipeline">
            <div className="stages">
              {STAGES.map(([file, label]) => (
                <span key={file} className={state.manifest[file] ? "stage done" : "stage"} title={state.manifest[file] ?? "not run"}>
                  {state.manifest[file] ? "✓ " : ""}
                  {label}
                </span>
              ))}
            </div>
            <button
              className="primary"
              disabled={!!busy}
              onClick={() => stage("Running full pipeline (insights → extract → council → highlight)…", () => api.pipeline(doc.doc_id))}
            >
              Run full pipeline
            </button>
          </div>
        )}
        <nav className="tabs">
          {(["ask", "insights", "requirements", "ground-truth"] as Tab[]).map((t) => (
            <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
              {t === "ground-truth" ? "Ground truth" : t[0].toUpperCase() + t.slice(1)}
            </button>
          ))}
        </nav>
        {busy && <p className="status">{busy}</p>}
        {error && <p className="status error">{error}</p>}

        {tab === "ask" && <AskPanel docId={selected} run={run} disabled={!!busy} />}
        {tab !== "ask" && !doc && <p className="hint">Select a document on the left.</p>}
        {tab === "insights" && doc && state && (
          <InsightsPanel state={state} disabled={!!busy} onRun={() => stage("Analysing document…", () => api.insights(doc.doc_id))} />
        )}
        {tab === "requirements" && doc && state && (
          <RequirementsPanel doc={doc} state={state} disabled={!!busy} stage={stage} />
        )}
        {tab === "ground-truth" && doc && state && (
          <GroundTruthPanel
            state={state}
            disabled={!!busy}
            onUpload={(file) => stage("Comparing with ground truth…", () => api.groundTruth(doc.doc_id, file))}
          />
        )}
      </main>
    </div>
  );
}

function AskPanel({ docId, run, disabled }: { docId: string; run: Runner; disabled: boolean }) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<Answer | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    const answer = await run("Thinking…", () => api.ask(question, docId));
    if (answer) setResult(answer);
  }

  return (
    <section>
      <form className="ask" onSubmit={submit}>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={docId ? "Ask about this document…" : "Ask a question across all documents…"}
        />
        <button disabled={disabled}>Ask</button>
      </form>
      {result && (
        <>
          <p className="answer">{result.answer}</p>
          <h3>Sources</h3>
          {result.sources.map((s) => (
            <details key={s.ref} className={s.cited ? "source cited" : "source"}>
              <summary>
                [{s.ref}] {s.doc_name} · page {s.page} · score {s.score.toFixed(2)}
                {s.cited && <span className="badge">cited</span>}
              </summary>
              <p>{s.text}</p>
            </details>
          ))}
        </>
      )}
    </section>
  );
}

function InsightsPanel({ state, disabled, onRun }: { state: DocState; disabled: boolean; onRun: () => void }) {
  const ins = state.insights;
  return (
    <section>
      <div className="toolbar">
        <button onClick={onRun} disabled={disabled}>
          {ins ? "Re-run insights" : "Generate insights"}
        </button>
      </div>
      {ins && (
        <>
          <p className="answer">
            <strong>{ins.document_type}</strong>
            <br />
            {ins.summary}
          </p>
          <div className="grid">
            <Card title="Parties" items={ins.parties.map((p) => `${p.name} — ${p.role}`)} />
            <Card title="Key dates" items={ins.key_dates.map((d) => `${d.date}: ${d.description} (p.${d.page})`)} />
            <Card title="Obligations" items={ins.obligations.map((o) => `${o.party}: ${o.description} (p.${o.page})`)} />
            <Card title="Risks" items={ins.risks.map((r) => `${r.description} (p.${r.page})`)} />
          </div>
        </>
      )}
    </section>
  );
}

function Card({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="card">
      <h3>{title}</h3>
      {items.length ? (
        <ul>
          {items.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="hint">None found.</p>
      )}
    </div>
  );
}

function toCsv(rows: (Requirement | ReviewedRequirement)[]): string {
  const esc = (v: string | number) => `"${String(v).replace(/"/g, '""')}"`;
  const header = ["id", "page", "section", "priority", "category", "status", "text", "original_text"];
  const body = rows.map((r) => {
    const rev = r as ReviewedRequirement;
    return [r.id, r.page, r.section, r.priority, r.category, rev.status ?? "", r.text, rev.original_text ?? ""];
  });
  return [header, ...body].map((row) => row.map(esc).join(",")).join("\n");
}

function RequirementsPanel({
  doc,
  state,
  disabled,
  stage,
}: {
  doc: Doc;
  state: DocState;
  disabled: boolean;
  stage: (label: string, fn: () => Promise<unknown>) => Promise<void>;
}) {
  const rows: (Requirement | ReviewedRequirement)[] = state.review ?? state.requirements ?? [];
  const reviewed = !!state.review;
  const found = new Map((state.highlight ?? []).map((h) => [h.id, h.found]));

  function download() {
    const url = URL.createObjectURL(new Blob([toCsv(rows)], { type: "text/csv" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: `${doc.name}.requirements.csv` });
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section>
      <div className="toolbar">
        <button onClick={() => stage("Extracting requirements…", () => api.requirements(doc.doc_id))} disabled={disabled}>
          1. Extract
        </button>
        <button
          onClick={() => stage("Council reviewing requirements…", () => api.review(doc.doc_id))}
          disabled={disabled || !state.requirements}
        >
          2. Council review
        </button>
        <button
          onClick={() => stage("Highlighting PDF…", () => api.highlight(doc.doc_id))}
          disabled={disabled || !state.requirements}
        >
          3. Highlight PDF
        </button>
        {state.manifest["highlighted.pdf"] && (
          <a className="button" href={api.fileUrl(doc.doc_id, "highlighted.pdf")} target="_blank" rel="noreferrer">
            Open highlighted PDF
          </a>
        )}
        {rows.length > 0 && <button onClick={download}>Download CSV</button>}
      </div>
      {reviewed && <p className="hint">{summarise(state.review!)}</p>}
      {rows.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Page</th>
              <th>Section</th>
              <th>Priority</th>
              {reviewed && <th>Council</th>}
              <th>Requirement</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const rev = r as ReviewedRequirement;
              return (
                <tr key={r.id} className={rev.status === "rejected" ? "rejected" : ""}>
                  <td>
                    {r.id}
                    {found.get(r.id) === false && <span title="Not located in PDF"> ⚠</span>}
                  </td>
                  <td>{r.page}</td>
                  <td>{r.section}</td>
                  <td>
                    <span className={`badge ${r.priority}`}>{r.priority}</span>
                  </td>
                  {reviewed && (
                    <td title={rev.votes.map((v) => `${v.model}: ${v.verdict}${v.issue ? ` — ${v.issue}` : ""}`).join("\n")}>
                      <span className={`badge status-${rev.status}`}>{rev.status}</span>
                    </td>
                  )}
                  <td>
                    {r.text}
                    {rev.status === "revised" && <div className="was">was: {rev.original_text}</div>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}

function summarise(review: ReviewedRequirement[]): string {
  const count = (s: string) => review.filter((r) => r.status === s).length;
  return `Council: ${count("accepted")} accepted · ${count("revised")} revised · ${count("rejected")} rejected. Hover a status to see each model's vote.`;
}

function GroundTruthPanel({ state, disabled, onUpload }: { state: DocState; disabled: boolean; onUpload: (f: File) => void }) {
  const cmp = state.comparison;
  return (
    <section>
      <p className="hint">
        Upload the business-approved requirement list (CSV or XLSX with a header row; the "Requirement" column is used). It is
        compared with the council-reviewed requirements, or the raw extraction if no review has run.
      </p>
      <div className="toolbar">
        <label className={`button ${disabled || !state.requirements ? "disabled" : ""}`}>
          Upload ground truth
          <input
            type="file"
            accept=".csv,.xlsx"
            hidden
            disabled={disabled || !state.requirements}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) onUpload(file);
              e.target.value = "";
            }}
          />
        </label>
      </div>
      {!state.requirements && <p className="hint">Extract requirements first.</p>}
      {cmp && (
        <>
          <div className="metrics">
            {(["precision", "recall", "f1"] as const).map((k) => (
              <div key={k} className="metric">
                <span>{k === "f1" ? "F1" : k[0].toUpperCase() + k.slice(1)}</span>
                <strong>{cmp.summary[k].toFixed(3)}</strong>
              </div>
            ))}
            <div className="metric">
              <span>Matched</span>
              <strong>
                {cmp.summary.matched} / {cmp.summary.ground_truth}
              </strong>
            </div>
          </div>
          <h3>Missed ({cmp.missed.length})</h3>
          {cmp.missed.length ? <ul>{cmp.missed.map((m, i) => <li key={i}>{m}</li>)}</ul> : <p className="hint">None.</p>}
          <h3>Extra ({cmp.extra.length})</h3>
          {cmp.extra.length ? (
            <ul>{cmp.extra.map((e) => <li key={e.id}>{e.id} (p.{e.page}): {e.text}</li>)}</ul>
          ) : (
            <p className="hint">None.</p>
          )}
          <h3>Matches ({cmp.matches.length})</h3>
          <table>
            <thead>
              <tr>
                <th>Ground truth</th>
                <th>Generated</th>
                <th>Similarity</th>
              </tr>
            </thead>
            <tbody>
              {cmp.matches.map((m) => (
                <tr key={m.id}>
                  <td>{m.truth}</td>
                  <td>
                    {m.id}: {m.text}
                  </td>
                  <td>{m.similarity.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
