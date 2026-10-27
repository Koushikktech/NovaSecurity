"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  Crosshair,
  ExternalLink,
  FileCode2,
  FileText,
  GitBranch,
  Github,
  LoaderCircle,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { DiffViewer } from "./DiffViewer";
import { Modal } from "../ui/Modal";
import type { Finding, FixJob } from "../../lib/types";

const severityStyles: Record<string, string> = {
  Critical: "text-red-400 bg-red-500/10 border-red-500/25",
  High: "text-orange-400 bg-orange-500/10 border-orange-500/25",
  Medium: "text-yellow-400 bg-yellow-500/10 border-yellow-500/25",
  Low: "text-blue-400 bg-blue-500/10 border-blue-500/25",
};

const validationStyles: Record<string, string> = {
  Confirmed: "text-red-400 bg-red-500/10 border-red-500/20",
  "Needs Review": "text-yellow-400 bg-yellow-500/10 border-yellow-500/20",
  "Likely False Positive": "text-green-400 bg-green-500/10 border-green-500/20",
};

const fixStepLabels: Record<string, string> = {
  prepare_repo: "Preparing an isolated git workspace",
  assemble_context: "Collecting full-file remediation context",
  generate_patch: "Asking NOVA to reason through a secure fix",
  apply_patch: "Applying the generated file updates",
  generate_diff: "Building a git-style diff preview",
};

interface FindingCardProps {
  finding: Finding;
  index: number;
  findingIndex: number;
  canCreatePullRequest: boolean;
  fixJob?: FixJob;
  onFix: (findingIndex: number) => Promise<void>;
  onCreatePullRequest: (findingIndex: number) => Promise<void>;
}

