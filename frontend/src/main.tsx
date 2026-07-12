import React from "react";
import ReactDOM from "react-dom/client";
import {
  Activity,
  BadgeCheck,
  Clock3,
  Database,
  FileType2,
  FileSearch,
  Gauge,
  KeyRound,
  Loader2,
  Lock,
  LogOut,
  MessageSquareText,
  RefreshCw,
  Search,
  ShieldCheck,
  UploadCloud,
  UserRoundCheck
} from "lucide-react";
import "./styles.css";
import { AuthProvider, useAuth } from "./auth/AuthProvider";
import { apiFetch, ApiAuthError } from "./api";

type IngestResult = {
  document_id: string;
  file_name: string;
  chunks_created: number;
  ocr_used: boolean;
  extraction_warnings: string[];
};

type Citation = {
  document_id?: string;
  file_name?: string;
  section_title?: string | null;
  chunk_index: number;
  score: number;
  ocr_used: boolean;
};

type QueryResult = {
  answer: string;
  cached: boolean;
  citations: Citation[];
  metrics: {
    retrieval_ms?: number;
    total_ms?: number;
    contexts_used?: number;
  };
};

const DEFAULT_INGEST_PATH = "/data/ingest/sample.docx";
const roleOptions = ["admin", "finance", "engineering", "legal", "support"];

function LoginScreen() {
  const { login } = useAuth();
  const [busy, setBusy] = React.useState(false);

  return (
    <main className="app-shell login-shell">
      <section className="panel login-card">
        <div className="brand">
          <div className="brand-mark">
            <Database size={20} />
          </div>
          <div>
            <h1>RAG Console</h1>
            <span>Sign in required</span>
          </div>
        </div>
        <p>
          This workspace is authenticated through Keycloak (OIDC / Authorization Code + PKCE).
          Your tenant and roles are resolved from your account -- there is no manual tenant or
          role selector.
        </p>
        <button
          className="primary-action"
          type="button"
          disabled={busy}
          onClick={() => {
            setBusy(true);
            login();
          }}
        >
          {busy ? <Loader2 className="spin" size={18} /> : <KeyRound size={18} />}
          Sign in with Keycloak
        </button>
      </section>
    </main>
  );
}

