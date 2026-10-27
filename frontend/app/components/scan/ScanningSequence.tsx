"use client";

import React, { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Terminal,
  Database,
  Network,
  Cpu,
  ShieldAlert,
  Shield,
  Lock,
  GitMerge,
  Layers,
} from "lucide-react";
import { ScanningBackdrop } from "./ScanningBackdrop";
import type {
  PipelineStep,
  ScanPresentation,
  ScanStatus,
} from "../../lib/types";

interface ScanningSequenceProps {
  currentStep: PipelineStep;
  scanStatus: ScanStatus | null;
  stepIndex: number;
  totalSteps: number;
  scanPresentation: ScanPresentation | null;
  error: string | null;
  onComplete: () => void;
  onError: () => void;
}

interface Phase {
  id: string;
  title: string;
  agent: string;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
  bg: string;
  detail: string;
}

const PHASES: Phase[] = [
  {
    id: "ingest",
    title: "INITIALIZING UPLINK",
    agent: "SYS.INGESTOR",
    icon: Database,
    color: "text-blue-400",
    bg: "bg-blue-500",
    detail: "Cloning target repository. Parsing ASTs with tree-sitter.",
  },
  {
    id: "build_index",
    title: "CODEBASE INDEXING",
    agent: "IDX.BUILDER",
    icon: Layers,
    color: "text-yellow-400",
    bg: "bg-yellow-500",
    detail: "Building codebase index. Mapping functions, classes, imports.",
  },
  {
    id: "build_graph",
    title: "DATA-FLOW CONSTRUCTION",
    agent: "NX.GRAPH",
    icon: Network,
    color: "text-cyan-400",
    bg: "bg-cyan-500",
    detail: "Building source-to-sink graphs. Mapping taint propagation paths.",
  },
  {
    id: "targeted_scan",
    title: "TARGETED VULNERABILITY SCAN",
    agent: "NOVA.HUNTER",
    icon: Cpu,
    color: "text-purple-400",
    bg: "bg-purple-500",
    detail: "Cross-referencing graph paths with adversarial language models.",
  },
  {
    id: "indexed_sweep",
    title: "FULL CODEBASE SWEEP",
    agent: "NOVA.SWEEP",
    icon: Shield,
    color: "text-indigo-400",
    bg: "bg-indigo-500",
    detail: "Sweeping high-priority files for additional vulnerabilities.",
  },
  {
    id: "merge_findings",
    title: "DEDUPLICATION AND MERGE",
    agent: "NOVA.MERGE",
    icon: GitMerge,
    color: "text-teal-400",
    bg: "bg-teal-500",
    detail: "Merging findings from targeted scan and sweep. Calculating confidence.",
  },
  {
    id: "red_team",
    title: "ADVERSARIAL VALIDATION",
    agent: "RED TEAM",
    icon: ShieldAlert,
    color: "text-red-400",
    bg: "bg-red-500",
    detail: "Red team generating proof-of-concept exploits. Testing reachability.",
  },
  {
    id: "blue_team",
    title: "DEFENSIVE ANALYSIS",
    agent: "BLUE TEAM",
    icon: Shield,
    color: "text-emerald-400",
    bg: "bg-emerald-500",
    detail: "Blue team challenging findings. Computing final confidence.",
  },
];

const LOG_POOL: Record<string, string[]> = {
  ingest: [
    "[SYS] Connecting to remote host...",
    "[INGEST] Streaming repository...",
    "[INGEST] AST parsing complete.",
  ],
  build_index: [
    "[IDX] Scanning imports and exports...",
    "[IDX] Mapping function signatures...",
    "[IDX] Index summary generated.",
  ],
  build_graph: [
    "[GRAPH] Initializing directed graph...",
    "[GRAPH] Mapping source and sink nodes...",
    "[GRAPH] Unsanitized paths detected.",
  ],
  targeted_scan: [
    "[NOVA] Initiating targeted scan...",
    "[NOVA] Analyzing high-risk paths...",
    "[NOVA] Vulnerability candidate detected.",
  ],
  indexed_sweep: [
    "[SWEEP] Scanning critical files...",
    "[SWEEP] Reviewing high-risk functions...",
    "[SWEEP] Cross-referencing graph evidence...",
  ],
  merge_findings: [
    "[MERGE] Deduplicating findings...",
    "[MERGE] Corroborating across sources...",
    "[MERGE] Confidence scores calculated.",
  ],
  red_team: [
    "[RED] Constructing exploit payload...",
    "[RED] Testing attack vector reachability...",
    "[RED] Exploit feasibility confirmed.",
  ],
  blue_team: [
    "[BLUE] Counter-analysis initiated...",
    "[BLUE] Checking defensive mechanisms...",
    "[BLUE] Final confidence computed.",
  ],
  finalizing: [
    "[SYS] Assembling final report...",
    "[SYS] Hydrating findings and graph...",
    "[SYS] Report package complete.",
  ],
};

