import type {
  FindingsResponse,
  FixJob,
  FixJobStatus,
  FixStartResponse,
  FixStep,
  GraphData,
  PullRequestState,
  ScanResponse,
  ScanStartResponse,
  SSEEvent,
} from "./types";

function getApiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (configured) {
    return configured.replace(/\/+$/, "");
  }

  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }

  return "http://127.0.0.1:8000";
}

async function readErrorResponse(res: Response): Promise<string> {
  const text = await res.text();
  if (!text) {
    return `Request failed with status ${res.status}`;
  }

  try {
    const parsed = JSON.parse(text) as { detail?: unknown; message?: unknown };
    if (typeof parsed.detail === "string" && parsed.detail.trim()) {
      return parsed.detail;
    }
    if (typeof parsed.message === "string" && parsed.message.trim()) {
      return parsed.message;
    }
  } catch {
    // Fall back to the raw response body when it is not JSON.
  }

  return text;
}

function normalizeText(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function normalizeStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string");
}

function isFixJobStatus(value: unknown): value is FixJobStatus {
  return (
    value === "queued" ||
    value === "running" ||
    value === "completed" ||
    value === "failed"
  );
}

function isFixStep(value: unknown): value is FixStep {
  return (
    value === "prepare_repo" ||
    value === "assemble_context" ||
    value === "generate_patch" ||
    value === "apply_patch" ||
    value === "generate_diff" ||
    value === null
  );
}

function isPullRequestStatus(value: unknown): value is PullRequestState["status"] {
  return (
    value === "idle" ||
    value === "creating" ||
    value === "created" ||
    value === "compare_ready" ||
    value === "failed"
  );
}

function normalizePullRequestState(value: unknown): PullRequestState {
  if (!value || typeof value !== "object") {
    return { status: "idle", url: null, error: null };
  }

  const record = value as Record<string, unknown>;
  return {
    status: isPullRequestStatus(record.status) ? record.status : "idle",
    url: normalizeText(record.url),
    error: normalizeText(record.error),
  };
}

function normalizeFixJob(value: unknown): FixJob {
  const record =
    value && typeof value === "object" ? (value as Record<string, unknown>) : {};

  return {
    id: typeof record.id === "string" ? record.id : "",
    scan_id: typeof record.scan_id === "string" ? record.scan_id : "",
    finding_index:
      typeof record.finding_index === "number" ? record.finding_index : 0,
    status: isFixJobStatus(record.status) ? record.status : "failed",
    current_step: isFixStep(record.current_step) ? record.current_step : null,
    started_at: normalizeText(record.started_at),
    completed_at: normalizeText(record.completed_at),
    error: normalizeText(record.error),
    finding:
      record.finding && typeof record.finding === "object"
        ? (record.finding as FixJob["finding"])
        : null,
    branch_name: normalizeText(record.branch_name),
    base_branch: normalizeText(record.base_branch),
    changed_files: normalizeStringArray(record.changed_files),
    diff: normalizeText(record.diff),
    summary: normalizeText(record.summary),
    rationale: normalizeText(record.rationale),
    tests_to_run: normalizeStringArray(record.tests_to_run),
    compare_url: normalizeText(record.compare_url),
    pr_title: normalizeText(record.pr_title),
    pr_body: normalizeText(record.pr_body),
    commit_sha: normalizeText(record.commit_sha),
    pr: normalizePullRequestState(record.pr),
  };
}

export async function startScan(repoUrl: string): Promise<ScanStartResponse> {
  const res = await fetch(`${getApiBase()}/api/scan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ repo_url: repoUrl }),
  });
  if (!res.ok) {
    const err = await readErrorResponse(res);
    throw new Error(`Failed to start scan: ${res.status} ${err}`);
  }
  return res.json();
}

export async function startDemoScan(repoKey: string): Promise<ScanStartResponse> {
  const res = await fetch(`${getApiBase()}/api/demo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ repo_key: repoKey }),
  });
  if (!res.ok) {
    const err = await readErrorResponse(res);
    throw new Error(`Failed to start demo scan: ${res.status} ${err}`);
  }
  return res.json();
}

export async function getScanStatus(scanId: string): Promise<ScanResponse> {
  const res = await fetch(`${getApiBase()}/api/scan/${scanId}`, {
    cache: "no-store",
  });
  if (!res.ok) {
    const err = await readErrorResponse(res);
    throw new Error(`Failed to get scan status: ${res.status} ${err}`);
  }
  return res.json();
}

export async function getScanFindings(
  scanId: string
): Promise<FindingsResponse> {
  const res = await fetch(`${getApiBase()}/api/scan/${scanId}/findings`, {
    cache: "no-store",
  });
  if (!res.ok) {
    const err = await readErrorResponse(res);
    throw new Error(`Failed to get findings: ${res.status} ${err}`);
  }
  return res.json();
}

export async function getScanGraph(scanId: string): Promise<GraphData> {
  const res = await fetch(`${getApiBase()}/api/scan/${scanId}/graph`, {
    cache: "no-store",
  });
  if (!res.ok) {
    const err = await readErrorResponse(res);
    throw new Error(`Failed to get graph: ${res.status} ${err}`);
  }
  return res.json();
}

export async function startFix(
  scanId: string,
  findingIndex: number
): Promise<FixStartResponse> {
  const res = await fetch(`${getApiBase()}/api/scan/${scanId}/fix`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ finding_index: findingIndex }),
  });
  if (!res.ok) {
    const err = await readErrorResponse(res);
    throw new Error(`Failed to start fix: ${res.status} ${err}`);
  }
  return res.json();
}

export async function getFixStatus(fixId: string): Promise<FixJob> {
  const res = await fetch(`${getApiBase()}/api/fix/${fixId}`, {
    cache: "no-store",
  });
  if (!res.ok) {
    const err = await readErrorResponse(res);
    throw new Error(`Failed to get fix status: ${res.status} ${err}`);
  }
  return normalizeFixJob(await res.json());
}

export async function createPullRequest(fixId: string): Promise<FixJob> {
  const res = await fetch(`${getApiBase()}/api/fix/${fixId}/pull-request`, {
    method: "POST",
  });
  if (!res.ok) {
    const err = await readErrorResponse(res);
    throw new Error(`Failed to create pull request: ${res.status} ${err}`);
  }
  return normalizeFixJob(await res.json());
}

export function streamScanProgress(
  scanId: string,
  onEvent: (event: SSEEvent) => void,
  onError?: (err: Error) => void
): () => void {
  const url = `${getApiBase()}/api/scan/${scanId}/stream`;

  let aborted = false;

  async function connect() {
    try {
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok || !res.body) {
        throw new Error(`SSE connection failed: ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (!aborted) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) {
            continue;
          }

          const data = line.slice(6).trim();
          if (!data) {
            continue;
          }

          try {
            const event: SSEEvent = JSON.parse(data);
            onEvent(event);

            if (event.type === "complete" || event.type === "error") {
              aborted = true;
              await reader.cancel();
              return;
            }
          } catch {
            // Skip malformed JSON frames and keep the stream alive.
          }
        }
      }
    } catch (err) {
      if (!aborted) {
        onError?.(err instanceof Error ? err : new Error(String(err)));
      }
    }
  }

  void connect();

  return () => {
    aborted = true;
  };
}
