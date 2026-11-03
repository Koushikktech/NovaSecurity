"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import Link from "next/link";
import DemoStage from "../../components/DemoStage";
import GitHubPicker from "../../components/GitHubPicker";
import { useReviewSession } from "../../hooks/useReviewSession";

type Evidence = {
  id: string;
  kind: string;
  tool_or_profile: string;
  output_snippet?: string;
};
type Finding = {
  patch_id?: string;
  evidence_status?: string;
  verification_assessment?: {
    citations?: { path: string; start_line: number; quote: string }[];
    explanation?: string;
    unresolved_assumptions?: string[];
  };
  id: string;
  category: string;
  title: string;
  explanation: string;
  user_impact: string;
  proposed_remedy?: string;
  severity: string;
  disposition: string;
  related_locations: {
    path: string;
    relationship: string;
    qualified_symbol: string;
  }[];
  primary_location: { path: string; start_line: number };
  analysis_status: string;
  evidence_items: Evidence[];
};
type ReviewMode = "auto" | "project" | "commit" | "compare" | "pr" | "folder";
type Activity = {
  provider?: string;
  attempts: number;
  failures: number;
  tokens: number;
  elapsed_ms: number;
  thinking: string;
  max_attempts: number;
  log: {
    model: string;
    role: string;
    attempt: number;
    state: string;
    error?: string;
    warning?: string;
    api_mode?: string;
  }[];
};
type Coverage = {
  validation_rejections?: {finding_id: string; path: string; reason: string}[];
  impact?: {
    changes: {
      symbol: {
        id: string;
        name: string;
        path: string;
        start: number;
        end: number;
      };
      callers: { path: string; line: number; relationship: string }[];
      test_hints: string[];
    }[];
    deleted_symbols: { path: string; name: string; start: number }[];
    limitations: string;
  };
  verification_coverage?: {
    requested: number;
    assessed: number;
    unassessed_ids: string[];
    evidence_counts?: Record<string, number>;
  };
  challenge_error?: string;
  excluded_files?: string[];
  source_exclusions?: { path: string; reason: string; side: string }[];
  repository_policy_source?: string;
  repository_policy?: {verification_profile?: string};
  finding_lifecycle?: {
    previous_run_id?: string;
    changes: { state: string; reason?: string }[];
  };
  investigation?: {
    model_calls: number;
    tool_calls: number;
    trace: {
      event_type: string;
      tool?: { name: string; path?: string; query?: string };
      role?: string;
      stage?: string;
    }[];
  };
  model_activity?: Activity;
  progress?: { batch: number; batches: number };
  target?: {
    mode: string;
    comparison: string;
    revision_label: string;
    snapshot_id?: string;
  };
  total_files?: number;
  source_files?: string[];
  unsupported_files?: string[];
  scope_note?: string;
  project_review?: {
    depth: string;
    reviewed_files: string[];
    omitted_files: string[];
    reason?: string;
  };
  review_summary?: string;
  model_review_error?: string;
  changed_files?: string[];
  diff?: string;
  test_gaps?: { path: string; suggestion: string }[];
  javascript?: { status: string };
  static_tools?: Record<string, { status: string }>;
  context?: { omitted: string[] };
};
type Run = {
  provider?: string;
  review_mode?: string;
  review_depth?: string;
  id: string;
  status: string;
  base_sha?: string;
  head_sha?: string;
  coverage: Coverage;
  stage_statuses: Record<string, string>;
};
type Patch = {
  id: string;
  diff: string;
  status: string;
  checks: {
    check_name: string;
    status: string;
    stdout_snippet: string;
    stderr_snippet: string;
  }[];
};
const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export default function Review() {
  const [verificationProfile, setVerificationProfile] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [tab, setTab] = useState("findings");
  const [roleModels, setRoleModels] = useState<Record<string, string>>({});
  const [profiles, setProfiles] = useState<string[]>([
    "expense_service_sql",
    "python_contract",
    "javascript_contract",
    "typescript_contract",
  ]);
  const [provider, setProvider] = useState("gemini");
  const [codexReasoning, setCodexReasoning] = useState("high");
  const [codexStatus, setCodexStatus] = useState<{
    enabled?: boolean;
    installed?: boolean;
    chatgpt_signed_in?: boolean;
    model?: string;
    version?: string;
    models?: { model: string; default: boolean; reasoning: string[] }[];
  }>({});
  const providerInitialized = useRef(false);
  const [model, setModel] = useState("");
  const [thinking, setThinking] = useState("default");
  const [apiMode, setApiMode] = useState("auto");
  const [attempts, setAttempts] = useState(3);
  const [search, setSearch] = useState("");
  const [severity, setSeverity] = useState("all");
  const [entry, setEntry] = useState("url");
  const [url, setUrl] = useState("");
  const [mode, setMode] = useState<ReviewMode>("auto");
  const [revision, setRevision] = useState("");
  const [baseRef] = useState("");
  const [headRef] = useState("");
  const [depth, setDepth] = useState("quick");
  const [folder, setFolder] = useState<File[]>([]);
  const effectiveMode =
    mode !== "auto"
      ? mode
      : url.includes("/pull/")
        ? "pr"
        : url.includes("/commit/")
          ? "commit"
          : url.includes("/compare/")
            ? "compare"
            : "project";
  const labels: Record<string, string> = {
    auto: "Detect from URL",
    project: "Whole project",
    commit: "Single commit",
    compare: "Compare revisions",
    pr: "Pull request",
    folder: "Local folder",
  };

  const [token, setToken] = useState("");
  const [filter, setFilter] = useState("all");
  const [action, setAction] = useState("");
  const [patch, setPatch] = useState<Patch | null>(null);
  const [source, setSource] = useState<{
    path: string;
    content: string;
  } | null>(null);
  const [message, setMessage] = useState("");
  const lastExample = useRef(false);

  const request = useCallback(
    async (path: string, init?: RequestInit) => {
      const response = await fetch(base + "/api/v1" + path, {
        ...init,
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: "Bearer " + token } : {}),
          ...init?.headers,
        },
      });
      if (!response.ok) {
        const body = await response
          .json()
          .catch(() => ({ detail: response.statusText }));
        throw Object.assign(
          new Error(
            typeof body.detail === "string" ? body.detail : "Request failed",
          ),
          { status: response.status },
        );
      }
      return response.json();
    },
    [token],
  );
  const {
    run,
    findings,
    busy,
    error,
    connection,
    setError,
    startReview,
    openReview,
    refreshFindings,
    activeRunId,
  } = useReviewSession<Run, Finding>(request);
  useEffect(() => {
    let active = true;
    request("/capabilities")
      .then((data) => {
        if (active && data.providers?.codex_cli)
          setCodexStatus(data.providers.codex_cli);
        if (active && !providerInitialized.current && data.default_provider) {
          providerInitialized.current = true;
          setProvider(data.default_provider);
          if (data.default_provider === "codex_cli") {
            setAttempts(1);
            setCodexReasoning(data.providers?.codex_cli?.reasoning || "high");
          }
        }
        if (active && Array.isArray(data.trusted_verification_profiles))
          setProfiles(data.trusted_verification_profiles);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [request]);
  async function perform(label: string, fn: () => Promise<void>) {
    setAction(label);
    setError("");
    setMessage("");
    try {
      await fn();
    } catch (e) {
      setError(String(e));
    } finally {
      setAction("");
    }
  }
  async function start(example = false, resumeId?: string) {
    lastExample.current = example;
    setSelected(null);
    setTab("findings");
    setError("");
    setPatch(null);
    setVerificationProfile("");
    setSource(null);
    setMessage("");
    await startReview(async (signal) => {
      let created;
      if (resumeId) {
        created = await request("/reviews/" + resumeId + "/resume", {
          method: "POST",
          signal,
        });
      } else if (example) {
        created = await request("/examples/checkout", {
          method: "POST",
          signal,
          body: JSON.stringify({
            provider,
            model: model || null,
            codex_reasoning: codexReasoning,
            thinking,
            api_mode: apiMode,
            max_attempts: attempts,
            role_models: Object.fromEntries(
              Object.entries(roleModels).filter(([, v]) => v),
            ),
          }),
        });
      } else if (mode === "folder") {
        if (!folder.length)
          throw new Error("Select a folder containing supported source files");
        let total = 0;
        const files = [];
        for (const file of folder) {
          const original = file.webkitRelativePath || file.name;
          const path = file.webkitRelativePath
            ? original.split("/").slice(1).join("/")
            : file.name;
          if (
            path
              .split("/")
              .some((p) =>
                [
                  "node_modules",
                  ".git",
                  ".ssh",
                  ".aws",
                  ".azure",
                  ".gcloud",
                  ".venv",
                  "vendor",
                  "dist",
                  "build",
                  "__pycache__",
                ].includes(p),
              )
          )
            continue;
          const basename = path.split("/").at(-1)?.toLowerCase() || "";
          if (
            basename === "application_default_credentials.json" ||
            (basename.startsWith(".env.") &&
              ![".env.example", ".env.sample", ".env.template"].includes(
                basename,
              ))
          )
            continue;
          if (
            !/\.(py|js|jsx|ts|tsx|json|toml|yaml|yml|ini|cfg|md)$/i.test(
              path,
            ) ||
            file.size > 512000
          )
            continue;
          total += file.size;
          if (total > 20 * 1024 * 1024 || files.length >= 2000)
            throw new Error(
              "Folder limit: 20 MiB of text source and 2,000 files",
            );
          files.push({ path, content: await file.text() });
        }
        if (!files.length)
          throw new Error(
            "No supported source files were found in this folder",
          );
        created = await request("/reviews/folder", {
          method: "POST",
          signal,
          body: JSON.stringify({
            files,
            depth,
            role_models: Object.fromEntries(
              Object.entries(roleModels).filter(([, v]) => v),
            ),
            model: model || null,
            provider,
            codex_reasoning: codexReasoning,
            api_mode: apiMode,
            thinking,
            max_attempts: attempts,
          }),
        });
      } else {
        created = await request("/reviews", {
          method: "POST",
          signal,
          body: JSON.stringify({
            role_models: Object.fromEntries(
              Object.entries(roleModels).filter(([, v]) => v),
            ),
            model: model || null,
            provider,
            codex_reasoning: codexReasoning,
            api_mode: apiMode,
            thinking,
            max_attempts: attempts,
            repo_url: url,
            mode: effectiveMode,
            revision: ["project", "commit"].includes(effectiveMode)
              ? revision || null
              : null,
            base_sha: effectiveMode === "compare" ? baseRef || null : null,
            head_sha: effectiveMode === "compare" ? headRef || null : null,
            depth,
          }),
        });
      }
      return created;
    });
  }
  async function restoreReport(id: string) {
    setSelected(null);
    setPatch(null);
    setSource(null);
    setMessage("");
    setTab("findings");
    await openReview(id);
  }
  async function cancel() {
    if (activeRunId.current)
      await request("/reviews/" + activeRunId.current + "/cancel", {
        method: "POST",
      });
  }
  async function download(path: string, name: string, raw = false) {
    const response = await fetch(base + "/api/v1" + path, {
      headers: token ? { Authorization: "Bearer " + token } : {},
    });
    if (!response.ok) throw new Error("Download failed");
    const content = raw
      ? await response.text()
      : JSON.stringify(await response.json(), null, 2);
    const href = URL.createObjectURL(
      new Blob([content], { type: raw ? "text/plain" : "application/json" }),
    );
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.download = name;
    anchor.click();
    URL.revokeObjectURL(href);
  }
  const [restoreId, setRestoreId] = useState("");
  const visible = findings
    .filter(
      (f) =>
        (filter === "all" || f.category === filter) &&
        (severity === "all" || f.severity === severity) &&
        (f.title + f.primary_location.path)
          .toLowerCase()
          .includes(search.toLowerCase()),
    )
    .sort(
      (a, b) =>
        ["critical", "high", "medium", "low", "info"].indexOf(a.severity) -
        ["critical", "high", "medium", "low", "info"].indexOf(b.severity),
    );
  const chosen = visible.find((f) => f.id === selected) || visible[0];
  const effectiveVerificationProfile = verificationProfile || run?.coverage.repository_policy?.verification_profile || profiles[0] || "expense_service_sql";
  const activity = run?.coverage.model_activity;
  const reportProvider = activity?.provider || run?.provider || provider;
  const diffView = (text: string) => (
    <pre className="code diff">
      {text.split("\n").map((line, i) => (
        <span
          key={i}
          className={
            line.startsWith("+")
              ? "added"
              : line.startsWith("-")
                ? "removed"
                : line.startsWith("@@")
                  ? "hunk"
                  : ""
          }
        >
          {line || " "}
          {"\n"}
        </span>
      ))}
    </pre>
  );
  return (
    <main className="studio">
      <nav className="topbar">
        <Link href="/" className="brand">
          <span>p.</span> proofline
        </Link>
        <span className="eyebrow">CODE REVIEW WORKSPACE</span>
        <details className="settings">
          <summary>Settings & debug</summary>
          <div className="settings-body">
            <h3>Model configuration</h3>
            <p>
              Applies to the next review, including the example. Repairs and
              resumed runs inherit their saved provider and model.
            </p>
            <label>
              Model provider
              <select
                aria-label="Model provider"
                value={provider}
                onChange={(e) => {
                  providerInitialized.current = true;
                  setProvider(e.target.value);
                  setModel("");
                  setRoleModels({});
                  setAttempts(e.target.value === "codex_cli" ? 1 : 3);
                }}
              >
                <option value="gemini">Google Gemini API</option>
                <option value="codex_cli" disabled={!codexStatus.enabled}>
                  Local Codex · ChatGPT subscription
                </option>
              </select>
            </label>
            {provider === "codex_cli" && (
              <p role="status">
                {codexStatus.chatgpt_signed_in
                  ? "ChatGPT signed in"
                  : "Run codex login with ChatGPT on this computer"}{" "}
                · {codexStatus.version || "CLI status unavailable"}. Uses your
                subscription limits; requests still go to OpenAI. Localhost
                only.
              </p>
            )}
            <label>
              Model ID
              <input
                list={
                  provider === "codex_cli" ? "codex-account-models" : undefined
                }
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder={
                  provider === "codex_cli"
                    ? codexStatus.model || "Account default"
                    : "Server default"
                }
              />
            </label>
            {provider === "codex_cli" && (
              <datalist id="codex-account-models">
                {codexStatus.models?.map((row) => (
                  <option key={row.model} value={row.model}>
                    {row.default ? "Account default" : row.model}
                  </option>
                ))}
              </datalist>
            )}
            <details>
              <summary>Advanced model roles</summary>
              {[
                ["review", "Review model"],
                ["verify_reasoning", "Verifier model"],
                ["patch", "Repair model"],
              ].map(([role, label]) => (
                <label key={role}>
                  {label}
                  <input
                    value={roleModels[role] || ""}
                    placeholder="Use selected model or server default"
                    onChange={(e) =>
                      setRoleModels((old) => ({
                        ...old,
                        [role]: e.target.value,
                      }))
                    }
                  />
                </label>
              ))}
            </details>
            {provider === "gemini" ? (
              <>
                <label>
                  Gemini API
                  <select
                    aria-label="Gemini API"
                    value={apiMode}
                    onChange={(e) => setApiMode(e.target.value)}
                  >
                    <option value="auto">
                      Auto (Interactions for modern models)
                    </option>
                    <option value="interactions">Interactions</option>
                    <option value="generate_content">Generate content</option>
                  </select>
                </label>
                <p>
                  Interactions are stateless: conversation storage and automatic
                  continuation are disabled.
                </p>
                <label>
                  Reasoning
                  <select
                    value={thinking}
                    onChange={(e) => setThinking(e.target.value)}
                  >
                    <option value="default">Provider default</option>
                    <option value="low">Low</option>
                    <option value="high">High</option>
                  </select>
                </label>
                <p>
                  Gemini 2.5: 1,024 / 8,192 thinking tokens. Gemini 3–4: low /
                  high thinking level. Model availability depends on your API
                  account.
                </p>
              </>
            ) : (
              <>
                <label>
                  Codex reasoning
                  <select
                    aria-label="Codex reasoning"
                    value={codexReasoning}
                    onChange={(e) => setCodexReasoning(e.target.value)}
                  >
                    {["low", "medium", "high", "xhigh", "max"].map((effort) => (
                      <option value={effort} key={effort}>
                        {effort === "high" ? "High · demo default" : effort}
                      </option>
                    ))}
                  </select>
                </label>
                <p>
                  Choose an account-supported model. High is the demo default;
                  higher effort can take longer. Native CLI tools are disabled;
                  Proofline handles source investigation. Invocation counts may
                  include CLI-internal service retries.
                </p>
              </>
            )}
            <label>
              Maximum attempts per request
              <input
                type="number"
                min="1"
                max="5"
                value={attempts}
                onChange={(e) =>
                  setAttempts(
                    Math.max(1, Math.min(5, Number(e.target.value) || 1)),
                  )
                }
              />
            </label>
            <label>
              Operator access token
              <input
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                autoComplete="off"
              />
            </label>
            <label>
              Restore report
              <input
                placeholder="Review ID"
                value={restoreId}
                onChange={(e) => setRestoreId(e.target.value)}
              />
            </label>
            <button onClick={() => void restoreReport(restoreId.trim())}>
              Open saved report
            </button>
            {run && (
              <>
                <p>Review ID: {run.id}</p>
                <button
                  onClick={() =>
                    void perform("Exporting", () =>
                      download(
                        "/reviews/" + run.id + "/export",
                        "proofline-review.json",
                      ),
                    )
                  }
                >
                  Download diagnostic report
                </button>
              </>
            )}
          </div>
        </details>
      </nav>
      <header className="intro">
        <div>
          <p className="eyebrow">A SECOND PAIR OF EYES</p>
          <h1>
            Ship with
            <br />
            <em>understanding.</em>
          </h1>
        </div>
        <p>
          See what breaks, why it matters,
          <br />
          and what to do next.
          <br />
          <span>Python · JavaScript · TypeScript</span>
        </p>
      </header>
      <section className="launch">
        <div className="section-label">01 / Choose your code</div>
        <div className="launch-body">
          <div className="switcher">
            {["url", "github", "folder"].map((x) => (
              <button
                key={x}
                aria-pressed={entry === x}
                onClick={() => {
                  setEntry(x);
                  setMode(x === "folder" ? "folder" : "auto");
                  setUrl("");
                  setRevision("");
                }}
              >
                {x === "url"
                  ? "Paste a link"
                  : x === "github"
                    ? "Pick from GitHub"
                    : "Local folder"}
              </button>
            ))}
          </div>
          {entry === "github" && (
            <GitHubPicker
              request={request}
              onSelect={(u, ref) => {
                setUrl(u);
                setRevision(ref);
                setMode("auto");
              }}
            />
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void start();
            }}
          >
            {entry === "url" && (
              <input
                className="url-input"
                type="url"
                required
                aria-label="GitHub review URL"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="Paste a repository, PR, commit or comparison URL"
              />
            )}
            {entry === "folder" && (
              <label>
                Choose source folder
                <input
                  type="file"
                  aria-label="Source folder"
                  multiple
                  {...{ webkitdirectory: "" }}
                  onChange={(e) => setFolder(Array.from(e.target.files || []))}
                />
                <small>
                  {folder.length} files selected; dependencies and binaries
                  excluded.
                </small>
              </label>
            )}
            <div className="launch-actions">
              <span className="muted">
                {url
                  ? labels[effectiveMode] + " detected"
                  : "Choose code to start a review"}
              </span>
              <button
                type="button"
                className="quiet"
                disabled={busy}
                onClick={() => void start(true)}
              >
                Try checkout demo ↗
              </button>
              <button
                className="primary"
                disabled={busy || (!url && mode !== "folder")}
              >
                {busy ? "Review in progress…" : "Start review →"}
              </button>
            </div>
            <details className="advanced">
              <summary>Scope options</summary>
              <label>
                Branch, tag or commit
                <input
                  aria-label="Project revision"
                  value={revision}
                  onChange={(e) => setRevision(e.target.value)}
                />
              </label>
              <label>
                Analysis depth
                <select
                  value={depth}
                  onChange={(e) => setDepth(e.target.value)}
                >
                  <option value="quick">Quick · prioritized context</option>
                  <option value="deep">Deep · source batches</option>
                </select>
              </label>
            </details>
          </form>
        </div>
      </section>
      {error && (
        <div role="alert" className="notice error">
          {error}
          <button
            onClick={() =>
              activeRunId.current
                ? void openReview(activeRunId.current)
                : void start(lastExample.current)
            }
          >
            {activeRunId.current ? "Reconnect to saved review" : "Retry review"}
          </button>
        </div>
      )}
      {connection === "retrying" && (
        <p role="status" className="notice">
          Connection lost. Reconnecting to this review; no new review is being
          submitted.
        </p>
      )}
      {message && (
        <div role="status" className="notice">
          {message}
        </div>
      )}
      {action && (
        <p role="status" className="notice">
          {action}…
        </p>
      )}
      {run && (
        <>
          <DemoStage run={run} findings={findings} patch={patch} source={source}
            onInspect={(id) => { setSelected(id); setTab("findings"); setFilter("all"); setSeverity("all"); setSearch(""); setTimeout(() => document.querySelector(".review-grid")?.scrollIntoView({behavior:"smooth", block:"start"}), 50); }}
            onSource={(path) => { void perform("Loading source", async () => { setSource(null); setSource(await request("/reviews/" + run.id + "/source?path=" + encodeURIComponent(path))); }); }} />
          <section className="run-summary">
            <div>
              <p className="eyebrow">02 / Review overview</p>
              <h2>
                {busy
                  ? "Following the evidence…"
                  : (
                      {
                        partial: "Review needs attention.",
                        failed: "Review failed.",
                        cancelled: "Review cancelled.",
                        interrupted: "Review interrupted.",
                        completed: "Your review is ready.",
                      } as Record<string, string>
                    )[run.status] || "Review pending."}
              </h2>
              <p>
                {run.coverage.review_summary ||
                  "Results apply to the analyzed scope. Inspect coverage before drawing conclusions."}
              </p>
            </div>
            <div className="metrics">
              <div>
                <strong>
                  {
                    findings.filter(
                      (f) =>
                        ["critical", "high"].includes(f.severity) &&
                        f.disposition !== "dismissed",
                    ).length
                  }
                </strong>
                <span>High priority</span>
              </div>
              <div>
                <strong>{findings.length}</strong>
                <span>Total findings</span>
              </div>
              <div>
                <strong>{activity?.attempts || 0}</strong>
                <span>
                  {reportProvider === "codex_cli"
                    ? "Codex CLI invocations"
                    : "Gemini API attempts"}
                </span>
              </div>
            </div>
          </section>
          <section className="activity">
            <div className="row">
              <strong>
                <span className={busy ? "pulse" : "dot"} /> {run.status}
              </strong>
              <span>
                {activity?.log.at(-1)?.model || "No model request recorded"} ·{" "}
                {activity?.tokens || 0} tokens · {activity?.failures || 0}{" "}
                failed attempts
              </span>
              {busy ? (
                <button onClick={() => void perform("Cancelling", cancel)}>
                  Cancel
                </button>
              ) : (
                <button onClick={() => void start(false, run.id)}>
                  Resume pinned review
                </button>
              )}
            </div>
            <div className="stages">
              {Object.entries(run.stage_statuses).map(([k, v]) => (
                <span key={k} data-state={v}>
                  {k === "gemini_review"
                    ? "model review"
                    : k.replaceAll("_", " ")}{" "}
                  <b>{v}</b>
                </span>
              ))}
            </div>
            {run.coverage.model_review_error && (
              <p className="error">
                AI analysis incomplete: {run.coverage.model_review_error}.
                Static findings remain available.
              </p>
            )}
            {run.coverage.challenge_error && (
              <p className="error">
                Independent verification incomplete:{" "}
                {run.coverage.challenge_error}
              </p>
            )}
            <details>
              <summary>Investigation tools & checkpoints</summary>
              <p>
                {run.coverage.investigation?.tool_calls || 0} tool calls ·{" "}
                {run.coverage.investigation?.model_calls || 0} structured model
                calls
              </p>
              {run.coverage.investigation?.trace.map((e, i) => (
                <div className="log-row" key={i}>
                  <strong>{e.event_type.replaceAll("_", " ")}</strong>
                  <span>{e.role || e.stage}</span>
                  <code>
                    {e.tool?.name} {e.tool?.path || e.tool?.query}
                  </code>
                </div>
              ))}
            </details>
            <details>
              <summary>Model activity & request history</summary>
              <p>
                {reportProvider === "codex_cli"
                  ? "Counts are CLI launches, including Proofline retries; CLI-internal service retries are not separately counted."
                  : "Attempts include automatic retries."}{" "}
                Maximum {activity?.max_attempts || attempts} per request.
                Reasoning: {activity?.thinking || "server default"}. No recorded
                activity means no recorded model contact.
              </p>
              {activity?.log.map((e, i) => (
                <div className="log-row" key={i}>
                  <span>{e.role.replaceAll("_", " ")}</span>
                  <code>{e.model}</code>
                  <span>
                    Attempt {e.attempt}
                    {e.api_mode ? " · " + e.api_mode.replaceAll("_", " ") : ""}
                  </span>
                  <b>{e.state}</b>
                  {e.error && <p>{e.error}</p>}
                  {e.warning && <p>CLI diagnostic: {e.warning}</p>}
                </div>
              ))}
            </details>
          </section>
          <div className="report-tabs">
            {["findings", "changes", "coverage"].map((t) => (
              <button
                aria-pressed={tab === t}
                key={t}
                onClick={() => setTab(t)}
              >
                {t === "findings"
                  ? "Findings · " + findings.length
                  : t === "changes"
                    ? "Files & diff"
                    : "Coverage & test gaps"}
              </button>
            ))}
            {run.review_mode === "pr" && (
              <button
                onClick={() => {
                  if (window.confirm("Publish this review to GitHub?"))
                    void perform("Publishing review", async () => {
                      const result = await request(
                        "/reviews/" + run.id + "/publish",
                        { method: "POST" },
                      );
                      setMessage(
                        result.published
                          ? "Published: " + result.url
                          : result.message,
                      );
                    });
                }}
              >
                Publish review
              </button>
            )}
            <button
              className="export"
              onClick={() =>
                void perform("Exporting", () =>
                  download(
                    "/reviews/" + run.id + "/export",
                    "proofline-review.json",
                  ),
                )
              }
            >
              Export report ↗
            </button>
          </div>
          {tab === "findings" && (
            <>
              <div className="filters">
                <div className="switcher">
                  {["all", "bug", "security", "style"].map((c) => (
                    <button
                      aria-pressed={filter === c}
                      key={c}
                      onClick={() => setFilter(c)}
                    >
                      {c === "all"
                        ? "All findings"
                        : c === "bug"
                          ? "Correctness"
                          : c}{" "}
                      <small>
                        {
                          findings.filter(
                            (f) => c === "all" || f.category === c,
                          ).length
                        }
                      </small>
                    </button>
                  ))}
                </div>
                <input
                  aria-label="Search findings"
                  placeholder="Search title or file…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
                <select
                  aria-label="Severity filter"
                  value={severity}
                  onChange={(e) => setSeverity(e.target.value)}
                >
                  {["all", "critical", "high", "medium", "low", "info"].map(
                    (v) => (
                      <option value={v} key={v}>
                        {v === "all" ? "Every severity" : v}
                      </option>
                    ),
                  )}
                </select>
              </div>
              <div className="review-grid">
                <aside className="finding-list">
                  {visible.map((f) => (
                    <button
                      key={f.id}
                      className={
                        chosen?.id === f.id ? "finding selected" : "finding"
                      }
                      onClick={() => {
                        setSelected(f.id);
                        setSource(null);
                        setPatch(null);
                      }}
                    >
                      <div>
                        <span className={"badge " + f.severity}>
                          {f.severity}
                        </span>
                        <small>
                          {f.category} · {f.disposition}
                        </small>
                      </div>
                      <h3>{f.title}</h3>
                      <code>
                        {f.primary_location.path}:
                        {f.primary_location.start_line}
                      </code>
                    </button>
                  ))}
                  {!visible.length && (
                    <div className="empty">
                      <h3>
                        {busy
                          ? "Analysis is running"
                          : "No findings in this view"}
                      </h3>
                      <p>
                        {busy
                          ? "Findings will appear when review completes."
                          : "Try another filter and check review coverage."}
                      </p>
                    </div>
                  )}
                </aside>
                <article className="inspector">
                  {chosen ? (
                    <>
                      <p className="eyebrow">
                        {chosen.category} /{" "}
                        {chosen.analysis_status.replaceAll("_", " ")}
                      </p>
                      <h2>{chosen.title}</h2>
                      <button
                        className="file-link"
                        onClick={() =>
                          void perform("Loading source", async () =>
                            setSource(
                              await request(
                                "/reviews/" +
                                  run.id +
                                  "/source?path=" +
                                  encodeURIComponent(
                                    chosen.primary_location.path,
                                  ),
                              ),
                            ),
                          )
                        }
                      >
                        {chosen.primary_location.path}:
                        {chosen.primary_location.start_line} ↗
                      </button>
                      <p className="badge">
                        Evidence: {chosen.evidence_status || "unassessed"}
                      </p>
                      {chosen.verification_assessment?.explanation && (
                        <p>{chosen.verification_assessment.explanation}</p>
                      )}
                      {chosen.verification_assessment?.citations?.map(
                        (c, i) => (
                          <div className="evidence" key={i}>
                            <button
                              className="file-link"
                              onClick={() =>
                                void perform("Loading cited source", async () =>
                                  setSource(
                                    await request(
                                      "/reviews/" +
                                        run.id +
                                        "/source?path=" +
                                        encodeURIComponent(c.path),
                                    ),
                                  ),
                                )
                              }
                            >
                              {c.path}:{c.start_line} ↗
                            </button>
                            <pre>{c.quote}</pre>
                          </div>
                        ),
                      )}
                      <div className="explanation">
                        <section>
                          <h4>What happens</h4>
                          <p>{chosen.explanation}</p>
                        </section>
                        <section>
                          <h4>Why it matters</h4>
                          <p>{chosen.user_impact}</p>
                        </section>
                        <section>
                          <h4>Recommended action</h4>
                          <p>
                            {chosen.proposed_remedy ||
                              "Inspect the cited behavior and add a regression test."}
                          </p>
                        </section>
                      </div>
                      {chosen.related_locations.length > 0 && (
                        <section>
                          <h4>Affected code</h4>
                          {chosen.related_locations.map((l, i) => (
                            <p key={i}>
                              <code>{l.path}</code> — {l.relationship}
                            </p>
                          ))}
                        </section>
                      )}
                      <details open>
                        <summary>
                          Supporting evidence · {chosen.evidence_items.length}
                        </summary>
                        {chosen.evidence_items.map((e) => (
                          <div className="evidence" key={e.id}>
                            <strong>{e.tool_or_profile}</strong>
                            <pre>{e.output_snippet || e.kind}</pre>
                          </div>
                        ))}
                      </details>
                      <div className="row">
                        <button
                          className="primary"
                          disabled={!!action}
                          onClick={() =>
                            void perform(
                              "Generating proposed repair",
                              async () =>
                                setPatch(
                                  await request(
                                    "/findings/" + chosen.id + "/patches",
                                    { method: "POST" },
                                  ),
                                ),
                            )
                          }
                        >
                          Propose repair
                        </button>
                        {chosen.patch_id && <button onClick={()=>void perform("Loading saved repair",async()=>setPatch(await request("/patches/"+chosen.patch_id)))}>Open saved repair</button>}
                        <button
                          onClick={() =>
                            void perform("Updating", async () => {
                              await request(
                                "/findings/" + chosen.id + "/disposition",
                                {
                                  method: "PATCH",
                                  body: JSON.stringify({
                                    disposition:
                                      chosen.disposition === "dismissed"
                                        ? "open"
                                        : "dismissed",
                                    reason: "Developer review",
                                  }),
                                },
                              );
                              await refreshFindings(run.id);
                            })
                          }
                        >
                          {chosen.disposition === "dismissed"
                            ? "Reopen finding"
                            : "Dismiss finding"}
                        </button>
                      </div>
                      {source && (
                        <section>
                          <h4>Source · {source.path}</h4>
                          <pre className="code">
                            {source.content.split("\n").map((l, i) => (
                              <span
                                className={
                                  source.path ===
                                    chosen.primary_location.path &&
                                  i + 1 === chosen.primary_location.start_line
                                    ? "highlight"
                                    : ""
                                }
                                key={i}
                              >
                                {String(i + 1).padStart(4)} {l}
                                {"\n"}
                              </span>
                            ))}
                          </pre>
                        </section>
                      )}
                      {patch && (
                        <section className="repair">
                          <h3>
                            {patch.status === "checks_passed" ? "Checked repair" : "Proposed repair"}{" "}
                            <span className="badge">{patch.status.replaceAll("_", " ")}</span>
                          </h3>
                          <p>
                            {patch.status === "checks_passed" ? "Protected regression and happy-path checks passed for this patch and snapshot. Inspect the diff before applying." : "Inspect the diff before applying. This proposal has not passed the approved execution checks."}
                          </p>
                          {diffView(patch.diff)}
                          {patch.checks.map((c, i) => (
                            <details key={i}>
                              <summary>
                                {{base:"Original", before:"Changed", after:"Repaired"}[c.check_name] || c.check_name} · {c.status}
                              </summary>
                              <pre className="code">
                                {c.stdout_snippet + "\n" + c.stderr_snippet}
                              </pre>
                            </details>
                          ))}
                          <button
                            onClick={() =>
                              void perform("Downloading", () =>
                                download(
                                  "/patches/" + patch.id + "/download",
                                  "proofline.patch",
                                  true,
                                ),
                              )
                            }
                          >
                            Download patch
                          </button>
                          <details>
                            <summary>Verification & publication</summary>
                            <p>
                              Execution requires the matching trusted oracle,
                              pinned base snapshot for differential profiles,
                              and configured Docker images. A profile cannot
                              verify arbitrary project behavior.
                            </p>
                            <label>
                              Verification profile
                              <select
                                aria-label="Verification profile"
                                value={effectiveVerificationProfile}
                                onChange={(e) =>
                                  setVerificationProfile(e.target.value)
                                }
                              >
                                {profiles.map((p) => (
                                  <option key={p}>{p}</option>
                                ))}
                              </select>
                            </label>
                            <button
                              disabled={!!action}
                              onClick={() =>
                                void perform("Verifying repair", async () => {
                                  const result = await request(
                                    "/patches/" + patch.id + "/verify",
                                    {
                                      method: "POST",
                                      body: JSON.stringify({
                                        profile_id: effectiveVerificationProfile,
                                      }),
                                    },
                                  );
                                  setMessage(result.message);
                                  setPatch(
                                    await request("/patches/" + patch.id),
                                  );
                                })
                              }
                            >
                              Run approved verification
                            </button>
                            {run.review_mode === "pr" && (
                              <button
                                onClick={() => {
                                  if (
                                    window.confirm(
                                      "Create a fix pull request on GitHub?",
                                    )
                                  )
                                    void perform("Publishing fix", async () => {
                                      const result = await request(
                                        "/patches/" + patch.id + "/publish",
                                        { method: "POST" },
                                      );
                                      setMessage(
                                        result.published
                                          ? "Published: " + result.pr_url
                                          : result.message,
                                      );
                                    });
                                }}
                              >
                                Publish fix PR
                              </button>
                            )}
                          </details>
                        </section>
                      )}
                    </>
                  ) : (
                    <div className="empty">
                      <h2>Evidence lives here.</h2>
                      <p>
                        Select a finding to inspect its impact, source, evidence
                        and repair.
                      </p>
                    </div>
                  )}
                </article>
              </div>
            </>
          )}
          {tab === "changes" && (
            <section className="panel">
              <h2>
                {run.review_mode === "project"
                  ? "Project files"
                  : "Changes under review"}
              </h2>
              <p>
                {run.base_sha || "Snapshot"} → {run.head_sha || "Local source"}
              </p>
              {run.coverage.impact && (
                <details open={run.coverage.impact.changes.length > 0}>
                  <summary>
                    Change impact · {run.coverage.impact.changes.length} changed
                    symbols
                  </summary>
                  <p>{run.coverage.impact.limitations}</p>
                  {run.coverage.impact.changes.map((change) => (
                    <div className="evidence" key={change.symbol.id}>
                      <h3>{change.symbol.name}</h3>
                      <button
                        className="file-link"
                        onClick={() =>
                          void perform("Loading changed symbol", async () =>
                            setSource(
                              await request(
                                "/reviews/" +
                                  run.id +
                                  "/source?path=" +
                                  encodeURIComponent(change.symbol.path),
                              ),
                            ),
                          )
                        }
                      >
                        {change.symbol.path}:{change.symbol.start} ↗
                      </button>
                      <h4>Affected callers</h4>
                      {change.callers.length ? (
                        change.callers.map((caller, i) => (
                          <p key={i}>
                            <button
                              className="file-link"
                              onClick={() =>
                                void perform("Loading caller", async () =>
                                  setSource(
                                    await request(
                                      "/reviews/" +
                                        run.id +
                                        "/source?path=" +
                                        encodeURIComponent(caller.path),
                                    ),
                                  ),
                                )
                              }
                            >
                              {caller.path}:{caller.line} ↗
                            </button>{" "}
                            · {caller.relationship.replaceAll("_", " ")}
                          </p>
                        ))
                      ) : (
                        <p>No supported resolved callers found.</p>
                      )}
                      <h4>Related test hints</h4>
                      <p>
                        {change.test_hints.join(", ") ||
                          "No lexical test matches; this does not establish missing coverage."}
                      </p>
                      {findings
                        .filter(
                          (f) =>
                            (f.primary_location.path === change.symbol.path &&
                              f.primary_location.start_line >=
                                change.symbol.start &&
                              f.primary_location.start_line <=
                                change.symbol.end) ||
                            change.callers.some(
                              (c) => c.path === f.primary_location.path,
                            ),
                        )
                        .map((f) => (
                          <button
                            key={f.id}
                            onClick={() => {
                              setSelected(f.id);
                              setTab("findings");
                              setFilter("all");
                              setSeverity("all");
                              setSearch("");
                            }}
                          >
                            Inspect finding: {f.title} ↗
                          </button>
                        ))}
                    </div>
                  ))}
                  {run.coverage.impact.deleted_symbols.map((symbol, i) => (
                    <p key={i}>
                      Removed declaration:{" "}
                      <code>
                        {symbol.path}::{symbol.name}
                      </code>{" "}
                      (base snapshot)
                    </p>
                  ))}
                </details>
              )}
              <div className="file-list">
                {(run.review_mode === "project"
                  ? run.coverage.source_files || []
                  : run.coverage.changed_files || []
                ).map((path) => (
                  <button
                    key={path}
                    onClick={() =>
                      void perform("Loading source", async () =>
                        setSource(
                          await request(
                            "/reviews/" +
                              run.id +
                              "/source?path=" +
                              encodeURIComponent(path),
                          ),
                        ),
                      )
                    }
                  >
                    {path}
                  </button>
                ))}
              </div>
              {source && (
                <pre className="code">
                  {source.path + "\n" + source.content}
                </pre>
              )}
              {run.coverage.diff ? (
                diffView(run.coverage.diff)
              ) : (
                <p>
                  Whole-project reviews inspect a snapshot; there is no change
                  diff.
                </p>
              )}
            </section>
          )}
          {tab === "coverage" && (
            <section className="panel">
              <h2>Know what was reviewed.</h2>
              <p>
                {run.coverage.excluded_files?.length || 0} files excluded from
                findings by repository policy. Policy source:{" "}
                {run.coverage.repository_policy_source || "not recorded"}.
              </p>
              <p>{run.coverage.scope_note}</p>
              {!!run.coverage.source_exclusions?.length && (
                <details>
                  <summary>
                    Not ingested · {run.coverage.source_exclusions.length}{" "}
                    recorded exclusions
                  </summary>
                  <p>
                    Credential paths and configured review outputs are excluded
                    before analysis. This is separate from repository finding
                    policy.
                  </p>
                  {run.coverage.source_exclusions.map((entry, i) => (
                    <p key={i}>
                      <code>{entry.path}</code> · {entry.reason} · {entry.side}
                    </p>
                  ))}
                </details>
              )}
              <div className="metrics">
                <div>
                  <strong>{run.coverage.total_files || 0}</strong>
                  <span>Files inventoried</span>
                </div>
                <div>
                  <strong>
                    {run.coverage.project_review?.reviewed_files.length ?? "—"}
                  </strong>
                  <span>Model-reviewed files</span>
                </div>
                <div>
                  <strong>
                    {run.coverage.project_review?.omitted_files.length ?? "—"}
                  </strong>
                  <span>Omitted model files</span>
                </div>
              </div>
              <p>
                Completion means the reported scope was processed, not that the
                project is defect-free.
              </p>
              {!!run.coverage.validation_rejections?.length && <div className="notice"><h3>Source validation needs attention</h3><p>{run.coverage.validation_rejections.length} candidate findings could not be grounded in their cited source ranges.</p>{run.coverage.validation_rejections.map(item=><p key={item.finding_id}><code>{item.path}</code> · {item.reason}</p>)}</div>}
              <h3>Independent verification</h3>
              <p>
                {run.coverage.verification_coverage?.assessed || 0} of{" "}
                {run.coverage.verification_coverage?.requested || 0} requested
                findings assessed;{" "}
                {run.coverage.verification_coverage?.unassessed_ids.length || 0}{" "}
                unassessed.
              </p>
              <h3>Review history</h3>
              <p>
                {run.coverage.finding_lifecycle?.previous_run_id
                  ? "Compared with " +
                    run.coverage.finding_lifecycle.previous_run_id
                  : "First comparable review"}
              </p>
              <div className="stages">
                {Object.entries(
                  (run.coverage.finding_lifecycle?.changes || []).reduce<
                    Record<string, number>
                  >((counts, item) => {
                    counts[item.state] = (counts[item.state] || 0) + 1;
                    return counts;
                  }, {}),
                ).map(([state, count]) => (
                  <span key={state}>
                    {state.replaceAll("_", " ")}: {count}
                  </span>
                ))}
              </div>
              <p>
                Not redetected means the current review did not establish the
                issue; it is not proof of a fix.
              </p>
              <h3>Test coverage questions</h3>
              {run.coverage.test_gaps?.map((g) => (
                <div className="evidence" key={g.path}>
                  <code>{g.path}</code>
                  <p>{g.suggestion}</p>
                </div>
              ))}
              <details>
                <summary>Omitted files and limitations</summary>
                <pre>
                  {run.coverage.project_review?.omitted_files.join("\n") ||
                    "No project omission inventory available."}
                </pre>
                <p>{run.coverage.project_review?.reason}</p>
                <p>{run.coverage.context?.omitted.join("\n")}</p>
              </details>
            </section>
          )}
        </>
      )}
      <footer>
        PROOFLINE <span>Evidence first. Human judgment always.</span>
      </footer>
    </main>
  );
}