export function ScanningSequence({
  currentStep,
  scanStatus,
  stepIndex,
  totalSteps,
  scanPresentation,
  error,
  onComplete,
  onError,
}: ScanningSequenceProps) {
  const [logs, setLogs] = useState<string[]>([]);
  const displayedPhaseIdx =
    currentStep === "finalizing"
      ? PHASES.length - 1
      : Math.max(
          PHASES.findIndex((phase) => phase.id === currentStep),
          0
        );

  useEffect(() => {
    if (scanStatus === "completed") {
      const timer = setTimeout(onComplete, 1100);
      return () => clearTimeout(timer);
    }

    if (scanStatus === "failed") {
      onError();
    }
  }, [scanStatus, onComplete, onError]);

  useEffect(() => {
    const stepId = currentStep || "ingest";
    const pool =
      scanPresentation?.stepLogs[stepId] ??
      LOG_POOL[stepId] ??
      LOG_POOL.ingest;
    let idx = 0;
    let interval: ReturnType<typeof setInterval> | null = null;
    const start = setTimeout(() => {
      setLogs([pool[idx % pool.length]]);
      idx += 1;

      interval = setInterval(() => {
        setLogs((prev) => [...prev.slice(-7), pool[idx % pool.length]]);
        idx += 1;
      }, 420);
    }, 0);

    return () => {
      clearTimeout(start);
      if (interval) {
        clearInterval(interval);
      }
    };
  }, [currentStep, scanPresentation]);

  const logColor = useCallback((log: string) => {
    if (log.includes("[RED]")) return "text-red-400";
    if (log.includes("[BLUE]")) return "text-blue-400";
    if (log.includes("[GRAPH]")) return "text-cyan-400";
    if (log.includes("[NOVA]")) return "text-purple-400";
    if (log.includes("[SWEEP]")) return "text-indigo-400";
    if (log.includes("[MERGE]")) return "text-teal-400";
    if (log.includes("[PATCH]")) return "text-emerald-400";
    if (log.includes("[INGEST]")) return "text-yellow-400";
    if (log.includes("[IDX]")) return "text-yellow-400";
    return "text-gray-500";
  }, []);

  const phase = PHASES[Math.min(displayedPhaseIdx, PHASES.length - 1)];
  const phaseDetail =
    (currentStep ? scanPresentation?.phaseDetails[currentStep] : undefined) ??
    phase.detail;
  const visibleTotalSteps = totalSteps || PHASES.length;
  const visibleStepNumber =
    currentStep === "finalizing" || scanStatus === "completed"
      ? visibleTotalSteps
      : Math.min(stepIndex + 1, visibleTotalSteps);
  const overallProgress =
    scanStatus === "completed"
      ? 100
      : Math.round((stepIndex / Math.max(visibleTotalSteps, 1)) * 100);

  return (
    <div className="flex flex-col items-center justify-center w-full max-w-5xl mx-auto min-h-screen p-6 text-white font-mono z-10 relative select-none">
      <ScanningBackdrop />

      {error && (
        <div className="absolute inset-0 flex items-center justify-center z-50 bg-black/80 backdrop-blur-sm">
          <div className="text-center p-8">
            <ShieldAlert className="w-12 h-12 text-red-400 mx-auto mb-4" />
            <p className="text-red-400 text-sm font-mono">{error}</p>
          </div>
        </div>
      )}

      <div className="w-full grid grid-cols-1 md:grid-cols-12 gap-5 relative z-10">
        <div className="col-span-1 md:col-span-4 flex flex-col gap-2">
          <div className="text-[10px] text-gray-600 border-b border-white/5 pb-2 mb-1 flex items-center justify-between">
            <span>{"// OPERATION.PIPELINE"}</span>
            <span className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
              <span className="text-red-500">LIVE</span>
            </span>
          </div>

          {PHASES.map((item, index) => {
            const isActive = index === displayedPhaseIdx;
            const isDone =
              index < displayedPhaseIdx || scanStatus === "completed";
            const Icon = item.icon;

            return (
              <motion.div
                key={item.id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.08 }}
                className={`relative p-3 rounded-lg border transition-all duration-300 ${
                  isActive
                    ? "border-white/20 bg-white/[0.03]"
                    : isDone
                      ? "border-white/5 bg-black/30"
                      : "border-transparent opacity-30"
                } flex items-center gap-3`}
              >
                {isActive && (
                  <motion.div
                    layoutId="phase-bar"
                    className={`absolute left-0 top-0 bottom-0 w-[3px] rounded-r ${item.bg}`}
                    transition={{ type: "spring", bounce: 0.2 }}
                  />
                )}
                <div
                  className={`p-1.5 rounded shrink-0 ${
                    isActive
                      ? item.color
                      : isDone
                        ? "text-gray-500"
                        : "text-gray-700"
                  }`}
                >
                  <Icon className="w-4 h-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div
                    className={`text-[10px] font-bold tracking-wider ${
                      isActive
                        ? item.color
                        : isDone
                          ? "text-gray-400"
                          : "text-gray-600"
                    }`}
                  >
                    {item.agent}
                  </div>
                  <div className="text-[9px] text-gray-600 truncate">
                    {item.title}
                  </div>
                </div>

                {isDone && !isActive && (
                  <Lock className="w-3 h-3 text-emerald-500/40 shrink-0" />
                )}
              </motion.div>
            );
          })}
        </div>

        <div className="col-span-1 md:col-span-8 flex flex-col border border-white/10 rounded-xl bg-black/50 backdrop-blur-md relative overflow-hidden">
          <div className="flex items-center justify-between p-3 border-b border-white/10 bg-white/[0.02] text-[10px] text-gray-500">
            <div className="flex items-center gap-2">
              <Terminal className="w-3 h-3" />
              <span>TERMINAL // {phase.agent}</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-gray-600">
                STEP {visibleStepNumber}/{visibleTotalSteps}
              </span>
              {scanPresentation?.targetLabel && (
                <span className="hidden md:inline text-gray-700">
                  {scanPresentation.targetLabel}
                </span>
              )}
              <span className={phase.color}>{overallProgress}%</span>
            </div>
          </div>

          <div className="flex-1 p-8 flex flex-col items-center justify-center relative min-h-[320px]">
            <AnimatePresence mode="wait">
              <motion.div
                key={phase.id}
                initial={{ opacity: 0, scale: 0.7, filter: "blur(12px)" }}
                animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
                exit={{ opacity: 0, scale: 1.15, filter: "blur(12px)" }}
                transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                className="flex flex-col items-center gap-6 text-center z-10"
              >
                <div className="relative">
                  <div
                    className={`absolute -inset-6 blur-3xl opacity-15 ${phase.bg}`}
                  />
                  <div
                    className={`p-6 rounded-2xl border border-white/10 bg-black/40 ${phase.color}`}
                  >
                    <phase.icon className="w-14 h-14" />
                  </div>

                  <motion.div
                    animate={{ rotate: 360 }}
                    transition={{
                      duration: 8,
                      repeat: Infinity,
                      ease: "linear",
                    }}
                    className="absolute -inset-5 border border-dashed border-white/15 rounded-full pointer-events-none"
                  />
                  <motion.div
                    animate={{ rotate: -360 }}
                    transition={{
                      duration: 14,
                      repeat: Infinity,
                      ease: "linear",
                    }}
                    className="absolute -inset-10 border border-dotted border-white/[0.06] rounded-full pointer-events-none"
                  />

                  <div className="absolute -inset-14 pointer-events-none">
                    <div className="absolute top-0 left-0 w-3 h-3 border-t border-l border-white/20" />
                    <div className="absolute top-0 right-0 w-3 h-3 border-t border-r border-white/20" />
                    <div className="absolute bottom-0 left-0 w-3 h-3 border-b border-l border-white/20" />
                    <div className="absolute bottom-0 right-0 w-3 h-3 border-b border-r border-white/20" />
                  </div>
                </div>

                <div>
                  <h3
                    className={`text-lg font-bold tracking-[0.2em] uppercase ${phase.color}`}
                  >
                    {phase.title}
                  </h3>
                  <p className="text-[11px] text-gray-500 mt-2 max-w-sm leading-relaxed">
                    {phaseDetail}
                  </p>
                </div>
              </motion.div>
            </AnimatePresence>

            <div className="absolute bottom-6 left-6 right-6 flex flex-col gap-1.5">
              <div className="flex justify-between text-[9px] text-gray-600">
                <span>
                  {scanStatus === "completed"
                    ? "Scan complete"
                    : `Processing ${phase.agent}...`}
                </span>
                <span>[{overallProgress} / 100]</span>
              </div>
              <div className="w-full h-1.5 bg-white/5 rounded-full overflow-hidden border border-white/5">
                <motion.div
                  className={`h-full ${phase.bg} rounded-full`}
                  animate={{ width: `${overallProgress}%` }}
                  transition={{ duration: 0.5, ease: "easeOut" }}
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="w-full mt-5 p-4 border border-white/10 rounded-xl bg-black/40 backdrop-blur-md relative z-10 overflow-hidden">
        <div className="flex items-center gap-2 text-[9px] text-gray-600 mb-3 border-b border-white/5 pb-2">
          <Terminal className="w-3 h-3" />
          <span>STDOUT // AGENT_CLUSTER</span>
        </div>
        <div className="h-28 flex flex-col justify-end gap-0.5 overflow-hidden">
          {logs.map((log, idx) => (
            <motion.div
              key={`${idx}-${log}`}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.2 }}
              className={`text-[11px] leading-relaxed ${logColor(log)}`}
            >
              <span className="text-gray-700 mr-2 tabular-nums">
                {new Date().toISOString().split("T")[1].slice(0, 12)}
              </span>
              {log}
            </motion.div>
          ))}
          <motion.div
            animate={{ opacity: [1, 0, 1] }}
            transition={{ duration: 0.8, repeat: Infinity }}
            className="w-2 h-3.5 bg-white/80 mt-0.5"
          />
        </div>
      </div>
    </div>
  );
}
