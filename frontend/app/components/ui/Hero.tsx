"use client";

import React, { useEffect, useRef, useState } from "react";
import { motion, useScroll, useTransform, useSpring } from "framer-motion";
import { ShieldCheck, Lock, Activity, Github, ArrowRight, AlertCircle, Play, Bug } from "lucide-react";

interface HeroProps {
  onScan: (repoUrl: string) => void;
  onDemoScan: (repoKey: string, repoUrl: string) => void;
}

const DEMO_REPOS = [
  {
    key: "lets-be-bad-guys",
    name: "lets-be-bad-guys",
    owner: "mpirnat",
    url: "https://github.com/mpirnat/lets-be-bad-guys",
    description: "Intentionally vulnerable Django app — OWASP Top 10 demo with XSS, SQL injection, code execution & more.",
    tag: "Django",
    tagColor: "text-emerald-400",
    tagBg: "bg-emerald-500/10",
    accent: "from-red-500 to-orange-500",
    findings: "7 vulnerabilities",
    severity: "2 Critical · 3 High",
  },
  {
    key: "vulpy",
    name: "vulpy",
    owner: "fportantier",
    url: "https://github.com/fportantier/vulpy",
    description: "Vulnerable Flask app featuring SQL injection, hardcoded secrets, weak auth & insecure session management.",
    tag: "Flask",
    tagColor: "text-blue-400",
    tagBg: "bg-blue-500/10",
    accent: "from-purple-500 to-pink-500",
    findings: "9 vulnerabilities",
    severity: "3 Critical · 3 High",
  },
];

