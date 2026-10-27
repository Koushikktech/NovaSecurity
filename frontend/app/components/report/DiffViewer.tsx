"use client";

interface DiffViewerProps {
  diff: string;
}

function getLineClass(line: string): string {
  if (line.startsWith("diff --git") || line.startsWith("index ")) {
    return "text-cyan-300 bg-cyan-950/30 font-medium";
  }
  if (line.startsWith("@@")) {
    return "text-purple-300 bg-purple-950/30 font-medium shadow-[inset_2px_0_0_0_rgba(168,85,247,0.4)]";
  }
  if (line.startsWith("+++ ")) {
    return "text-emerald-300 bg-emerald-950/20";
  }
  if (line.startsWith("--- ")) {
    return "text-red-300 bg-red-950/20";
  }
  if (line.startsWith("+")) {
    return "text-emerald-300 bg-emerald-500/10 shadow-[inset_2px_0_0_0_rgba(16,185,129,0.4)]";
  }
  if (line.startsWith("-")) {
    return "text-red-300 bg-red-500/10 shadow-[inset_2px_0_0_0_rgba(239,68,68,0.4)]";
  }
  return "text-gray-300 hover:bg-white/[0.02]";
}

export function DiffViewer({ diff }: DiffViewerProps) {
  const lines = diff.split("\n");
  const added = lines.filter(
    (line) => line.startsWith("+") && !line.startsWith("+++ ")
  ).length;
  const removed = lines.filter(
    (line) => line.startsWith("-") && !line.startsWith("--- ")
  ).length;

  return (
    <div className="flex flex-col h-full bg-[#0a0a0a]">
      {/* Sleek Header */}
      <div className="flex-none px-6 py-5 flex items-center justify-between border-b border-white/5 bg-gradient-to-b from-white/[0.04] to-transparent">
        <div className="flex items-center gap-4">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 shadow-[0_0_15px_rgba(16,185,129,0.15)]">
            <svg
              className="w-5 h-5 text-emerald-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"
              />
            </svg>
          </div>
          <div>
            <h3 className="text-base font-semibold text-white tracking-wide">
              Nova Security Patch
            </h3>
            <p className="text-xs text-gray-400 mt-1 uppercase tracking-widest font-mono">
              Proposed Remediation
            </p>
          </div>
        </div>
        <div className="flex items-center gap-5 bg-black/40 px-5 py-2.5 rounded-lg border border-white/5 shadow-inner">
          <div className="flex items-center gap-2">
             <span className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.8)] animate-pulse" />
            <span className="text-sm font-mono text-emerald-400">+{added}</span>
          </div>
          <div className="w-px h-5 bg-white/10" />
          <div className="flex items-center gap-2">
             <span className="w-2 h-2 rounded-full bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.8)]" />
            <span className="text-sm font-mono text-red-400">-{removed}</span>
          </div>
        </div>
      </div>

      {/* Diff Content */}
      <div className="flex-1 overflow-auto bg-[#0a0a0a] min-h-[400px]">
        <div className="min-w-max p-6">
          <div
            className="font-mono text-[13px] leading-6 selection:bg-white/20"
            role="presentation"
          >
            {lines.map((line, index) => (
              <div
                key={`${index}-${line}`}
                className={`px-4 py-0.5 transition-colors duration-150 empty:h-6 ${getLineClass(
                  line
                )}`}
              >
                {line || " "}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
