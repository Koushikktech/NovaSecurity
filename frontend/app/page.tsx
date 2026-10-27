"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Hero } from "./components/ui/Hero";
import { ScanningSequence } from "./components/scan/ScanningSequence";
import { ReportView } from "./components/report/ReportView";
import { useScan } from "./hooks/useScan";
import { AlertTriangle, RotateCcw } from "lucide-react";

type AppState = "IDLE" | "SCANNING" | "COMPLETE" | "ERROR";

export default function Home() {
  const [appState, setAppState] = useState<AppState>("IDLE");
  const [repoUrl, setRepoUrl] = useState("");
  const scan = useScan();

  const handleStartScan = async (url: string) => {
    setRepoUrl(url);
    setAppState("SCANNING");
    try {
      await scan.startScan(url);
    } catch {
      setAppState("ERROR");
    }
  };

  const handleDemoScan = async (repoKey: string, repoUrl: string) => {
    setRepoUrl(repoUrl);
    setAppState("SCANNING");
    try {
      await scan.startDemoScan(repoKey);
    } catch {
      setAppState("ERROR");
    }
  };

  // Watch scan status to auto-transition
  const handleScanComplete = () => {
    setAppState("COMPLETE");
  };

  const handleReset = () => {
    scan.reset();
    setRepoUrl("");
    setAppState("IDLE");
  };

  return (
    <main className="min-h-screen bg-background">
      <AnimatePresence mode="wait">
        {appState === "IDLE" && (
          <motion.div
            key="hero"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.5 }}
          >
            <Hero onScan={handleStartScan} onDemoScan={handleDemoScan} />
          </motion.div>
        )}

        {appState === "SCANNING" && (
          <motion.div
            key="scanning"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.5 }}
            className="relative min-h-screen"
          >
            <ScanningSequence
              currentStep={scan.currentStep}
              scanStatus={scan.status}
              stepIndex={scan.stepIndex}
              totalSteps={scan.totalSteps}
              scanPresentation={scan.scanPresentation}
              error={scan.error}
              onComplete={handleScanComplete}
              onError={() => setAppState("ERROR")}
            />
          </motion.div>
        )}

        {appState === "COMPLETE" && (
          <motion.div
            key="report"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5 }}
            className="min-h-screen"
          >
            <ReportView
              scanId={scan.scanId}
              scanMode={scan.scanMode}
              findings={scan.findings}
              summary={scan.summary}
              graphData={scan.graphData}
              repoUrl={repoUrl}
              onReset={handleReset}
            />
          </motion.div>
        )}

        {appState === "ERROR" && (
          <motion.div
            key="error"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4 }}
            className="min-h-screen flex items-center justify-center bg-[#030303]"
          >
            <div className="text-center max-w-md mx-auto px-6">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-red-500/10 border border-red-500/20 mb-6">
                <AlertTriangle className="w-8 h-8 text-red-400" />
              </div>
              <h2 className="text-2xl font-bold text-white mb-3 font-heading">
                Scan Failed
              </h2>
              <p className="text-gray-400 text-sm mb-8 leading-relaxed font-mono">
                {scan.error || "An unexpected error occurred while scanning the repository."}
              </p>
              <button
                onClick={handleReset}
                className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-white/10 border border-white/20 text-white font-medium hover:bg-white/15 transition-all text-sm group"
              >
                <RotateCcw className="w-4 h-4 group-hover:-rotate-45 transition-transform" />
                Try Again
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </main>
  );
}
