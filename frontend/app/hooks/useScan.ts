"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  getScanFindings,
  getScanGraph,
  getScanStatus,
  startDemoScan as apiStartDemoScan,
  startScan as apiStartScan,
  streamScanProgress,
} from "../lib/api";
import type {
  Finding,
  GraphData,
  PipelineStep,
  ScanMode,
  ScanPresentation,
  ScanStatus,
  ScanSummary,
  SSEEvent,
} from "../lib/types";

const DEFAULT_TOTAL_STEPS = 8;
const DEMO_PIPELINE_STEPS: Exclude<PipelineStep, "finalizing" | null>[] = [
  "ingest",
  "build_index",
  "build_graph",
  "targeted_scan",
  "indexed_sweep",
  "merge_findings",
  "red_team",
  "blue_team",
];

const DEMO_REPO_URLS: Record<string, string> = {
  "lets-be-bad-guys": "https://github.com/mpirnat/lets-be-bad-guys",
  vulpy: "https://github.com/fportantier/vulpy",
};

const sleep = (ms: number) =>
  new Promise((resolve) => window.setTimeout(resolve, ms));

function formatRepoLabel(repoUrl: string): string {
  return repoUrl.replace(/^https?:\/\//, "").replace(/\.git$/, "");
}

function buildDemoPresentation(repoKey: string): ScanPresentation {
  const repoUrl = DEMO_REPO_URLS[repoKey] ?? repoKey;
  const targetLabel = formatRepoLabel(repoUrl);
  return {
    targetLabel,
    phaseDetails: {
      ingest:
        "Loading the retained demo repository snapshot and the pre-run scan artifact.",
      build_index:
        "Rehydrating the code index and file priority map captured during the recorded scan.",
      build_graph:
        "Restoring the recorded data-flow graph and vulnerable path evidence from the real scan.",
      targeted_scan:
        "Replaying the highest-confidence vulnerable paths confirmed during the targeted analysis.",
      indexed_sweep:
        "Cross-checking the same high-priority files and findings surfaced during the indexed sweep.",
      merge_findings:
        "Reconstructing the merged report from the recorded targeted and sweep findings.",
      red_team:
        "Replaying the exploitability checks and proof-of-concept results captured in the scan artifact.",
      blue_team:
        "Applying the same defensive review and confidence calibration used in the recorded run.",
      finalizing:
        "Preparing the recorded findings, graph, and repo context so remediation stays attached to this scan.",
    },
    stepLogs: {
      ingest: [
        `[SYS] Loading pre-run scan artifact for ${targetLabel}.`,
        "[INGEST] Restoring retained repository files for remediation.",
        "[INGEST] Recorded demo scan context attached.",
      ],
      build_index: [
        "[IDX] Rehydrating stored code index and import map.",
        "[IDX] Rebuilding file priority metadata from the recorded scan.",
        "[IDX] Demo repository context is ready for report playback.",
      ],
      build_graph: [
        "[GRAPH] Restoring retained source-to-sink graph evidence.",
        "[GRAPH] Replaying vulnerable paths confirmed in the pre-run scan.",
        "[GRAPH] Graph evidence is being attached to the report context.",
      ],
      targeted_scan: [
        "[NOVA] Reviewing targeted findings from the recorded scan run.",
        "[NOVA] Replaying the highest-confidence vulnerable paths.",
        "[NOVA] Loading the original targeted reasoning for these findings.",
      ],
      indexed_sweep: [
        "[SWEEP] Cross-checking retained findings against the indexed sweep output.",
        "[SWEEP] Rehydrating additional evidence from high-priority files.",
        "[SWEEP] Sweep results are being merged into the recorded report.",
      ],
      merge_findings: [
        "[MERGE] Deduplicating recorded findings into the final report set.",
        "[MERGE] Corroborating findings across targeted and sweep sources.",
        "[MERGE] Final report candidates restored from the scan artifact.",
      ],
      red_team: [
        "[RED] Replaying stored proof-of-concept and exploitability analysis.",
        "[RED] Restoring attack vectors confirmed during the original run.",
        "[RED] Red-team evidence is now attached to each retained finding.",
      ],
      blue_team: [
        "[BLUE] Replaying defensive review and dispute analysis.",
        "[BLUE] Restoring final confidence calibration from the recorded run.",
        "[BLUE] Validation state is being applied to the retained findings.",
      ],
      finalizing: [
        "[SYS] Packaging findings, graph, and remediation workspace context.",
        `[SYS] Report ready for ${targetLabel}.`,
      ],
    },
  };
}

export interface UseScanReturn {
  scanId: string | null;
  scanMode: ScanMode | null;
  scanPresentation: ScanPresentation | null;
  status: ScanStatus | null;
  currentStep: PipelineStep;
  stepIndex: number;
  totalSteps: number;
  findings: Finding[];
  summary: ScanSummary | null;
  graphData: GraphData | null;
  error: string | null;
  isLoading: boolean;
  startScan: (repoUrl: string) => Promise<void>;
  startDemoScan: (repoKey: string) => Promise<void>;
  reset: () => void;
}

export function useScan(): UseScanReturn {
  const [scanId, setScanId] = useState<string | null>(null);
  const [scanMode, setScanMode] = useState<ScanMode | null>(null);
  const [scanPresentation, setScanPresentation] =
    useState<ScanPresentation | null>(null);
  const [status, setStatus] = useState<ScanStatus | null>(null);
  const [currentStep, setCurrentStep] = useState<PipelineStep>(null);
  const [stepIndex, setStepIndex] = useState(0);
  const [totalSteps, setTotalSteps] = useState(DEFAULT_TOTAL_STEPS);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [summary, setSummary] = useState<ScanSummary | null>(null);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const cleanupRef = useRef<(() => void) | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const runTokenRef = useRef(0);

  const isRunActive = useCallback((token: number) => {
    return runTokenRef.current === token;
  }, []);

  const clearActiveRun = useCallback(() => {
    runTokenRef.current += 1;
    cleanupRef.current?.();
    cleanupRef.current = null;
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      clearActiveRun();
    };
  }, [clearActiveRun]);

  const resetState = useCallback(() => {
    setScanId(null);
    setScanMode(null);
    setScanPresentation(null);
    setStatus(null);
    setCurrentStep(null);
    setStepIndex(0);
    setTotalSteps(DEFAULT_TOTAL_STEPS);
    setFindings([]);
    setSummary(null);
    setGraphData(null);
    setError(null);
    setIsLoading(false);
  }, []);

  const beginRun = useCallback(
    (mode: ScanMode, total = DEFAULT_TOTAL_STEPS) => {
      clearActiveRun();
      const token = runTokenRef.current;
      setScanId(null);
      setScanMode(mode);
      setScanPresentation(null);
      setStatus(null);
      setCurrentStep(null);
      setStepIndex(0);
      setTotalSteps(total);
      setFindings([]);
      setSummary(null);
      setGraphData(null);
      setError(null);
      setIsLoading(true);
      return token;
    },
    [clearActiveRun]
  );

  const finalizeRemoteScan = useCallback(
    async (id: string, token: number, summaryFromEvent?: ScanSummary | null) => {
      let lastError: Error | null = null;

      for (let attempt = 0; attempt < 6; attempt += 1) {
        if (!isRunActive(token)) {
          return;
        }

        try {
          const findingsRes = await getScanFindings(id);
          let graphRes: GraphData | null = null;

          try {
            graphRes = await getScanGraph(id);
          } catch {
            graphRes = null;
          }

          if (!isRunActive(token)) {
            return;
          }

          setFindings(findingsRes.findings);
          setSummary(findingsRes.summary ?? summaryFromEvent ?? null);
          setGraphData(graphRes);
          setCurrentStep(null);
          setStepIndex(DEFAULT_TOTAL_STEPS);
          setStatus("completed");
          setIsLoading(false);
          return;
        } catch (err) {
          lastError =
            err instanceof Error
              ? err
              : new Error("Failed to load scan results");
        }

        await sleep(250 * (attempt + 1));
      }

      if (!isRunActive(token)) {
        return;
      }

      setStatus("failed");
      setCurrentStep(null);
      setError(
        lastError?.message ??
          "Scan completed, but the report could not be loaded."
      );
      setIsLoading(false);
    },
    [isRunActive]
  );

  const startPolling = useCallback(
    (id: string, token: number) => {
      pollRef.current = setInterval(async () => {
        if (!isRunActive(token)) {
          if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
          return;
        }

        try {
          const scan = await getScanStatus(id);
          if (!isRunActive(token)) {
            return;
          }

          if (scan.status === "completed") {
            if (pollRef.current) {
              clearInterval(pollRef.current);
              pollRef.current = null;
            }
            setCurrentStep("finalizing");
            setStepIndex(scan.total_steps ?? DEFAULT_TOTAL_STEPS);
            await finalizeRemoteScan(id, token, scan.summary);
            return;
          }

          if (scan.status === "failed") {
            if (pollRef.current) {
              clearInterval(pollRef.current);
              pollRef.current = null;
            }
            setStatus("failed");
            setCurrentStep(null);
            setError(scan.error ?? "Scan failed");
            setIsLoading(false);
            return;
          }

          setStatus(scan.status);
          setCurrentStep(scan.current_step);
          setStepIndex(scan.step_index ?? 0);
          setTotalSteps(scan.total_steps ?? DEFAULT_TOTAL_STEPS);
        } catch {
          // Keep polling on transient errors.
        }
      }, 1500);
    },
    [finalizeRemoteScan, isRunActive]
  );

  const startScan = useCallback(
    async (repoUrl: string) => {
      const token = beginRun("live");

      try {
        const res = await apiStartScan(repoUrl);
        if (!isRunActive(token)) {
          return;
        }

        const id = res.scan_id;
        setScanId(id);
        setStatus("queued");

        const onEvent = (event: SSEEvent) => {
          if (!isRunActive(token)) {
            return;
          }

          switch (event.type) {
            case "progress":
              setStatus(event.status);
              setCurrentStep(event.step);
              setStepIndex(event.step_index);
              setTotalSteps(event.total_steps);
              break;
            case "complete":
              setCurrentStep("finalizing");
              setStepIndex(DEFAULT_TOTAL_STEPS);
              void finalizeRemoteScan(id, token, event.summary);
              break;
            case "error":
              setStatus("failed");
              setCurrentStep(null);
              setError(event.message);
              setIsLoading(false);
              break;
          }
        };

        const onSSEError = () => {
          if (!isRunActive(token)) {
            return;
          }
          startPolling(id, token);
        };

        cleanupRef.current = streamScanProgress(id, onEvent, onSSEError);
      } catch (err) {
        if (!isRunActive(token)) {
          return;
        }

        setStatus("failed");
        setError(err instanceof Error ? err.message : "Failed to start scan");
        setIsLoading(false);
      }
    },
    [beginRun, finalizeRemoteScan, isRunActive, startPolling]
  );

  const startDemoScan = useCallback(
    async (repoKey: string) => {
      const token = beginRun("demo", DEMO_PIPELINE_STEPS.length);
      setScanPresentation(buildDemoPresentation(repoKey));

      try {
        const res = await apiStartDemoScan(repoKey);
        if (!isRunActive(token)) {
          return;
        }

        const id = res.scan_id;
        setScanId(id);
        setStatus("queued");

        const onEvent = (event: SSEEvent) => {
          if (!isRunActive(token)) {
            return;
          }

          switch (event.type) {
            case "progress":
              setStatus(event.status);
              setCurrentStep(event.step);
              setStepIndex(event.step_index);
              setTotalSteps(event.total_steps);
              break;
            case "complete":
              setCurrentStep("finalizing");
              setStepIndex(DEMO_PIPELINE_STEPS.length);
              void finalizeRemoteScan(id, token, event.summary);
              break;
            case "error":
              setStatus("failed");
              setCurrentStep(null);
              setError(event.message);
              setIsLoading(false);
              break;
          }
        };

        const onSSEError = () => {
          if (!isRunActive(token)) {
            return;
          }
          startPolling(id, token);
        };

        cleanupRef.current = streamScanProgress(id, onEvent, onSSEError);
      } catch (err) {
        if (!isRunActive(token)) {
          return;
        }

        setStatus("failed");
        setCurrentStep(null);
        setError(
          err instanceof Error
            ? err.message
            : "Failed to start demo scan"
        );
        setIsLoading(false);
      }
    },
    [beginRun, finalizeRemoteScan, isRunActive, startPolling]
  );

  const reset = useCallback(() => {
    clearActiveRun();
    resetState();
  }, [clearActiveRun, resetState]);

  return {
    scanId,
    scanMode,
    scanPresentation,
    status,
    currentStep,
    stepIndex,
    totalSteps,
    findings,
    summary,
    graphData,
    error,
    isLoading,
    startScan,
    startDemoScan,
    reset,
  };
}
