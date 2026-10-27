"use client";

import { useMemo } from "react";
import { motion } from "framer-motion";

interface PixelAgentProps {
  color: string;
  x: number;
  y: number;
  delay: number;
  variant: number;
}

function PixelAgent({ color, x, y, delay, variant }: PixelAgentProps) {
  const sprites: Record<number, number[][]> = {
    0: [
      [0, 1, 1, 1, 0],
      [1, 1, 1, 1, 1],
      [1, 0, 1, 0, 1],
      [1, 1, 1, 1, 1],
      [0, 1, 0, 1, 0],
      [0, 1, 0, 1, 0],
    ],
    1: [
      [0, 0, 1, 0, 0],
      [0, 1, 1, 1, 0],
      [1, 1, 1, 1, 1],
      [1, 0, 1, 0, 1],
      [0, 1, 1, 1, 0],
      [0, 1, 0, 1, 0],
    ],
    2: [
      [1, 0, 1, 0, 1],
      [0, 1, 1, 1, 0],
      [1, 1, 1, 1, 1],
      [0, 1, 1, 1, 0],
      [1, 0, 1, 0, 1],
      [0, 0, 1, 0, 0],
    ],
    3: [
      [0, 1, 0, 1, 0],
      [1, 1, 1, 1, 1],
      [1, 0, 1, 0, 1],
      [0, 1, 1, 1, 0],
      [0, 1, 0, 1, 0],
      [1, 0, 0, 0, 1],
    ],
  };

  const sprite = sprites[variant % 4];
  const px = 4;

  return (
    <motion.div
      className="absolute pointer-events-none"
      style={{ left: `${x}%`, top: `${y}%` }}
      initial={{ opacity: 0, y: 20 }}
      animate={{
        opacity: [0, 0.7, 0.5, 0.7, 0],
        y: [20, -40, -80, -120, -180],
        x: [0, 12, -8, 18, 0],
      }}
      transition={{
        duration: 8 + variant * 2,
        delay,
        repeat: Infinity,
        ease: "linear",
      }}
    >
      <div className="relative">
        <div
          className="absolute rounded-full blur-lg opacity-30"
          style={{
            background: color,
            width: px * 5 + 10,
            height: px * 6 + 10,
            left: -5,
            top: -5,
          }}
        />
        <svg width={px * 5} height={px * 6}>
          {sprite.map((row, ry) =>
            row.map((cell, cx) =>
              cell ? (
                <rect
                  key={`${ry}-${cx}`}
                  x={cx * px}
                  y={ry * px}
                  width={px}
                  height={px}
                  fill={color}
                  opacity={0.85}
                />
              ) : null
            )
          )}
        </svg>
      </div>
    </motion.div>
  );
}

function DataStream({ delay, x }: { delay: number; x: number }) {
  return (
    <motion.div
      className="absolute w-px pointer-events-none"
      style={{ left: `${x}%`, top: 0 }}
      initial={{ height: 0, opacity: 0 }}
      animate={{ height: "100%", opacity: [0, 0.25, 0] }}
      transition={{
        duration: 3,
        delay,
        repeat: Infinity,
        ease: "linear",
      }}
    >
      <div className="h-full w-full bg-gradient-to-b from-transparent via-cyan-500/30 to-transparent" />
    </motion.div>
  );
}

const AGENT_COLORS = [
  "#3b82f6",
  "#06b6d4",
  "#a855f7",
  "#ef4444",
  "#10b981",
  "#f59e0b",
];

export function ScanningBackdrop() {
  const agents = useMemo(
    () =>
      Array.from({ length: 14 }, (_, i) => ({
        id: i,
        color: AGENT_COLORS[i % AGENT_COLORS.length],
        x: 3 + ((i * 7.1) % 94),
        y: 55 + ((i * 13.3) % 45),
        delay: (i * 1.3) % 6,
        variant: i % 4,
      })),
    []
  );

  const streams = useMemo(
    () =>
      Array.from({ length: 18 }, (_, i) => ({
        id: i,
        x: (i * 5.5) % 100,
        delay: (i * 0.7) % 5,
      })),
    []
  );

  return (
    <>
      <div className="fixed inset-0 pointer-events-none z-0 bg-[#030303]" aria-hidden="true">
        <div className="absolute inset-0 opacity-[0.04] bg-[linear-gradient(to_right,#ffffff_1px,transparent_1px),linear-gradient(to_bottom,#ffffff_1px,transparent_1px)] bg-[size:32px_32px]" />
        <div className="absolute inset-0 bg-[linear-gradient(transparent_50%,rgba(0,0,0,0.15)_50%)] bg-[size:100%_4px] opacity-30" />
        <div className="absolute left-[20%] top-[-10%] h-[40%] w-[40%] rounded-full bg-blue-600/[0.08] blur-[120px]" />
        <div className="absolute bottom-[-10%] right-[10%] h-[30%] w-[30%] rounded-full bg-purple-600/[0.08] blur-[120px]" />
      </div>

      <div className="fixed inset-0 pointer-events-none z-0 overflow-hidden blur-[1.5px] opacity-60" aria-hidden="true">
        {agents.map((agent) => (
          <PixelAgent key={agent.id} {...agent} />
        ))}
      </div>

      <div className="fixed inset-0 pointer-events-none z-0 overflow-hidden opacity-15" aria-hidden="true">
        {streams.map((stream) => (
          <DataStream key={stream.id} x={stream.x} delay={stream.delay} />
        ))}
      </div>
    </>
  );
}