export function FindingCard({
  finding,
  index,
  findingIndex,
  canCreatePullRequest,
  fixJob,
  onFix,
  onCreatePullRequest,
}: FindingCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [isDiffModalOpen, setIsDiffModalOpen] = useState(false);

  const severity = finding.severity || "Medium";
  const title = finding.vulnerability_type || "Unknown Vulnerability";
  const fileLocation = finding.file
    ? `${finding.file}${finding.line ? `:${finding.line}` : ""}`
    : "Unknown";
  const confidence = finding.final_confidence
    ? Math.round(finding.final_confidence * 100)
    : finding.confidence
      ? Math.round(
          typeof finding.confidence === "number" && finding.confidence <= 1
            ? finding.confidence * 100
            : (finding.confidence as number)
        )
      : 0;
  const description = finding.description || "No description available.";
  const evidence = finding.red_team_poc || null;
  const validationStatus = finding.validation_status;
  const pathNodes = finding.path ?? [];
  const pullRequestState = fixJob?.pr ?? {
    status: "idle",
    url: null,
    error: null,
  };
  const changedFiles = fixJob?.changed_files ?? [];
  const testsToRun = fixJob?.tests_to_run ?? [];

  const fixInProgress =
    fixJob?.status === "queued" || fixJob?.status === "running";
  const prInProgress = pullRequestState.status === "creating";
  const actionLabel = fixInProgress
    ? "Generating fix..."
    : fixJob?.status === "completed"
      ? "Regenerate fix"
      : fixJob?.status === "failed"
        ? "Retry fix"
        : "Fix vulnerability";

  const remediationLink = pullRequestState.url ?? fixJob?.compare_url ?? null;
  const remediationLinkLabel =
    pullRequestState.status === "created"
      ? "Open Pull Request"
      : "Open Compare Page";

  return (
    <>
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, delay: index * 0.06 }}
        className="relative overflow-hidden rounded-xl border border-white/10 bg-black/40 shadow-[0_4px_24px_rgba(0,0,0,0.5)] transition-all hover:border-white/20 hover:bg-black/50"
      >
        <div className="absolute top-0 left-0 h-px w-full bg-gradient-to-r from-transparent via-white/10 to-transparent opacity-0 transition-opacity group-hover:opacity-100" />

        <button
          type="button"
          onClick={() => setExpanded((prev) => !prev)}
          className="flex w-full items-start gap-3 px-4 py-4 text-left transition-colors hover:bg-white/[0.02]"
        >
          <div
            className={`mt-0.5 rounded border px-2 py-1 text-[10px] font-semibold uppercase tracking-wider ${severityStyles[severity] || severityStyles.Medium}`}
          >
            {severity}
          </div>

          <div className="min-w-0 flex-1">
            <h3 className="mb-1.5 text-sm font-semibold text-white md:text-base">
              {title}
            </h3>
            <div className="flex flex-wrap items-center gap-3 font-mono text-xs text-gray-400">
              <span className="inline-flex items-center gap-1.5 rounded border border-white/10 bg-white/[0.03] px-2 py-1">
                <FileText className="h-3 w-3 text-blue-400" />
                {fileLocation}
              </span>
              <span className="inline-flex items-center gap-1.5 rounded border border-white/10 bg-white/[0.03] px-2 py-1">
                <Crosshair className="h-3 w-3 text-red-400" />
                {confidence}%
              </span>
              {validationStatus && (
                <span
                  className={`inline-flex items-center gap-1.5 rounded border px-2 py-1 text-[10px] font-semibold ${validationStyles[validationStatus] || ""}`}
                >
                  {validationStatus === "Confirmed" ? (
                    <ShieldCheck className="h-3 w-3" />
                  ) : (
                    <AlertTriangle className="h-3 w-3" />
                  )}
                  {validationStatus}
                </span>
              )}
              {finding.corroborated && (
                <span className="rounded border border-purple-500/20 bg-purple-500/10 px-2 py-1 text-[10px] font-semibold text-purple-400">
                  CORROBORATED
                </span>
              )}
              {fixJob?.status === "completed" && (
                <span className="rounded border border-emerald-500/20 bg-emerald-500/10 px-2 py-1 text-[10px] font-semibold text-emerald-400">
                  FIX READY
                </span>
              )}
            </div>
          </div>

          <motion.span
            animate={{ rotate: expanded ? 180 : 0 }}
            transition={{ duration: 0.2 }}
            className="mt-1 text-gray-500"
          >
            <ChevronDown className="h-4 w-4" />
          </motion.span>
        </button>

        <AnimatePresence initial={false}>
          {expanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="border-t border-white/10 bg-black/25"
            >
              <div className="space-y-5 p-4">
                <div>
                  <p className="mb-1.5 text-[10px] uppercase tracking-wider text-gray-500">
                    Description
                  </p>
                  <p className="text-sm leading-relaxed text-gray-300">
                    {description}
                  </p>
                </div>

                {evidence && (
                  <div>
                    <p className="mb-1.5 text-[10px] uppercase tracking-wider text-gray-500">
                      Red Team PoC
                    </p>
                    <pre className="overflow-x-auto rounded border border-white/10 bg-black/40 p-3 font-mono text-xs whitespace-pre-wrap text-gray-300">
                      {evidence}
                    </pre>
                  </div>
                )}

                {finding.red_team_attack_vector && (
                  <div>
                    <p className="mb-1.5 text-[10px] uppercase tracking-wider text-gray-500">
                      Attack Vector
                    </p>
                    <p className="break-words font-mono text-xs text-red-300">
                      {finding.red_team_attack_vector}
                    </p>
                  </div>
                )}

                {pathNodes.length > 0 && (
                  <div>
                    <p className="mb-1.5 text-[10px] uppercase tracking-wider text-gray-500">
                      Data Flow
                    </p>
                    <div className="flex flex-wrap items-center gap-1.5 font-mono text-xs">
                      {pathNodes.map((node, pathIndex) => (
                        <span
                          key={`${node}-${pathIndex}`}
                          className="flex items-center gap-1.5"
                        >
                          <span className="rounded border border-purple-500/15 bg-purple-500/10 px-1.5 py-0.5 text-purple-300">
                            {node.split("::").pop()}
                          </span>
                          {pathIndex < pathNodes.length - 1 && (
                            <ArrowRight className="h-3 w-3 text-gray-600" />
                          )}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {finding.blue_team_defense && (
                  <div>
                    <p className="mb-1.5 text-[10px] uppercase tracking-wider text-gray-500">
                      Blue Team Analysis
                    </p>
                    <p className="text-xs leading-relaxed text-gray-400">
                      {finding.blue_team_defense}
                    </p>
                  </div>
                )}

                {finding.sources && finding.sources.length > 0 && (
                  <div className="flex items-center gap-2 border-t border-white/5 pt-2">
                    <span className="text-[10px] uppercase tracking-wider text-gray-600">
                      Found by:
                    </span>
                    {finding.sources.map((source) => (
                      <span
                        key={source}
                        className="rounded border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] text-gray-400"
                      >
                        {source.replace("_", " ")}
                      </span>
                    ))}
                  </div>
                )}

                <div className="overflow-hidden rounded-xl border border-emerald-500/20 bg-emerald-500/[0.03] shadow-[inset_0_0_20px_rgba(16,185,129,0.02)]">
                  <div className="flex items-center justify-between gap-4 border-b border-emerald-500/10 bg-gradient-to-r from-emerald-500/[0.05] to-transparent px-5 py-4">
                    <div>
                      <p className="text-[10px] uppercase tracking-[0.25em] text-emerald-400">
                        NOVA Remediation
                      </p>
                      <p className="mt-1 text-sm text-gray-300">
                        Review the finding, then ask NOVA to generate and apply a patch on a new branch.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => void onFix(findingIndex)}
                      disabled={fixInProgress || prInProgress}
                      className="inline-flex items-center gap-2 rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-4 py-2 text-sm font-medium text-emerald-300 transition-all hover:bg-emerald-500/15 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {fixInProgress ? (
                        <LoaderCircle className="h-4 w-4 animate-spin" />
                      ) : (
                        <Sparkles className="h-4 w-4" />
                      )}
                      {actionLabel}
                    </button>
                  </div>

                  {!fixJob && (
                    <div className="px-4 py-4 text-sm text-gray-400">
                      NOVA will receive the verified finding, the supporting
                      analysis, and the full contents of the affected files so it
                      can produce a minimal security patch.
                    </div>
                  )}

                  {fixJob && (
                    <div className="space-y-4 px-4 py-4">
                      {(fixJob.status === "queued" ||
                        fixJob.status === "running") && (
                        <div className="rounded-lg border border-white/10 bg-black/30 px-4 py-3">
                          <div className="flex items-center gap-2 text-sm text-white">
                            <LoaderCircle className="h-4 w-4 animate-spin text-emerald-400" />
                            Building a remediation branch
                          </div>
                          <p className="mt-2 text-xs text-gray-400">
                            {fixStepLabels[fixJob.current_step || ""] ||
                              "NOVA is working through the patch."}
                          </p>
                        </div>
                      )}

                      {fixJob.status === "failed" && (
                        <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">
                          <div className="flex items-center gap-2 font-medium">
                            <AlertTriangle className="h-4 w-4" />
                            Remediation failed
                          </div>
                          <p className="mt-2 text-xs text-red-100/80">
                            {fixJob.error ||
                              "NOVA could not produce a safe fix for this finding."}
                          </p>
                        </div>
                      )}

                      {fixJob.status === "completed" && (
                        <>
                          <div className="rounded-lg border border-emerald-500/20 bg-black/30 p-4">
                            <div className="flex items-center gap-2 text-sm font-medium text-emerald-300">
                              <CheckCircle2 className="h-4 w-4" />
                              Fix generated successfully
                            </div>

                            {fixJob.summary && (
                              <p className="mt-3 text-sm leading-relaxed text-gray-300">
                                {fixJob.summary}
                              </p>
                            )}

                            {fixJob.rationale && (
                              <p className="mt-3 text-xs leading-relaxed text-gray-400">
                                {fixJob.rationale}
                              </p>
                            )}

                            <p className="mt-3 text-xs text-emerald-100/70">
                              Review the diff and run the suggested verification
                              steps before you merge or open a pull request.
                            </p>

                            <div className="mt-4 flex flex-wrap gap-2">
                              {fixJob.branch_name && (
                                <span className="inline-flex items-center gap-1.5 rounded border border-white/10 bg-white/[0.03] px-2.5 py-1 font-mono text-xs text-gray-300">
                                  <GitBranch className="h-3 w-3 text-emerald-400" />
                                  {fixJob.branch_name}
                                </span>
                              )}
                              {fixJob.base_branch && (
                                <span className="inline-flex items-center gap-1.5 rounded border border-white/10 bg-white/[0.03] px-2.5 py-1 font-mono text-xs text-gray-400">
                                  base: {fixJob.base_branch}
                                </span>
                              )}
                              {fixJob.commit_sha && (
                                <span className="inline-flex items-center gap-1.5 rounded border border-white/10 bg-white/[0.03] px-2.5 py-1 font-mono text-xs text-gray-400">
                                  commit: {fixJob.commit_sha.slice(0, 8)}
                                </span>
                              )}
                            </div>

                            {changedFiles.length > 0 && (
                              <div className="mt-4">
                                <p className="mb-2 text-[10px] uppercase tracking-wider text-gray-500">
                                  Changed Files
                                </p>
                                <div className="flex flex-wrap gap-2">
                                  {changedFiles.map((file) => (
                                    <span
                                      key={file}
                                      className="inline-flex items-center gap-1.5 rounded border border-white/10 bg-white/[0.03] px-2.5 py-1 font-mono text-xs text-gray-300"
                                    >
                                      <FileCode2 className="h-3 w-3 text-cyan-400" />
                                      {file}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}

                            {testsToRun.length > 0 && (
                              <div className="mt-4">
                                <p className="mb-2 text-[10px] uppercase tracking-wider text-gray-500">
                                  Suggested Verification
                                </p>
                                <div className="space-y-2">
                                  {testsToRun.map((command) => (
                                    <pre
                                      key={command}
                                      className="overflow-x-auto rounded border border-white/10 bg-black/40 px-3 py-2 font-mono text-xs whitespace-pre-wrap text-gray-300"
                                    >
                                      {command}
                                    </pre>
                                  ))}
                                </div>
                              </div>
                            )}

                            <div className="mt-5 flex flex-wrap gap-3">
                              {canCreatePullRequest ? (
                                <button
                                  type="button"
                                  onClick={() => void onCreatePullRequest(findingIndex)}
                                  disabled={
                                    prInProgress ||
                                    pullRequestState.status === "created"
                                  }
                                  className="inline-flex items-center gap-2 rounded-lg border border-white/15 bg-white/5 px-4 py-2 text-sm text-white transition-all hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-60"
                                >
                                  {prInProgress ? (
                                    <LoaderCircle className="h-4 w-4 animate-spin" />
                                  ) : (
                                    <Github className="h-4 w-4" />
                                  )}
                                  {prInProgress
                                    ? "Creating PR..."
                                    : pullRequestState.status === "created"
                                      ? "Pull Request Created"
                                      : pullRequestState.status === "compare_ready"
                                        ? "Retry GitHub PR"
                                        : "Create GitHub PR"}
                                </button>
                              ) : (
                                <div className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-4 py-2 text-sm text-gray-400">
                                  <Github className="h-4 w-4" />
                                  Demo scan keeps remediation local
                                </div>
                              )}

                              {remediationLink && (
                                <a
                                  href={remediationLink}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="inline-flex items-center gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-4 py-2 text-sm text-emerald-300 transition-all hover:bg-emerald-500/15"
                                >
                                  <ExternalLink className="h-4 w-4" />
                                  {remediationLinkLabel}
                                </a>
                              )}
                            </div>

                            {pullRequestState.error && (
                              <div className="mt-4 rounded-lg border border-yellow-500/20 bg-yellow-500/10 px-3 py-2 text-xs text-yellow-100/90">
                                {pullRequestState.error}
                              </div>
                            )}
                          </div>

                          {fixJob.diff && (
                            <div className="mt-6 flex items-center justify-between rounded-xl border border-emerald-500/20 bg-black/40 p-4 shadow-inner">
                              <div className="flex-1">
                                <h4 className="flex items-center gap-2 text-sm font-semibold text-emerald-100">
                                  <Sparkles className="h-4 w-4 text-emerald-400" />
                                  Review Patch Preview
                                </h4>
                                <p className="mt-1 max-w-sm text-xs leading-relaxed text-gray-400">
                                  Nova isolated the affected files and prepared a
                                  proposed remediation patch for review.
                                </p>
                              </div>
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  setIsDiffModalOpen(true);
                                }}
                                className="group relative flex items-center gap-2 overflow-hidden rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-5 py-2.5 text-sm font-medium text-emerald-400 transition-all hover:bg-emerald-500/20"
                              >
                                <div className="absolute inset-0 translate-x-[-100%] bg-gradient-to-r from-emerald-400/0 via-emerald-400/10 to-emerald-400/0 transition-transform duration-500 group-hover:translate-x-[100%]" />
                                <FileCode2 className="h-4 w-4" />
                                View Diff Preview
                              </button>
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>

      <Modal
        isOpen={isDiffModalOpen}
        onClose={() => setIsDiffModalOpen(false)}
        maxWidth="max-w-6xl"
      >
        {fixJob?.diff && <DiffViewer diff={fixJob.diff} />}
      </Modal>
    </>
  );
}