export function Hero({ onScan, onDemoScan }: HeroProps) {
  const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });
  const containerRef = useRef<HTMLDivElement>(null);
  const [repoUrl, setRepoUrl] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { scrollYProgress } = useScroll({
    target: containerRef,
    offset: ["start start", "end start"],
  });

  const smoothProgress = useSpring(scrollYProgress, { stiffness: 100, damping: 30, restDelta: 0.001 });

  const y1 = useTransform(smoothProgress, [0, 1], [0, 200]);
  const y2 = useTransform(smoothProgress, [0, 1], [0, -150]);
  const y3 = useTransform(smoothProgress, [0, 1], [0, 150]);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      setMousePosition({ x, y });
    };

    window.addEventListener("mousemove", handleMouseMove);
    return () => window.removeEventListener("mousemove", handleMouseMove);
  }, []);

  const validateAndScan = () => {
    const trimmed = repoUrl.trim();
    
    if (!trimmed) {
      setError("Please enter a GitHub repository URL to scan.");
      return;
    }

    // Basic URL validation
    const githubRegex = /^https?:\/\/(www\.)?github\.com\/[\w.-]+\/[\w.-]+/i;
    if (!githubRegex.test(trimmed)) {
      setError("Please enter a valid GitHub URL (e.g., https://github.com/owner/repo)");
      return;
    }

    setError("");
    setIsSubmitting(true);
    onScan(trimmed);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      validateAndScan();
    }
  };

  return (
    <div 
      ref={containerRef}
      className="relative min-h-screen w-full flex flex-col items-center justify-center overflow-hidden bg-[#050505] text-white"
    >
      {/* Dynamic Cursor Spotlight */}
      <div 
        className="pointer-events-none absolute inset-0 z-0 transition-opacity duration-300"
        style={{
          background: `radial-gradient(600px circle at ${mousePosition.x}px ${mousePosition.y}px, rgba(59, 130, 246, 0.1), transparent 40%)`
        }}
      />

      {/* Grid Background */}
      <div className="absolute inset-0 z-0 opacity-20 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,#000_70%,transparent_100%)]" />

      {/* Floating 3D Elements */}
      <motion.div style={{ y: y1 }} className="hidden lg:block absolute top-[20%] left-[8%] z-10">
        <div style={{ perspective: 1200 }}>
          <motion.div 
            animate={{ y: [0, -15, 0] }}
            transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}
            style={{ 
              rotateX: 15, 
              rotateY: 25, 
              rotateZ: -5,
              transformStyle: 'preserve-3d' 
            }}
            className="relative group rounded-xl"
          >
            <div style={{ transform: 'translateZ(-40px)' }} className="absolute -inset-2 bg-gradient-to-r from-blue-600 to-cyan-600 rounded-2xl blur-xl opacity-40 group-hover:opacity-60 transition duration-1000"></div>
            <div style={{ transform: 'translateZ(0px)' }} className="relative bg-[#0d0d0d]/90 backdrop-blur-xl border border-white/10 p-4 rounded-xl flex items-center gap-3 shadow-2xl group-hover:border-white/20 transition-colors">
              <Activity className="text-cyan-400 w-5 h-5 flex-shrink-0" />
              <div>
                <p className="text-[10px] text-gray-400 font-mono tracking-wider">STATUS</p>
                <p className="text-sm font-semibold whitespace-nowrap">Scanning Network...</p>
              </div>
            </div>
          </motion.div>
        </div>
      </motion.div>

      <motion.div style={{ y: y2 }} className="hidden lg:block absolute bottom-[20%] left-[12%] z-10">
        <div style={{ perspective: 1200 }}>
          <motion.div 
            animate={{ y: [0, 20, 0] }}
            transition={{ duration: 7, repeat: Infinity, ease: "easeInOut", delay: 1 }}
            style={{ 
              rotateX: -15, 
              rotateY: 20, 
              rotateZ: 8,
              transformStyle: 'preserve-3d' 
            }}
            className="relative group rounded-xl"
          >
            <div style={{ transform: 'translateZ(-40px)' }} className="absolute -inset-2 bg-gradient-to-r from-orange-600 to-red-600 rounded-2xl blur-xl opacity-40 group-hover:opacity-60 transition duration-1000"></div>
            <div style={{ transform: 'translateZ(0px)' }} className="relative bg-[#0d0d0d]/90 backdrop-blur-xl border border-white/10 p-5 rounded-xl shadow-2xl w-64 group-hover:border-white/20 transition-colors">
              <p className="text-[10px] text-gray-400 mb-3 font-mono tracking-wider">VULNERABILITIES</p>
              <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
                <motion.div 
                  initial={{ width: 0 }}
                  animate={{ width: "87%" }}
                  transition={{ duration: 1.5, delay: 0.5 }}
                  className="h-full bg-gradient-to-r from-orange-400 to-red-500 shadow-[0_0_10px_rgba(239,68,68,0.5)]"
                />
              </div>
              <p className="text-[10px] text-right mt-2 text-red-400 font-mono tracking-wider">87% RESOLVED</p>
            </div>
          </motion.div>
        </div>
      </motion.div>

      <motion.div style={{ y: y3 }} className="hidden lg:block absolute top-[25%] right-[8%] z-10">
        <div style={{ perspective: 1200 }}>
          <motion.div 
            animate={{ y: [0, -20, 0] }}
            transition={{ duration: 5.5, repeat: Infinity, ease: "easeInOut", delay: 0.5 }}
            style={{ 
              rotateX: 20, 
              rotateY: -25, 
              rotateZ: 5,
              transformStyle: 'preserve-3d' 
            }}
            className="relative group rounded-xl"
          >
            <div style={{ transform: 'translateZ(-40px)' }} className="absolute -inset-2 bg-gradient-to-r from-emerald-600 to-teal-600 rounded-2xl blur-xl opacity-40 group-hover:opacity-60 transition duration-1000"></div>
            <div style={{ transform: 'translateZ(0px)' }} className="relative bg-[#0d0d0d]/90 backdrop-blur-xl border border-white/10 p-4 rounded-xl flex flex-col gap-2 shadow-2xl w-52 group-hover:border-white/20 transition-colors">
              <div className="flex justify-between items-center">
                  <div className="bg-emerald-500/10 p-1.5 rounded-lg">
                    <Lock className="text-emerald-400 w-4 h-4" />
                  </div>
                  <span className="text-[10px] font-bold text-emerald-400 tracking-wider">SECURE</span>
              </div>
              <div className="mt-1">
                <p className="text-[10px] text-gray-400 font-mono">End-to-End Encrypted</p>
                <p className="text-base font-bold tracking-wide mt-0.5">Nova Trust™</p>
              </div>
            </div>
          </motion.div>
        </div>
      </motion.div>

      {/* Main Content */}
      <div className="relative z-20 flex flex-col items-center max-w-4xl mx-auto px-4 text-center">
        <motion.div
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
        >
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/5 border border-white/10 mb-8 w-fit mx-auto backdrop-blur-md">
                <ShieldCheck className="w-4 h-4 text-blue-400" />
                <span className="text-xs font-medium tracking-wide text-blue-100 uppercase">Nova Security</span>
            </div>
        </motion.div>

        <motion.h1 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
            className="text-5xl md:text-7xl lg:text-8xl font-bold tracking-tighter mb-6 leading-tight"
        >
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-white to-white/70">new standard for</span>
            <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 via-indigo-400 to-purple-400">security</span>
        </motion.h1>

        <motion.p 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="text-lg md:text-xl text-gray-400 mb-12 max-w-2xl mx-auto font-light"
        >
          Nova streamlines your security posture with intelligent vulnerability analysis that adapts to your codebase.
        </motion.p>

        {/* Input area */}
        <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.3, ease: [0.16, 1, 0.3, 1] }}
            className="w-full max-w-2xl"
        >
          <div className="relative group mx-auto max-w-2xl">
            <div className={`absolute -inset-1 rounded-2xl blur transition duration-500 ${error ? 'bg-gradient-to-r from-red-500 via-orange-500 to-red-500 opacity-30' : 'bg-gradient-to-r from-blue-500 via-purple-500 to-cyan-500 opacity-20 group-hover:opacity-40'}`}></div>
            <div className="relative p-1.5 bg-black/60 backdrop-blur-2xl rounded-2xl border border-white/10 flex flex-col md:flex-row items-center gap-2 shadow-2xl">
              
              <div className="flex-1 flex items-center gap-3 px-4 py-3 w-full border-b md:border-b-0 md:border-r border-white/5">
                <Github className="text-gray-500 w-5 h-5 shrink-0" />
                <input 
                  type="text" 
                  value={repoUrl}
                  onChange={(e) => { setRepoUrl(e.target.value); setError(""); }}
                  onKeyDown={handleKeyDown}
                  placeholder="https://github.com/owner/repo"
                  className="w-full bg-transparent border-none outline-none text-white placeholder:text-gray-600 font-mono text-sm transition-colors"
                />
              </div>

              <div className="flex w-full md:w-auto p-2 md:p-0 gap-2 shrink-0">
                <button 
                  onClick={validateAndScan}
                  disabled={isSubmitting}
                  className="flex-1 md:flex-none flex items-center justify-center gap-2 px-8 py-3 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-medium shadow-[0_0_20px_rgba(79,70,229,0.3)] hover:shadow-[0_0_30px_rgba(79,70,229,0.5)] transition-all text-sm group/btn disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isSubmitting ? (
                    <span className="flex items-center gap-2">
                      <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      Starting…
                    </span>
                  ) : (
                    <>
                      <span>Scan</span>
                      <ArrowRight className="w-4 h-4 group-hover/btn:translate-x-1 transition-transform" />
                    </>
                  )}
                </button>
              </div>

            </div>
          </div>

          {/* Error message */}
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center gap-2 mt-3 text-sm text-red-400 font-mono justify-center"
            >
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              {error}
            </motion.div>
          )}

          {/* Hint */}
          <p className="text-[11px] text-gray-600 mt-3 font-mono">
            Paste a public GitHub repository URL to begin the security analysis
          </p>
        </motion.div>

        {/* ── Demo Repos Section ─────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.45, ease: [0.16, 1, 0.3, 1] }}
          className="w-full max-w-2xl mt-10"
        >
          <div className="flex items-center gap-3 mb-4">
            <div className="h-px flex-1 bg-white/5" />
            <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-white/[0.03] border border-white/10">
              <Play className="w-3 h-3 text-purple-400" />
              <span className="text-[10px] font-bold tracking-[0.2em] uppercase text-gray-400">Try a Demo</span>
            </div>
            <div className="h-px flex-1 bg-white/5" />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {DEMO_REPOS.map((repo, i) => (
              <motion.button
                key={repo.key}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: 0.5 + i * 0.1 }}
                onClick={() => onDemoScan(repo.key, repo.url)}
                className="group relative text-left p-4 rounded-xl bg-white/[0.02] border border-white/10 hover:border-white/20 hover:bg-white/[0.04] transition-all duration-300 overflow-hidden"
              >
                {/* Hover glow */}
                <div className={`absolute -inset-1 bg-gradient-to-r ${repo.accent} opacity-0 group-hover:opacity-10 blur-xl transition-opacity duration-500 rounded-xl`} />
                
                <div className="relative">
                  {/* Header */}
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Bug className="w-3.5 h-3.5 text-red-400" />
                      <span className="text-xs font-bold text-white tracking-wide">{repo.owner}/{repo.name}</span>
                    </div>
                    <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full ${repo.tagBg} ${repo.tagColor} tracking-wider uppercase`}>
                      {repo.tag}
                    </span>
                  </div>

                  {/* Description */}
                  <p className="text-[11px] text-gray-500 leading-relaxed mb-3 line-clamp-2">
                    {repo.description}
                  </p>

                  {/* Stats & Action */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="text-[10px] font-mono text-red-400/80">{repo.findings}</span>
                      <span className="text-white/10">·</span>
                      <span className="text-[10px] font-mono text-gray-600">{repo.severity}</span>
                    </div>
                    <div className="flex items-center gap-1 text-[10px] font-bold text-purple-400 opacity-0 group-hover:opacity-100 transition-opacity tracking-wider">
                      RUN
                      <ArrowRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
                    </div>
                  </div>
                </div>
              </motion.button>
            ))}
          </div>

          <p className="text-[10px] text-gray-600 mt-3 font-mono text-center">
            Pre-scanned repos — results load instantly for demo purposes
          </p>
        </motion.div>
        


      </div>
    </div>
  );
}