function AuthenticatedApp() {
  const { user, logout } = useAuth();
  const tenantId = user?.tenant_id ?? "unknown";
  const memberRoles = user?.realm_access?.roles ?? [];

  const [localPath, setLocalPath] = React.useState(DEFAULT_INGEST_PATH);
  const [selectedFile, setSelectedFile] = React.useState<File | null>(null);
  const [visibility, setVisibility] = React.useState("tenant");
  const [allowedRoles, setAllowedRoles] = React.useState<string[]>(["finance"]);
  const [forceOcr, setForceOcr] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [topK, setTopK] = React.useState(5);
  const [ingests, setIngests] = React.useState<IngestResult[]>([]);
  const [result, setResult] = React.useState<QueryResult | null>(null);
  const [status, setStatus] = React.useState("Idle");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");

  const toggleAllowedRole = (role: string) => {
    setAllowedRoles((values) =>
      values.includes(role) ? values.filter((item) => item !== role) : [...values, role]
    );
  };

  const handleAuthError = (caught: unknown) => {
    if (caught instanceof ApiAuthError) {
      setError(caught.message);
      setStatus("Needs attention");
      return true;
    }
    return false;
  };

  const ingestDocument = async () => {
    setBusy(true);
    setError("");
    setStatus("Ingesting");
    try {
      const response = await apiFetch("/api/v1/documents/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          local_path: localPath,
          visibility,
          allowed_role_names: visibility === "role" ? allowedRoles : [],
          force_ocr: forceOcr
        })
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const payload = (await response.json()) as IngestResult;
      setIngests((items) => [payload, ...items]);
      setStatus("Indexed");
    } catch (caught) {
      if (!handleAuthError(caught)) {
        setError(caught instanceof Error ? caught.message : "Document ingest failed");
        setStatus("Needs attention");
      }
    } finally {
      setBusy(false);
    }
  };

  const uploadDocument = async () => {
    if (!selectedFile) {
      return;
    }
    setBusy(true);
    setError("");
    setStatus("Uploading");
    try {
      const form = new FormData();
      form.append("visibility", visibility);
      if (visibility === "role") {
        allowedRoles.forEach((role) => form.append("allowed_role_names", role));
      }
      form.append("force_ocr", String(forceOcr));
      form.append("file", selectedFile);

      const response = await apiFetch("/api/v1/documents/upload", {
        method: "POST",
        body: form
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const payload = (await response.json()) as IngestResult;
      setIngests((items) => [payload, ...items]);
      setStatus("Indexed");
    } catch (caught) {
      if (!handleAuthError(caught)) {
        setError(caught instanceof Error ? caught.message : "Document upload failed");
        setStatus("Needs attention");
      }
    } finally {
      setBusy(false);
    }
  };

  const askQuestion = async () => {
    setBusy(true);
    setError("");
    setStatus("Retrieving");
    try {
      const response = await apiFetch("/api/v1/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          top_k: topK
        })
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const payload = (await response.json()) as QueryResult;
      setResult(payload);
      setStatus(payload.cached ? "Cache hit" : "Answered");
    } catch (caught) {
      if (!handleAuthError(caught)) {
        setError(caught instanceof Error ? caught.message : "Query failed");
        setStatus("Needs attention");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Database size={20} />
          </div>
          <div>
            <h1>RAG Console</h1>
            <span>Week 3 UI</span>
          </div>
        </div>
        <nav className="nav-list" aria-label="Primary">
          <a className="nav-item active" href="#workspace">
            <MessageSquareText size={18} /> Workspace
          </a>
          <a className="nav-item" href="#documents">
            <FileSearch size={18} /> Documents
          </a>
          <a className="nav-item" href="#access">
            <ShieldCheck size={18} /> A&amp;A
          </a>
          <a className="nav-item" href="#sessions">
            <Clock3 size={18} /> Sessions
          </a>
          <a className="nav-item" href="#metrics">
            <Gauge size={18} /> Metrics
          </a>
        </nav>
        <button className="secondary-action logout-button" type="button" onClick={logout}>
          <LogOut size={16} /> Sign out
        </button>
        <div className="sidebar-footer">
          <Lock size={16} />
          <span>RBAC enforced before retrieval</span>
        </div>
      </aside>

      <section className="workspace" id="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">SaaS RAG Operations</p>
            <h2>Document ingestion and precision query workspace</h2>
          </div>
          <div className={`status-pill ${status === "Needs attention" ? "danger" : ""}`}>
            {busy ? <Loader2 className="spin" size={16} /> : <Activity size={16} />}
            <span>{status}</span>
          </div>
        </header>

        <section className="metrics-row" id="metrics">
          <Metric label="TTFT Target" value="<800 ms" icon={<Gauge size={18} />} />
          <Metric
            label="Retrieval"
            value={`${result?.metrics.retrieval_ms ?? 0} ms`}
            icon={<Search size={18} />}
          />
          <Metric
            label="Total"
            value={`${result?.metrics.total_ms ?? 0} ms`}
            icon={<Activity size={18} />}
          />
          <Metric
            label="Cache"
            value={result?.cached ? "Hit" : "Ready"}
            icon={<RefreshCw size={18} />}
          />
        </section>

        {error ? <div className="error-banner">{error}</div> : null}

        <div className="content-grid">
          <section className="panel" id="documents">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Ingestion</p>
                <h3>Document intake</h3>
              </div>
              <UploadCloud size={20} />
            </div>

            <label className="field">
              <span>Local document path</span>
              <input
                placeholder="/data/ingest/policy.docx"
                value={localPath}
                onChange={(event) => setLocalPath(event.target.value)}
              />
              <small className="field-help">
                Docker can read files mounted into the backend. Put Mac files in
                `work/rag-saas-docs-ingestion-poc/data/ingest`, then use `/data/ingest/file-name`.
                Supports PDF, Word DOCX, Excel XLSX, PowerPoint PPTX, text, CSV, markdown, and images.
              </small>
            </label>

            <label className="field file-field">
              <span>Upload file: PDF, Word, Excel, PowerPoint, text, image</span>
              <input
                type="file"
                accept=".pdf,.txt,.md,.csv,.tsv,.docx,.xlsx,.pptx,.png,.jpg,.jpeg,.tiff,.bmp"
                onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
              />
              <small className="field-help">
                Best for files from your Mac or another machine. The browser sends the file to the
                backend, so no Docker path mapping is needed.
              </small>
            </label>

            <div className="segmented" role="group" aria-label="Document visibility">
              {["tenant", "role", "private"].map((item) => (
                <button
                  key={item}
                  className={visibility === item ? "selected" : ""}
                  onClick={() => setVisibility(item)}
                  type="button"
                >
                  {item}
                </button>
              ))}
            </div>

            {visibility === "role" ? (
              <RolePicker
                title="Allowed roles"
                values={allowedRoles}
                onToggle={toggleAllowedRole}
              />
            ) : null}

            <label className="toggle">
              <input
                type="checkbox"
                checked={forceOcr}
                onChange={(event) => setForceOcr(event.target.checked)}
              />
              <span>Force OCR</span>
            </label>

            <button
              className="primary-action"
              type="button"
              disabled={busy || !selectedFile}
              onClick={uploadDocument}
            >
              <UploadCloud size={18} />
              Upload and ingest
            </button>

            <button
              className="secondary-action"
              type="button"
              disabled={busy || !localPath.trim()}
              onClick={ingestDocument}
            >
              <UploadCloud size={18} />
              Ingest mounted path
            </button>

            <div className="document-list">
              {ingests.map((item) => (
                <article className="document-card" key={item.document_id}>
                  <div>
                    <strong>{item.file_name}</strong>
                    <span>{item.chunks_created} chunks</span>
                  </div>
                  {item.ocr_used ? <Badge label="OCR" /> : <Badge label="Text" />}
                </article>
              ))}
            </div>
          </section>

          <section className="panel query-panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Query</p>
                <h3>Ask authorized knowledge</h3>
              </div>
              <MessageSquareText size={20} />
            </div>

            <div className="status-list">
              <StatusItem label="Asking as" value={user?.preferred_username ?? "unknown"} />
              <StatusItem label="Your roles" value={memberRoles.join(", ") || "none"} />
            </div>

            <label className="field">
              <span>Top K contexts: {topK}</span>
              <input
                type="range"
                min="1"
                max="10"
                value={topK}
                onChange={(event) => setTopK(Number(event.target.value))}
              />
            </label>

            <label className="field question-field">
              <span>Question</span>
              <textarea
                placeholder="Ask about a policy, contract, support article, or financial document..."
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>

            <button
              className="primary-action"
              type="button"
              disabled={busy || !query.trim()}
              onClick={askQuestion}
            >
              <Search size={18} />
              Retrieve answer
            </button>

            <article className="answer-surface">
              <div className="answer-header">
                <KeyRound size={18} />
                <span>{result?.cached ? "Cached answer" : "Latest answer"}</span>
              </div>
              <p>
                {result?.answer ??
                  "Ingest a document, then ask a question. Your roles decide what you can see."}
              </p>
            </article>
          </section>

          <section className="panel citations-panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Evidence</p>
                <h3>Citations</h3>
              </div>
              <BadgeCheck size={20} />
            </div>

            <div className="citation-list">
              {(result?.citations ?? []).map((citation) => (
                <article className="citation-card" key={`${citation.document_id}-${citation.chunk_index}`}>
                  <div className="citation-score">{Math.round(citation.score * 100)}%</div>
                  <div>
                    <strong>{citation.file_name ?? "Unknown file"}</strong>
                    <span>Chunk {citation.chunk_index}</span>
                    <small>{citation.ocr_used ? "OCR source" : "Native text"}</small>
                  </div>
                </article>
              ))}
              {!result?.citations?.length ? (
                <div className="empty-state">No citations yet.</div>
              ) : null}
            </div>
          </section>
        </div>

        <div className="ops-grid">
          <section className="panel" id="access">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Authentication &amp; Authorization</p>
                <h3>A&amp;A control surface</h3>
              </div>
              <UserRoundCheck size={20} />
            </div>
            <div className="status-list">
              <StatusItem label="Identity provider" value="Keycloak OIDC/JWT" />
              <StatusItem label="Signed in as" value={user?.preferred_username ?? "unknown"} />
              <StatusItem label="Tenant isolation" value={tenantId.slice(0, 8) + "..."} />
              <StatusItem label="Member roles" value={memberRoles.join(", ") || "none"} />
              <StatusItem label="Enforcement point" value="server-side, before retrieval ranking" />
            </div>
          </section>

          <section className="panel" id="sessions">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Session Management</p>
                <h3>Current session</h3>
              </div>
              <Clock3 size={20} />
            </div>
            <div className="status-list">
              <StatusItem label="Session mode" value="Stateless JWT (Keycloak-issued)" />
              <StatusItem label="Token status" value="Valid -- silently refreshed" />
              <StatusItem label="Cache scope" value={result?.cached ? "Redis hit" : "Redis ready"} />
              <StatusItem label="Last workflow status" value={status} />
              <StatusItem label="Audit trail" value="document.ingested events in Postgres" />
            </div>
          </section>

          <section className="panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Document Formats</p>
                <h3>Supported intake</h3>
              </div>
              <FileType2 size={20} />
            </div>
            <div className="format-grid">
              {["PDF", "Word DOCX", "Excel XLSX", "PowerPoint PPTX", "TXT/MD/CSV", "Images + OCR"].map(
                (format) => (
                  <Badge key={format} label={format} />
                )
              )}
            </div>
          </section>
        </div>
      </section>
    </main>
  );
}

function Metric({ label, value, icon }: { label: string; value: string; icon: React.ReactNode }) {
  return (
    <article className="metric">
      <div>{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function Badge({ label }: { label: string }) {
  return <span className="badge">{label}</span>;
}

function StatusItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="status-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function RolePicker({
  title,
  values,
  onToggle
}: {
  title: string;
  values: string[];
  onToggle: (role: string) => void;
}) {
  return (
    <fieldset className="role-picker" id="access">
      <legend>{title}</legend>
      <div>
        {roleOptions.map((role) => (
          <label key={role} className={values.includes(role) ? "role-chip selected" : "role-chip"}>
            <input
              type="checkbox"
              checked={values.includes(role)}
              onChange={() => onToggle(role)}
            />
            {role}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function App() {
  const { status } = useAuth();

  if (status === "loading") {
    return (
      <main className="app-shell login-shell">
        <Loader2 className="spin" size={32} />
      </main>
    );
  }

  if (status === "unauthenticated") {
    return <LoginScreen />;
  }

  return <AuthenticatedApp />;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </React.StrictMode>
);
