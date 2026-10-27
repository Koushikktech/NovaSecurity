"use client";

import { useState, useMemo } from "react";
import { motion } from "framer-motion";
import {
  Shield,
  Network,
  Crosshair,
  Activity,
  ArrowLeft,
  Download,
  Terminal,
  ChevronRight,
} from "lucide-react";
import { FindingCard } from "./FindingCard";
import { useFixes } from "../../hooks/useFixes";
import type {
  Finding,
  GraphData,
  ScanMode,
  ScanSummary,
} from "../../lib/types";

interface ReportViewProps {
  scanId: string | null;
  scanMode: ScanMode | null;
  findings: Finding[];
  summary: ScanSummary | null;
  graphData: GraphData | null;
  repoUrl: string;
  onReset: () => void;
}

export function ReportView({
  scanId,
  scanMode,
  findings,
  summary,
  graphData,
  repoUrl,
  onReset,
}: ReportViewProps) {
  const [activeFilter, setActiveFilter] = useState<string>("All");
  const fixes = useFixes(scanId, {
    allowPullRequestCreation: scanMode !== "demo",
  });
  const scanLines = [12, 27, 41, 58, 74, 89];
  const completedAt = "Just now";

  const critCount = summary?.critical ?? findings.filter((f) => f.severity === "Critical").length;
  const highCount = summary?.high ?? findings.filter((f) => f.severity === "High").length;
  const medCount = summary?.medium ?? findings.filter((f) => f.severity === "Medium").length;
  const lowCount = summary?.low ?? findings.filter((f) => f.severity === "Low").length;
  const totalFindings = summary?.total ?? findings.length;

  const confirmedCount = findings.filter(
    (f) => f.validation_status === "Confirmed"
  ).length;
  const redTeamPoCs = findings.filter((f) => f.red_team_success).length;

  // Health grade based on findings
  const healthGrade = useMemo(() => {
    if (totalFindings === 0) return "A+";
    if (critCount > 0) return "D";
    if (highCount > 2) return "C";
    if (highCount > 0) return "C+";
    if (medCount > 3) return "B";
    if (medCount > 0) return "B+";
    return "A";
  }, [totalFindings, critCount, highCount, medCount]);

  const stats = [
    {
      label: "VULNERABILITIES",
      value: totalFindings,
      icon: Shield,
      accent: "text-red-400",
      borderColor: "border-red-500/20",
    },
    {
      label: "GRAPH PATHS",
      value: graphData?.paths.length ?? 0,
      icon: Network,
      accent: "text-purple-400",
      borderColor: "border-purple-500/20",
    },
    {
      label: "RED TEAM PoCs",
      value: redTeamPoCs,
      icon: Crosshair,
      accent: "text-orange-400",
      borderColor: "border-orange-500/20",
    },
    {
      label: "CODE HEALTH",
      value: healthGrade,
      icon: Activity,
      accent: "text-emerald-400",
      borderColor: "border-emerald-500/20",
    },
  ];

  const severities = useMemo(
    () => [
      "All",
      ...Array.from(new Set(findings.map((f) => f.severity).filter(Boolean))),
    ],
    [findings]
  );

  const filteredFindings =
    activeFilter === "All"
      ? findings.map((finding, originalIndex) => ({ finding, originalIndex }))
      : findings
          .map((finding, originalIndex) => ({ finding, originalIndex }))
          .filter(({ finding }) => finding.severity === activeFilter);

  // Extract display-friendly repo name
  const repoName = repoUrl
    ? repoUrl.replace(/^https?:\/\//, "").replace(/\.git$/, "")
    : "Unknown Repository";

  return (
    <div className="min-h-screen bg-[#030303] text-white relative overflow-hidden">
      {/* Background effects */}
      <div className="fixed inset-0 pointer-events-none z-0">
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage: `
              linear-gradient(rgba(255,255,255,0.05) 1px, transparent 1px),
              linear-gradient(90deg, rgba(255,255,255,0.05) 1px, transparent 1px)
            `,
            backgroundSize: "40px 40px",
          }}
        />
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-red-500/5 rounded-full blur-[120px]" />
        <div className="absolute bottom-1/3 right-1/4 w-80 h-80 bg-purple-500/5 rounded-full blur-[100px]" />
        <div className="absolute top-1/2 left-1/2 w-64 h-64 bg-blue-500/5 rounded-full blur-[80px]" />

        {scanLines.map((pos, i) => (
          <motion.div
            key={i}
            className="absolute left-0 right-0 h-px bg-gradient-to-r from-transparent via-white/5 to-transparent"
            style={{ top: `${pos}%` }}
            animate={{ opacity: [0.3, 0.8, 0.3] }}
            transition={{
              duration: 3 + i * 0.5,
              repeat: Infinity,
              ease: "easeInOut",
            }}
          />
        ))}
      </div>

      <div className="relative z-10 max-w-6xl mx-auto px-6 py-10">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="mb-10"
        >
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-4">
              <button
                onClick={onReset}
                className="p-2.5 rounded-lg bg-white/5 border border-white/10 text-gray-400 hover:text-white hover:bg-white/10 transition-all group"
              >
                <ArrowLeft className="w-4 h-4 group-hover:-translate-x-0.5 transition-transform" />
              </button>
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <Terminal className="w-4 h-4 text-emerald-400" />
                  <span className="text-[10px] font-bold tracking-[0.3em] uppercase text-emerald-400 font-mono">
                    Nova Security Audit
                  </span>
                </div>
                <h1 className="text-3xl font-bold tracking-tight font-heading bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent">
                  Scan Report
                </h1>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button className="px-4 py-2.5 rounded-lg bg-white/5 border border-white/10 text-sm font-mono text-gray-300 hover:bg-white/10 transition-all flex items-center gap-2">
                <Download className="w-3.5 h-3.5" /> Export
              </button>
              <button
                onClick={onReset}
                className="px-4 py-2.5 rounded-lg bg-white/10 border border-white/20 text-sm font-mono text-white hover:bg-white/15 transition-all"
              >
                New Scan
              </button>
            </div>
          </div>

          {/* Scan meta */}
          <div className="flex flex-wrap items-center gap-4 text-xs font-mono text-gray-500 bg-white/[0.02] border border-white/5 rounded-lg px-4 py-3">
            <span>
              Target:{" "}
              <span className="text-gray-300">{repoName}</span>
            </span>
            <span className="text-white/10">|</span>
            <span>
              Completed:{" "}
              <span className="text-gray-300">{completedAt}</span>
            </span>
            <span className="text-white/10">|</span>
            <span>
              Findings:{" "}
              <span className="text-gray-300">{totalFindings}</span>
            </span>
            <span className="text-white/10">|</span>
            <span>
              Confirmed:{" "}
              <span className="text-emerald-400">{confirmedCount}</span>
            </span>
            {graphData && (
              <>
                <span className="text-white/10">|</span>
                <span>
                  Graph:{" "}
                  <span className="text-purple-400">
                    {graphData.nodes.length} nodes, {graphData.links.length} edges
                  </span>
                </span>
              </>
            )}
          </div>
        </motion.div>

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-10">
          {stats.map((stat, i) => {
            const Icon = stat.icon;
            return (
              <motion.div
                key={stat.label}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: 0.1 + i * 0.08 }}
                className={`bg-black/40 backdrop-blur-xl border ${stat.borderColor} rounded-xl p-5 relative overflow-hidden group hover:bg-black/60 transition-all`}
              >
                <div className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-white/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                <div className="flex items-center gap-2 mb-3">
                  <Icon className={`w-4 h-4 ${stat.accent}`} />
                  <span className="text-[9px] font-bold tracking-[0.25em] uppercase text-gray-500 font-mono">
                    {stat.label}
                  </span>
                </div>
                <div
                  className={`text-3xl font-bold font-mono ${stat.accent} tracking-tight`}
                >
                  {stat.value}
                </div>
              </motion.div>
            );
          })}
        </div>

        {totalFindings > 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.4 }}
            className="mb-8 bg-black/30 border border-white/5 rounded-xl p-5"
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[10px] font-bold tracking-[0.3em] uppercase text-gray-500 font-mono">
                Severity Breakdown
              </h3>
            </div>
            <div className="h-3 rounded-full bg-white/5 overflow-hidden flex">
              {critCount > 0 && (
                <motion.div
                  className="bg-red-500 h-full"
                  initial={{ width: 0 }}
                  animate={{
                    width: `${(critCount / totalFindings) * 100}%`,
                  }}
                  transition={{ duration: 0.8, delay: 0.5, ease: "easeOut" }}
                />
              )}
              {highCount > 0 && (
                <motion.div
                  className="bg-orange-500 h-full"
                  initial={{ width: 0 }}
                  animate={{
                    width: `${(highCount / totalFindings) * 100}%`,
                  }}
                  transition={{ duration: 0.8, delay: 0.6, ease: "easeOut" }}
                />
              )}
              {medCount > 0 && (
                <motion.div
                  className="bg-yellow-500 h-full"
                  initial={{ width: 0 }}
                  animate={{
                    width: `${(medCount / totalFindings) * 100}%`,
                  }}
                  transition={{ duration: 0.8, delay: 0.7, ease: "easeOut" }}
                />
              )}
              {lowCount > 0 && (
                <motion.div
                  className="bg-blue-500 h-full"
                  initial={{ width: 0 }}
                  animate={{
                    width: `${(lowCount / totalFindings) * 100}%`,
                  }}
                  transition={{ duration: 0.8, delay: 0.8, ease: "easeOut" }}
                />
              )}
            </div>
            <div className="flex items-center gap-6 mt-3 text-xs font-mono text-gray-400">
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-red-500" />
                Critical ({critCount})
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-orange-500" />
                High ({highCount})
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-yellow-500" />
                Medium ({medCount})
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-blue-500" />
                Low ({lowCount})
              </span>
            </div>
          </motion.div>
        )}

        {/* Empty state */}
        {totalFindings === 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
            className="mb-10 bg-black/30 border border-emerald-500/10 rounded-xl p-10 text-center"
          >
            <Shield className="w-12 h-12 text-emerald-400 mx-auto mb-4 opacity-60" />
            <h3 className="text-lg font-semibold text-white mb-2">
              No Vulnerabilities Found
            </h3>
            <p className="text-sm text-gray-400 max-w-md mx-auto">
              The Nova security analysis completed without finding any
              vulnerabilities. This doesn&apos;t guarantee the absence of
              security issues — consider running additional manual reviews.
            </p>
          </motion.div>
        )}

        {/* Severity filter tabs */}
        {totalFindings > 0 && (
          <>
            <div className="flex items-center gap-2 mb-6">
              {severities.map((sev) => (
                <button
                  key={sev}
                  onClick={() => setActiveFilter(sev as string)}
                  className={`px-3.5 py-1.5 rounded-lg text-xs font-mono font-bold tracking-wider uppercase transition-all duration-300 border ${
                    activeFilter === sev
                      ? "bg-white/10 border-white/20 text-white shadow-[0_0_15px_rgba(255,255,255,0.05)] scale-105"
                      : "bg-transparent border-white/5 text-gray-500 hover:text-gray-300 hover:border-white/10 hover:bg-white/[0.02]"
                  }`}
                >
                  {sev}
                </button>
              ))}
            </div>

            {/* Findings */}
            <div className="space-y-4 mb-16">
              {filteredFindings.map(({ finding, originalIndex }, i) => (
                <FindingCard
                  key={`${finding.file}-${finding.line}-${originalIndex}`}
                  finding={finding}
                  index={i}
                  findingIndex={originalIndex}
                  canCreatePullRequest={scanMode !== "demo"}
                  fixJob={fixes.jobs[originalIndex]}
                  onFix={fixes.startFix}
                  onCreatePullRequest={fixes.createPullRequest}
                />
              ))}
            </div>
          </>
        )}

        {/* Footer */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.8 }}
          className="border-t border-white/5 pt-6 pb-10 flex items-center justify-between text-xs font-mono text-gray-600"
        >
          <div className="flex items-center gap-2">
            <Shield className="w-3.5 h-3.5 text-purple-500" />
            <span>NovaGuard Security Scanner v1.0</span>
          </div>
          <div className="flex items-center gap-1 text-gray-500 hover:text-gray-300 transition-colors cursor-pointer">
            Full technical report
            <ChevronRight className="w-3 h-3" />
          </div>
        </motion.div>
      </div>
    </div>
  );
}
