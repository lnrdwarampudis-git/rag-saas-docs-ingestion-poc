import React from "react";
import ReactDOM from "react-dom/client";
import {
  Activity,
  AlertTriangle,
  BadgeCheck,
  Clock3,
  Cpu,
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
  RotateCcw,
  Search,
  ShieldCheck,
  UploadCloud,
  UserRoundCheck
} from "lucide-react";
import "./styles.css";
import { AuthProvider, useAuth } from "./auth/AuthProvider";
import { apiFetch, ApiAuthError } from "./api";

const MAX_UPLOAD_BYTES = 536_870_912;
const ALLOWED_UPLOAD_EXTENSIONS = [
  ".pdf",
  ".txt",
  ".md",
  ".csv",
  ".tsv",
  ".docx",
  ".xlsx",
  ".pptx",
  ".png",
  ".jpg",
  ".jpeg",
  ".tiff",
  ".bmp"
];

type IngestResult = {
  document_id: string;
  file_name: string;
  chunks_created: number;
  ocr_used: boolean;
  extraction_warnings?: string[];
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
    top_score?: number;
    retrieval_min_score?: number;
    retrieval_min_keyword_overlap?: number;
    llm_provider?: string;
    local_llm_runtime?: string;
    embedding_provider?: string;
    local_embedding_runtime?: string;
    embedding_model?: string;
    answer_model?: string;
  };
};

type ManagedDocument = {
  document_id: string;
  tenant_id: string;
  file_name: string;
  status: string;
  visibility: string;
  allowed_role_names: string[];
  chunks_created: number;
  ocr_used: boolean;
  byte_size?: number | null;
  mime_type?: string | null;
  uploaded_by?: string | null;
  extraction_warnings: string[];
  created_at?: string | null;
  updated_at?: string | null;
  latest_audit_action?: string | null;
};

type ManagedDocumentDetail = ManagedDocument & {
  chunks: Array<{
    chunk_index: number;
    text: string;
    token_count: number;
    metadata: Record<string, unknown>;
  }>;
};

type ProcessingJobStatus = {
  job_id: string;
  document_id: string;
  file_name: string;
  status: string;
  stage: string;
  attempts: number;
  error_message?: string | null;
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
};

type ModelRuntimeStatus = {
  provider: string;
  runtime: string;
  model_name: string;
  ready: boolean;
  message: string;
  base_url?: string | null;
};

type ModelStatus = {
  llm_provider: string;
  embedding_provider: string;
  embedding: ModelRuntimeStatus;
  answer: ModelRuntimeStatus;
};

type EvaluationReport = {
  summary: {
    cases: number;
    passed: number;
    failed: number;
    context_precision: number;
    context_recall: number;
    answer_relevance: number;
    targets: Record<string, number>;
  };
  results: Array<{
    case_id: string;
    passed: boolean;
    context_precision: number;
    context_recall: number;
    answer_relevance: number;
    retrieved_document_ids: string[];
    expected_document_ids: string[];
    answer: string;
  }>;
};

