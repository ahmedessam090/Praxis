"use client";

import { cn } from "@/lib/utils";

type Tone = "bull" | "neutral" | "bear";
export type Rung = { key: string; label: string; tone: Tone };

const FILL: Record<Tone, string> = {
  bull: "bg-bull",
  neutral: "bg-neutral",
  bear: "bg-bear",
};
const TEXT: Record<Tone, string> = {
  bull: "text-bull",
  neutral: "text-neutral",
  bear: "text-bear",
};

/**
 * A stepped ladder showing the FULL scale with every rung labelled; segments up to and
 * including the current rung are filled in the current rung's tone, so you see both where
 * we are AND how far up the scale (fully-up / moderate / down). Reused for state & posture.
 */
export function LevelLadder({
  label,
  rungs,
  currentKey,
}: {
  label: string;
  rungs: Rung[];
  currentKey: string;
}) {
  const idx = Math.max(
    0,
    rungs.findIndex((r) => r.key === currentKey),
  );
  const tone = rungs[idx]?.tone ?? "neutral";
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-muted">{label}</span>
        <span className={cn("text-sm font-semibold", TEXT[tone])}>{rungs[idx]?.label}</span>
      </div>
      <div className="flex gap-1.5">
        {rungs.map((r, i) => (
          <div
            key={r.key}
            className={cn(
              "h-2 flex-1 rounded-full transition-colors",
              i <= idx ? FILL[tone] : "bg-border",
            )}
          />
        ))}
      </div>
      <div className="mt-1.5 flex justify-between gap-1">
        {rungs.map((r, i) => (
          <span
            key={r.key}
            className={cn(
              "flex-1 text-center text-[10px] leading-tight",
              i === idx ? cn("font-semibold", TEXT[tone]) : "text-muted",
            )}
          >
            {r.label}
          </span>
        ))}
      </div>
    </div>
  );
}

/** −1…+1 score on a red→amber→green track with a marker at the value. */
export function ScoreMeter({ score }: { score: number }) {
  const pct = Math.min(100, Math.max(0, ((score + 1) / 2) * 100));
  const tone: Tone = score > 0.25 ? "bull" : score < -0.25 ? "bear" : "neutral";
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-muted">Score</span>
        <span className={cn("text-sm font-semibold tabular-nums", TEXT[tone])}>
          {score >= 0 ? "+" : "−"}
          {Math.abs(score).toFixed(2)}
        </span>
      </div>
      <div className="relative h-2 rounded-full bg-gradient-to-r from-bear via-neutral to-bull">
        <div
          className="absolute top-1/2 h-4 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-foreground shadow"
          style={{ left: `${pct}%` }}
        />
      </div>
      <div className="mt-1.5 flex justify-between text-[10px] text-muted">
        <span>Risk-off −1</span>
        <span>0</span>
        <span>+1 Risk-on</span>
      </div>
    </div>
  );
}

/** Tiny 3-state pip (bear · neutral · bull) for metric rows. */
export function StatusPip({ status }: { status: string }) {
  const order: Tone[] = ["bear", "neutral", "bull"];
  const active: Tone = status === "bullish" ? "bull" : status === "bearish" ? "bear" : "neutral";
  return (
    <span className="inline-flex items-center gap-0.5">
      {order.map((t) => (
        <span
          key={t}
          className={cn("h-1.5 w-1.5 rounded-full", t === active ? FILL[t] : "bg-border")}
        />
      ))}
    </span>
  );
}
