"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  createPullRequest as apiCreatePullRequest,
  getFixStatus,
  startFix as apiStartFix,
} from "../lib/api";
import type { FixJob } from "../lib/types";

type FixJobMap = Record<number, FixJob>;

interface PollState {
  consecutiveErrors: number;
  inFlight: boolean;
  stopped: boolean;
  timeout: ReturnType<typeof setTimeout> | null;
}

type PollRefMap = Record<number, PollState>;

const POLL_INTERVAL_MS = 1500;
const MAX_POLL_ERRORS = 5;

function createQueuedJob(
  scanId: string,
  findingIndex: number,
  fixId: string
): FixJob {
  return {
    id: fixId,
    scan_id: scanId,
    finding_index: findingIndex,
    status: "queued",
    current_step: null,
    started_at: new Date().toISOString(),
    completed_at: null,
    error: null,
    finding: null,
    branch_name: null,
    base_branch: null,
    changed_files: [],
    diff: null,
    summary: null,
    rationale: null,
    tests_to_run: [],
    compare_url: null,
    pr_title: null,
    pr_body: null,
    commit_sha: null,
    pr: {
      status: "idle",
      url: null,
      error: null,
    },
  };
}

function createFailedJob(
  scanId: string,
  findingIndex: number,
  fixId: string,
  error: string
): FixJob {
  return {
    ...createQueuedJob(scanId, findingIndex, fixId),
    status: "failed",
    error,
  };
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
}

export interface UseFixesReturn {
  jobs: FixJobMap;
  startFix: (findingIndex: number) => Promise<void>;
  createPullRequest: (findingIndex: number) => Promise<void>;
  reset: () => void;
}

interface UseFixesOptions {
  allowPullRequestCreation?: boolean;
}

export function useFixes(
  scanId: string | null,
  options: UseFixesOptions = {}
): UseFixesReturn {
  const [jobs, setJobs] = useState<FixJobMap>({});
  const pollRefs = useRef<PollRefMap>({});
  const allowPullRequestCreation = options.allowPullRequestCreation ?? true;

  const stopPolling = useCallback((findingIndex: number) => {
    const poller = pollRefs.current[findingIndex];
    if (!poller) {
      return;
    }

    poller.stopped = true;
    if (poller.timeout) {
      clearTimeout(poller.timeout);
    }
    delete pollRefs.current[findingIndex];
  }, []);

  const clearAllPolling = useCallback(() => {
    Object.values(pollRefs.current).forEach((poller) => {
      poller.stopped = true;
      if (poller.timeout) {
        clearTimeout(poller.timeout);
      }
    });
    pollRefs.current = {};
  }, []);

  useEffect(() => {
    clearAllPolling();
    setJobs({});
  }, [scanId, clearAllPolling]);

  useEffect(() => {
    return () => {
      clearAllPolling();
    };
  }, [clearAllPolling]);

  const startPolling = useCallback(
    (findingIndex: number, fixId: string) => {
      stopPolling(findingIndex);

      const poller: PollState = {
        consecutiveErrors: 0,
        inFlight: false,
        stopped: false,
        timeout: null,
      };
      pollRefs.current[findingIndex] = poller;

      const syncJob = async () => {
        if (poller.stopped || poller.inFlight) {
          return;
        }

        poller.inFlight = true;
        try {
          const job = await getFixStatus(fixId);
          poller.consecutiveErrors = 0;
          setJobs((prev) => ({
            ...prev,
            [findingIndex]: job,
          }));

          if (job.status === "completed" || job.status === "failed") {
            stopPolling(findingIndex);
            return;
          }
        } catch (error) {
          poller.consecutiveErrors += 1;
          if (poller.consecutiveErrors >= MAX_POLL_ERRORS) {
            stopPolling(findingIndex);
            setJobs((prev) => ({
              ...prev,
              [findingIndex]: {
                ...(prev[findingIndex] ??
                  createQueuedJob(
                    scanId ?? "unavailable",
                    findingIndex,
                    fixId
                  )),
                id: fixId,
                status: "failed",
                current_step: null,
                error: getErrorMessage(
                  error,
                  "Lost connection while tracking the remediation job."
                ),
              },
            }));
            return;
          }
        } finally {
          poller.inFlight = false;
        }

        if (!poller.stopped) {
          poller.timeout = setTimeout(() => {
            void syncJob();
          }, POLL_INTERVAL_MS);
        }
      };

      void syncJob();
    },
    [scanId, stopPolling]
  );

  const startFix = useCallback(
    async (findingIndex: number) => {
      if (!scanId) {
        setJobs((prev) => ({
          ...prev,
          [findingIndex]: createFailedJob(
            "unavailable",
            findingIndex,
            `local-${findingIndex}`,
            "Remediation is temporarily unavailable for this scan."
          ),
        }));
        return;
      }

      try {
        const response = await apiStartFix(scanId, findingIndex);
        setJobs((prev) => ({
          ...prev,
          [findingIndex]: createQueuedJob(scanId, findingIndex, response.fix_id),
        }));
        startPolling(findingIndex, response.fix_id);
      } catch (error) {
        setJobs((prev) => ({
          ...prev,
          [findingIndex]: createFailedJob(
            scanId,
            findingIndex,
            `local-${findingIndex}`,
            getErrorMessage(error, "Failed to start remediation.")
          ),
        }));
      }
    },
    [scanId, startPolling]
  );

  const createPullRequest = useCallback(
    async (findingIndex: number) => {
      const job = jobs[findingIndex];
      if (!job) {
        setJobs((prev) => ({
          ...prev,
          [findingIndex]: createFailedJob(
            scanId ?? "unavailable",
            findingIndex,
            `local-pr-${findingIndex}`,
            "No remediation job exists for this finding yet."
          ),
        }));
        return;
      }

      if (job.pr.status === "creating") {
        return;
      }

      if (!allowPullRequestCreation) {
        setJobs((prev) => ({
          ...prev,
          [findingIndex]: {
            ...job,
            pr: {
              status: "failed",
              url: null,
              error: "Pull request creation is unavailable for this scan.",
            },
          },
        }));
        return;
      }

      setJobs((prev) => ({
        ...prev,
        [findingIndex]: {
          ...job,
          pr: {
            status: "creating",
            url: job.pr.url,
            error: null,
          },
        },
      }));

      try {
        const updated = await apiCreatePullRequest(job.id);
        setJobs((prev) => ({
          ...prev,
          [findingIndex]: updated,
        }));
      } catch (error) {
        setJobs((prev) => ({
          ...prev,
          [findingIndex]: {
            ...(prev[findingIndex] ?? job),
            pr: {
              status: "failed",
              url: prev[findingIndex]?.pr.url ?? job.pr.url,
              error: getErrorMessage(error, "Failed to create pull request."),
            },
          },
        }));
      }
    },
    [allowPullRequestCreation, jobs, scanId]
  );

  const reset = useCallback(() => {
    clearAllPolling();
    setJobs({});
  }, [clearAllPolling]);

  return {
    jobs,
    startFix,
    createPullRequest,
    reset,
  };
}