type AnalyticsReport = {
  documents: {
    total: number;
    embedded: number;
    pending: number;
    failed: number;
    chunks: number;
    ocr_documents: number;
  };
  jobs: {
    total: number;
    queued: number;
    processing: number;
    completed: number;
    failed: number;
    recent_failures: string[];
  };
  queries: {
    total: number;
    cache_hits: number;
    cache_misses: number;
    cache_hit_rate: number;
    average_retrieval_ms: number;
    average_total_ms: number;
  };
  evaluation: {
    cases: number;
    passed: number;
    failed: number;
    context_precision: number;
    context_recall: number;
    answer_relevance: number;
  };
  recent_events: Array<{
    action: string;
    resource_type: string;
    resource_id: string | null;
    actor: string | null;
    metadata: Record<string, unknown>;
    created_at: string;
  }>;
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
  const [processingJobs, setProcessingJobs] = React.useState<ProcessingJobStatus[]>([]);
  const [documents, setDocuments] = React.useState<ManagedDocument[]>([]);
  const [selectedDocument, setSelectedDocument] = React.useState<ManagedDocumentDetail | null>(null);
  const [modelStatus, setModelStatus] = React.useState<ModelStatus | null>(null);
  const [evaluationReport, setEvaluationReport] = React.useState<EvaluationReport | null>(null);
  const [analyticsReport, setAnalyticsReport] = React.useState<AnalyticsReport | null>(null);
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

  const loadDocuments = React.useCallback(async () => {
    try {
      const response = await apiFetch("/api/v1/documents");
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const payload = (await response.json()) as { documents: ManagedDocument[] };
      setDocuments(payload.documents);
    } catch (caught) {
      if (!handleAuthError(caught)) {
        setError(caught instanceof Error ? caught.message : "Document list failed");
        setStatus("Needs attention");
      }
    }
  }, []);

  const loadModelStatus = React.useCallback(async () => {
    try {
      const response = await apiFetch("/api/v1/model-status");
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const payload = (await response.json()) as ModelStatus;
      setModelStatus(payload);
    } catch (caught) {
      if (!handleAuthError(caught)) {
        setModelStatus(null);
      }
    }
  }, []);

  const loadEvaluationReport = React.useCallback(async () => {
    try {
      const response = await apiFetch("/api/v1/evaluation/retrieval");
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const payload = (await response.json()) as EvaluationReport;
      setEvaluationReport(payload);
    } catch (caught) {
      if (!handleAuthError(caught)) {
        setEvaluationReport(null);
      }
    }
  }, []);

  const loadAnalyticsReport = React.useCallback(async () => {
    try {
      const response = await apiFetch("/api/v1/analytics");
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const payload = (await response.json()) as AnalyticsReport;
      setAnalyticsReport(payload);
    } catch (caught) {
      if (!handleAuthError(caught)) {
        setAnalyticsReport(null);
      }
    }
  }, []);

  const inspectDocument = async (documentId: string) => {
    setBusy(true);
    setError("");
    setStatus("Loading document");
    try {
      const response = await apiFetch(`/api/v1/documents/${documentId}`);
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const payload = (await response.json()) as ManagedDocumentDetail;
      setSelectedDocument(payload);
      setStatus("Document loaded");
    } catch (caught) {
      if (!handleAuthError(caught)) {
        setError(caught instanceof Error ? caught.message : "Document detail failed");
        setStatus("Needs attention");
      }
    } finally {
      setBusy(false);
    }
  };

  React.useEffect(() => {
    loadDocuments();
    loadAnalyticsReport();
    loadModelStatus();
    loadEvaluationReport();
  }, [loadAnalyticsReport, loadDocuments, loadEvaluationReport, loadModelStatus]);

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
      loadDocuments();
      loadAnalyticsReport();
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
    if (!validateSelectedFile(selectedFile)) {
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
      loadDocuments();
      loadAnalyticsReport();
    } catch (caught) {
      if (!handleAuthError(caught)) {
        setError(caught instanceof Error ? caught.message : "Document upload failed");
        setStatus("Needs attention");
      }
    } finally {
      setBusy(false);
    }
  };

  const refreshJob = React.useCallback(async (jobId: string) => {
    const response = await apiFetch(`/api/v1/processing-jobs/${jobId}`);
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const payload = (await response.json()) as ProcessingJobStatus;
    setProcessingJobs((items) => items.map((item) => (item.job_id === jobId ? payload : item)));
    if (payload.status === "completed" || payload.status === "failed") {
      loadDocuments();
    }
    return payload;
  }, [loadDocuments]);

  const retryJob = async (jobId: string) => {
    setBusy(true);
    setError("");
    setStatus("Retrying job");
    try {
      const response = await apiFetch(`/api/v1/processing-jobs/${jobId}/retry`, {
        method: "POST"
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const payload = (await response.json()) as ProcessingJobStatus;
      setProcessingJobs((items) => items.map((item) => (item.job_id === jobId ? payload : item)));
      setStatus("Queued for retry");
      loadAnalyticsReport();
    } catch (caught) {
      if (!handleAuthError(caught)) {
        setError(caught instanceof Error ? caught.message : "Job retry failed");
        setStatus("Needs attention");
      }
    } finally {
      setBusy(false);
    }
  };

  React.useEffect(() => {
    const activeJobs = processingJobs.filter((job) => !["completed", "failed"].includes(job.status));
    if (!activeJobs.length) {
      return;
    }
    const timer = window.setInterval(() => {
      activeJobs.forEach((job) => {
        refreshJob(job.job_id).catch((caught) => {
          if (!handleAuthError(caught)) {
            setError(caught instanceof Error ? caught.message : "Job refresh failed");
          }
        });
      });
    }, 2500);
    return () => window.clearInterval(timer);
  }, [processingJobs, refreshJob]);

  const uploadDocumentAsync = async () => {
    if (!selectedFile) {
      return;
    }
    if (!validateSelectedFile(selectedFile)) {
      return;
    }
    setBusy(true);
    setError("");
    setStatus("Queueing");
    try {
      const form = new FormData();
      form.append("visibility", visibility);
      if (visibility === "role") {
        allowedRoles.forEach((role) => form.append("allowed_role_names", role));
      }
      form.append("force_ocr", String(forceOcr));
      form.append("file", selectedFile);

      const response = await apiFetch("/api/v1/documents/upload-async", {
        method: "POST",
        body: form
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const payload = (await response.json()) as ProcessingJobStatus;
      setProcessingJobs((items) => [payload, ...items]);
      setStatus("Queued");
      loadDocuments();
      loadAnalyticsReport();
    } catch (caught) {
      if (!handleAuthError(caught)) {
        setError(caught instanceof Error ? caught.message : "Async upload failed");
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
        throw new Error(await readApiError(response));
      }
      const payload = (await response.json()) as QueryResult;
      setResult(payload);
      setStatus(payload.cached ? "Cache hit" : "Answered");
      loadAnalyticsReport();
    } catch (caught) {
      if (!handleAuthError(caught)) {
        setError(caught instanceof Error ? caught.message : "Query failed");
        setStatus("Needs attention");
      }
    } finally {
      setBusy(false);
    }
  };

  const validateSelectedFile = (file: File) => {
    const extension = fileExtension(file.name);
    if (!ALLOWED_UPLOAD_EXTENSIONS.includes(extension)) {
      setError(`Unsupported file type '${extension || "none"}'. Choose a supported document format.`);
      setStatus("Needs attention");
      return false;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      setError(`File is ${formatBytes(file.size)}. The current upload limit is ${formatBytes(MAX_UPLOAD_BYTES)}.`);
      setStatus("Needs attention");
      return false;
    }
    return true;
  };

  const modelReady = Boolean(modelStatus?.embedding.ready && modelStatus.answer.ready);

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
          <div className="topbar-actions">
            <div
              className={`model-pill ${
                modelStatus ? (modelReady ? "ready" : "danger") : "pending"
              }`}
              title={modelStatus ? modelStatus.embedding.message : "Model status loading"}
            >
              <Cpu size={16} />
              <span>{modelStatus ? (modelReady ? "Models ready" : "Model attention") : "Models"}</span>
            </div>
            <div className={`status-pill ${status === "Needs attention" ? "danger" : ""}`}>
              {busy ? <Loader2 className="spin" size={16} /> : <Activity size={16} />}
              <span>{status}</span>
            </div>
          </div>
        </header>

        <section className="metrics-row" id="metrics">
          <Metric label="TTFT Target" value="<800 ms" icon={<Gauge size={18} />} />
          <Metric
            label="Retrieval"
            value={formatMilliseconds(result?.metrics.retrieval_ms)}
            icon={<Search size={18} />}
          />
          <Metric
            label="Total"
            value={formatMilliseconds(result?.metrics.total_ms)}
            icon={<Activity size={18} />}
          />
          <Metric
            label="Cache"
            value={result ? (result.cached ? "Hit" : "Miss") : "Ready"}
            icon={<RefreshCw size={18} />}
          />
          <Metric
            label="Contexts"
            value={String(result?.metrics.contexts_used ?? 0)}
            icon={<FileSearch size={18} />}
          />
          <Metric
            label="Embedding"
            value={formatEmbeddingRuntime(result, modelStatus)}
            icon={<Cpu size={18} />}
          />
          <Metric
            label="Answer Model"
            value={formatAnswerRuntime(result, modelStatus)}
            icon={<MessageSquareText size={18} />}
          />
        </section>

        <EvaluationPanel report={evaluationReport} onRefresh={loadEvaluationReport} />

        <AnalyticsPanel report={analyticsReport} onRefresh={loadAnalyticsReport} />

        {error ? <div className="error-banner">{error}</div> : null}

        <div className="content-grid">
          <section className="panel" id="intake">
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
                accept={ALLOWED_UPLOAD_EXTENSIONS.join(",")}
                onChange={(event) => {
                  const file = event.target.files?.[0] ?? null;
                  setSelectedFile(file);
                  if (file) {
                    validateSelectedFile(file);
                  }
                }}
              />
              <small className="field-help">
                Best for files from your Mac or another machine. Limit: {formatBytes(MAX_UPLOAD_BYTES)}.
                The browser sends the file to the backend, so no Docker path mapping is needed.
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
              disabled={busy || !selectedFile}
              onClick={uploadDocumentAsync}
            >
              <Activity size={18} />
              Upload to queue
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
              {processingJobs.map((job) => (
                <article className="document-card job-card" key={job.job_id}>
                  <div>
                    <strong>{job.file_name}</strong>
                    <span>
                      {job.status} / {job.stage} / attempt {job.attempts}
                    </span>
                    {job.error_message ? <small>{job.error_message}</small> : null}
                  </div>
                  <div className="job-actions">
                    {job.status === "failed" ? (
                      <button
                        className="icon-action"
                        type="button"
                        disabled={busy}
                        onClick={() => retryJob(job.job_id)}
                        title="Retry failed job"
                      >
                        <RotateCcw size={16} />
                      </button>
                    ) : null}
                    <Badge label={job.status} />
                  </div>
                </article>
              ))}
              {ingests.map((item) => (
                <article className="document-card" key={item.document_id}>
                  <div>
                    <strong>{item.file_name}</strong>
                    <span>{item.chunks_created} chunks</span>
                    {extractionWarnings(item).length ? (
                      <small>{extractionWarnings(item).length} extraction warning(s)</small>
                    ) : null}
                  </div>
                  <div className="job-actions">
                    {extractionWarnings(item).length ? (
                      <AlertTriangle size={16} className="warning-icon" />
                    ) : null}
                    {item.ocr_used ? <Badge label="OCR" /> : <Badge label="Text" />}
                  </div>
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

            {result ? <QueryRunDetails result={result} modelStatus={modelStatus} /> : null}
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

        <section className="panel management-panel" id="documents">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Document Management</p>
              <h3>Authorized document inventory</h3>
            </div>
            <button className="secondary-action compact-action" type="button" onClick={loadDocuments}>
              <RefreshCw size={16} />
              Refresh
            </button>
          </div>

          <div className="document-table" role="table" aria-label="Authorized documents">
            <div className="document-row table-head" role="row">
              <span>File</span>
              <span>Status</span>
              <span>Access</span>
              <span>Chunks</span>
              <span>OCR</span>
              <span>Warnings</span>
              <span>Updated</span>
              <span>Action</span>
            </div>
            {documents.map((document) => (
              <div className="document-row" role="row" key={document.document_id}>
                <span className="document-name">{document.file_name}</span>
                <Badge label={document.status} />
                <span>{document.visibility}</span>
                <span>{document.chunks_created}</span>
                <span>{document.ocr_used ? "Yes" : "No"}</span>
                <span>{extractionWarnings(document).length}</span>
                <span>{formatDate(document.updated_at ?? document.created_at)}</span>
                <button
                  className="secondary-action compact-action"
                  type="button"
                  onClick={() => inspectDocument(document.document_id)}
                >
                  <FileSearch size={16} />
                  View
                </button>
              </div>
            ))}
            {!documents.length ? (
              <div className="empty-state">No authorized documents found yet.</div>
            ) : null}
          </div>

          {selectedDocument ? (
            <article className="chunk-preview">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Chunk Preview</p>
                  <h3>{selectedDocument.file_name}</h3>
                </div>
                <Badge label={`${selectedDocument.chunks.length} visible chunks`} />
              </div>
              <div className="status-list document-detail-grid">
                <StatusItem label="Visibility" value={selectedDocument.visibility} />
                <StatusItem
                  label="Allowed roles"
                  value={selectedDocument.allowed_role_names.join(", ") || "tenant members"}
                />
                <StatusItem label="Audit" value={selectedDocument.latest_audit_action ?? "none"} />
                <StatusItem label="MIME" value={selectedDocument.mime_type ?? "unknown"} />
              </div>
              {extractionWarnings(selectedDocument).length ? (
                <div className="warning-panel" role="status" aria-label="Extraction warnings">
                  <div className="warning-heading">
                    <AlertTriangle size={17} />
                    <strong>Extraction warnings</strong>
                  </div>
                  <ul>
                    {extractionWarnings(selectedDocument).map((warning, index) => (
                      <li key={`${warning}-${index}`}>{warning}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              <div className="chunk-list">
                {selectedDocument.chunks.slice(0, 5).map((chunk) => (
                  <div className="chunk-card" key={chunk.chunk_index}>
                    <strong>Chunk {chunk.chunk_index}</strong>
                    <p>{chunk.text}</p>
                  </div>
                ))}
              </div>
            </article>
          ) : null}
        </section>

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
              <StatusItem
                label="Embedding runtime"
                value={formatRuntimeDetail(modelStatus?.embedding)}
              />
              <StatusItem label="Answer runtime" value={formatRuntimeDetail(modelStatus?.answer)} />
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

function extractionWarnings(document: { extraction_warnings?: string[] }) {
  return document.extraction_warnings ?? [];
}

function QueryRunDetails({
  result,
  modelStatus
}: {
  result: QueryResult;
  modelStatus: ModelStatus | null;
}) {
  return (
    <article className="query-run-details" aria-label="Query run details">
      <div className="run-detail-header">
        <Gauge size={16} />
        <strong>Run details</strong>
      </div>
      <div className="run-detail-grid">
        <StatusItem label="Cache" value={result.cached ? "Redis hit" : "Fresh retrieval"} />
        <StatusItem label="Contexts used" value={String(result.metrics.contexts_used ?? 0)} />
        <StatusItem label="Top score" value={formatScore(result.metrics.top_score)} />
        <StatusItem
          label="Retrieval"
          value={formatMilliseconds(result.metrics.retrieval_ms)}
        />
        <StatusItem label="Total" value={formatMilliseconds(result.metrics.total_ms)} />
        <StatusItem label="Embedding" value={formatEmbeddingRuntime(result, modelStatus)} />
        <StatusItem label="Answer" value={formatAnswerRuntime(result, modelStatus)} />
        <StatusItem
          label="Thresholds"
          value={`${formatScore(result.metrics.retrieval_min_score)} score / ${formatScore(
            result.metrics.retrieval_min_keyword_overlap
          )} overlap`}
        />
      </div>
    </article>
  );
}

function EvaluationPanel({
  report,
  onRefresh
}: {
  report: EvaluationReport | null;
  onRefresh: () => void;
}) {
  const summary = report?.summary;
  const passed = Boolean(summary && summary.failed === 0);

  return (
    <section className="panel evaluation-panel" aria-label="Retrieval evaluation quality gate">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Evaluation</p>
          <h3>Retrieval quality gate</h3>
        </div>
        <div className="evaluation-actions">
          <Badge label={summary ? (passed ? "Passed" : "Attention") : "Loading"} />
          <button className="secondary-action compact-action" type="button" onClick={onRefresh}>
            <RefreshCw size={16} />
            Refresh
          </button>
        </div>
      </div>

      <div className="quality-grid">
        <StatusItem
          label="Cases"
          value={summary ? `${summary.passed}/${summary.cases} passed` : "Loading"}
        />
        <StatusItem label="Context precision" value={formatPercent(summary?.context_precision)} />
        <StatusItem label="Context recall" value={formatPercent(summary?.context_recall)} />
        <StatusItem label="Answer relevance" value={formatPercent(summary?.answer_relevance)} />
      </div>

      <div className="evaluation-case-list">
        {(report?.results ?? []).map((item) => (
          <article className="evaluation-case" key={item.case_id}>
            <div>
              <strong>{item.case_id}</strong>
              <span>
                P {formatPercent(item.context_precision)} / R {formatPercent(item.context_recall)} /
                A {formatPercent(item.answer_relevance)}
              </span>
            </div>
            <Badge label={item.passed ? "PASS" : "FAIL"} />
          </article>
        ))}
        {!report ? <div className="empty-state compact-empty">Evaluation report loading.</div> : null}
      </div>
    </section>
  );
}

function AnalyticsPanel({
  report,
  onRefresh
}: {
  report: AnalyticsReport | null;
  onRefresh: () => void;
}) {
  return (
    <section className="panel analytics-panel" aria-label="Admin analytics">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Analytics</p>
          <h3>Admin operations summary</h3>
        </div>
        <button className="secondary-action compact-action" type="button" onClick={onRefresh}>
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>

      <div className="analytics-grid">
        <StatusItem label="Documents" value={report ? String(report.documents.total) : "Loading"} />
        <StatusItem label="Embedded" value={report ? String(report.documents.embedded) : "Loading"} />
        <StatusItem label="Chunks" value={report ? String(report.documents.chunks) : "Loading"} />
        <StatusItem
          label="OCR docs"
          value={report ? String(report.documents.ocr_documents) : "Loading"}
        />
        <StatusItem label="Jobs failed" value={report ? String(report.jobs.failed) : "Loading"} />
        <StatusItem label="Queries" value={report ? String(report.queries.total) : "Loading"} />
        <StatusItem
          label="Cache hit rate"
          value={report ? formatPercent(report.queries.cache_hit_rate) : "Loading"}
        />
        <StatusItem
          label="Avg total"
          value={report ? formatMilliseconds(report.queries.average_total_ms) : "Loading"}
        />
      </div>

      <div className="analytics-subgrid">
        <StatusItem
          label="Query latency"
          value={
            report
              ? `${formatMilliseconds(report.queries.average_retrieval_ms)} retrieval / ${formatMilliseconds(
                  report.queries.average_total_ms
                )} total`
              : "Loading"
          }
        />
        <StatusItem
          label="Job queue"
          value={
            report
              ? `${report.jobs.queued} queued / ${report.jobs.processing} running / ${report.jobs.completed} done`
              : "Loading"
          }
        />
        <StatusItem
          label="Evaluation"
          value={
            report
              ? `${report.evaluation.passed}/${report.evaluation.cases} cases / ${formatPercent(
                  report.evaluation.context_precision
                )} precision`
              : "Loading"
          }
        />
      </div>

      {report?.jobs.recent_failures.length ? (
        <div className="failure-list">
          {report.jobs.recent_failures.map((fileName) => (
            <Badge key={fileName} label={fileName} />
          ))}
        </div>
      ) : null}

      <div className="event-list" aria-label="Recent operations">
        {report?.recent_events.length ? (
          report.recent_events.map((event) => (
            <article className="event-item" key={`${event.action}-${event.resource_id}-${event.created_at}`}>
              <div>
                <strong>{event.action}</strong>
                <span>{auditEventSummary(event)}</span>
              </div>
              <span>{formatDate(event.created_at)}</span>
            </article>
          ))
        ) : (
          <div className="empty-state compact-empty">
            {report ? "No recent operations." : "Operations loading."}
          </div>
        )}
      </div>
    </section>
  );
}

function auditEventSummary(event: AnalyticsReport["recent_events"][number]) {
  const fileName = typeof event.metadata.file_name === "string" ? event.metadata.file_name : "";
  const contextsUsed =
    typeof event.metadata.contexts_used === "number" ? `${event.metadata.contexts_used} contexts` : "";
  const cacheState = typeof event.metadata.cached === "boolean" ? (event.metadata.cached ? "cache hit" : "fresh") : "";
  const actor = event.actor ?? "system";
  if (event.action === "query.executed") {
    return [contextsUsed, cacheState, actor].filter(Boolean).join(" / ");
  }
  const resource = fileName || event.resource_type;
  return `${resource} / ${actor}`;
}

function formatDate(value?: string | null) {
  if (!value) {
    return "unknown";
  }
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit"
  }).format(new Date(value));
}

function formatRuntime(status?: ModelRuntimeStatus) {
  if (!status) {
    return "Loading";
  }
  return `${status.runtime} / ${status.model_name}`;
}

function formatEmbeddingRuntime(result?: QueryResult | null, modelStatus?: ModelStatus | null) {
  const runtime = result?.metrics.local_embedding_runtime ?? modelStatus?.embedding.runtime;
  const model = result?.metrics.embedding_model ?? modelStatus?.embedding.model_name;
  return runtime && model ? `${runtime} / ${model}` : "Loading";
}

function formatAnswerRuntime(result?: QueryResult | null, modelStatus?: ModelStatus | null) {
  const runtime = result?.metrics.local_llm_runtime ?? modelStatus?.answer.runtime;
  const model = result?.metrics.answer_model ?? modelStatus?.answer.model_name;
  return runtime && model ? `${runtime} / ${model}` : "Loading";
}

function formatMilliseconds(value?: number) {
  if (typeof value !== "number") {
    return "0 ms";
  }
  return `${Math.round(value)} ms`;
}

function formatScore(value?: number) {
  if (typeof value !== "number") {
    return "0.000";
  }
  return value.toFixed(3);
}

function formatPercent(value?: number) {
  if (typeof value !== "number") {
    return "0%";
  }
  return `${Math.round(value * 100)}%`;
}

function fileExtension(fileName: string) {
  const index = fileName.lastIndexOf(".");
  return index >= 0 ? fileName.slice(index).toLowerCase() : "";
}

function formatBytes(value: number) {
  if (value >= 1024 * 1024 * 1024) {
    return `${(value / (1024 * 1024 * 1024)).toFixed(1)} GiB`;
  }
  if (value >= 1024 * 1024) {
    return `${(value / (1024 * 1024)).toFixed(0)} MiB`;
  }
  if (value >= 1024) {
    return `${(value / 1024).toFixed(0)} KiB`;
  }
  return `${value} bytes`;
}

async function readApiError(response: Response) {
  const text = await response.text();
  if (!text) {
    return `Request failed with HTTP ${response.status}`;
  }
  try {
    const parsed = JSON.parse(text) as { detail?: unknown };
    if (typeof parsed.detail === "string") {
      return parsed.detail;
    }
  } catch {
    return text;
  }
  return text;
}

function formatRuntimeDetail(status?: ModelRuntimeStatus) {
  if (!status) {
    return "Loading";
  }
  const readiness = status.ready ? "ready" : "attention";
  return `${status.runtime} / ${status.model_name} / ${readiness}`;
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
