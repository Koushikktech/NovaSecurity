// ── Backend API response types ──

export interface ScanStartResponse {
  scan_id: string;
  status: string;
}

export interface ScanSummary {
  total: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
}

export type ScanMode = "live" | "demo";

export type ScanStatus = "queued" | "running" | "completed" | "failed";

export type PipelineStep =
  | "ingest"
  | "build_index"
  | "build_graph"
  | "targeted_scan"
  | "indexed_sweep"
  | "merge_findings"
  | "red_team"
  | "blue_team"
  | "finalizing"
  | null;

export interface ScanResponse {
  id: string;
  repo_url: string;
  status: ScanStatus;
  current_step: PipelineStep;
  step_index?: number;
  total_steps?: number;
  started_at: string | null;
  completed_at: string | null;
  findings: Finding[] | null;
  graph: GraphData | null;
  summary: ScanSummary | null;
  error: string | null;
}

export interface Finding {
  vulnerability_type?: string;
  severity?: "Critical" | "High" | "Medium" | "Low";
  file?: string;
  line?: number;
  description?: string;
  confidence?: number;
  final_confidence?: number;
  validation_status?: "Confirmed" | "Needs Review" | "Likely False Positive";
  red_team_poc?: string | null;
  red_team_success?: boolean;
  red_team_attack_vector?: string;
  blue_team_disputed?: boolean;
  blue_team_defense?: string | null;
  corroborated?: boolean;
  sources?: string[];
  path?: string[];
  source?: string;
  is_vulnerable?: boolean;
  [key: string]: unknown;
}

export interface FindingsResponse {
  findings: Finding[];
  summary: ScanSummary;
}

export interface ScanPresentation {
  targetLabel: string;
  phaseDetails: Partial<Record<Exclude<PipelineStep, null>, string>>;
  stepLogs: Partial<Record<Exclude<PipelineStep, null>, string[]>>;
}

export type FixJobStatus = "queued" | "running" | "completed" | "failed";

export type FixStep =
  | "prepare_repo"
  | "assemble_context"
  | "generate_patch"
  | "apply_patch"
  | "generate_diff"
  | null;

export interface PullRequestState {
  status: "idle" | "creating" | "created" | "compare_ready" | "failed";
  url: string | null;
  error: string | null;
}

export interface FixStartResponse {
  fix_id: string;
  status: FixJobStatus;
  reused?: boolean;
}

export interface FixJob {
  id: string;
  scan_id: string;
  finding_index: number;
  status: FixJobStatus;
  current_step: FixStep;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  finding: Finding | null;
  branch_name: string | null;
  base_branch: string | null;
  changed_files: string[];
  diff: string | null;
  summary: string | null;
  rationale: string | null;
  tests_to_run: string[];
  compare_url: string | null;
  pr_title: string | null;
  pr_body: string | null;
  commit_sha: string | null;
  pr: PullRequestState;
}

// ── Graph types (matches api.py _build_graph_data output) ──

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  category: "source" | "sink" | "normal" | "attacked";
  file: string;
  line: number;
  degree: number;
  // d3-force simulation properties
  x?: number;
  y?: number;
  z?: number;
  vx?: number;
  vy?: number;
  vz?: number;
  fx?: number | null;
  fy?: number | null;
  fz?: number | null;
  index?: number;
}

export interface GraphLink {
  source: string | GraphNode;
  target: string | GraphNode;
  type: string;
  detected: boolean;
  line: number;
  index?: number;
}

export interface DetectedPath {
  source: string;
  sink: string;
  nodes: string[];
  sanitized: boolean;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
  paths: DetectedPath[];
}

// Resolved link where source/target are node objects
export interface ResolvedLink {
  source: GraphNode;
  target: GraphNode;
  type: string;
  detected: boolean;
  line: number;
}

// ── SSE event types ──

export interface SSEProgressEvent {
  type: "progress";
  step: PipelineStep;
  step_index: number;
  total_steps: number;
  status: ScanStatus;
}

export interface SSECompleteEvent {
  type: "complete";
  summary: ScanSummary;
}

export interface SSEErrorEvent {
  type: "error";
  message: string;
}

export type SSEEvent = SSEProgressEvent | SSECompleteEvent | SSEErrorEvent;
