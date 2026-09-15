"use client";

import {
  ArrowDownRight,
  ArrowUpRight,
  Flag,
  Maximize2,
  TrendingDown,
  TrendingUp,
  Trophy,
  type LucideIcon,
} from "lucide-react";
import { Spinner } from "@/components/ui/primitives";
import type { GapNote, KeyLevel } from "@/lib/api";
import { cn, fmt, fmtSigned, statusColor } from "@/lib/utils";

/** Shared screener tone helpers — kept in one place so every view reads identically. */
export type Tone = "bull" | "neutral" | "bear" | "muted";

export const DOT: Record<string, string> = {
  bull: "bg-bull",
  neutral: "bg-neutral",
  bear: "bg-bear",
  muted: "bg-muted",
};
export const TEXT: Record<string, string> = {
  bull: "text-bull",
  neutral: "text-neutral",
  bear: "text-bear",
  muted: "text-muted",
};

/** Conviction 0..100 -> tone, matching the thresholds used across the screener. */
export function convictionTone(conviction: number): Tone {
  if (conviction >= 66) return "bull";
  if (conviction >= 40) return "neutral";
  return "bear";
}

/**
 * A small deterministic palette for sector chips. Sectors aren't an enum, so we hash the
 * label to a stable hue — same sector always gets the same colour without a hard-coded map.
 */
const SECTOR_PALETTE = [
  "bg-sky-500/12 text-sky-500 dark:text-sky-400 border-sky-500/25",
  "bg-violet-500/12 text-violet-500 dark:text-violet-400 border-violet-500/25",
  "bg-emerald-500/12 text-emerald-500 dark:text-emerald-400 border-emerald-500/25",
  "bg-amber-500/12 text-amber-500 dark:text-amber-400 border-amber-500/25",
  "bg-rose-500/12 text-rose-500 dark:text-rose-400 border-rose-500/25",
  "bg-cyan-500/12 text-cyan-500 dark:text-cyan-400 border-cyan-500/25",
  "bg-indigo-500/12 text-indigo-500 dark:text-indigo-400 border-indigo-500/25",
  "bg-teal-500/12 text-teal-500 dark:text-teal-400 border-teal-500/25",
  "bg-fuchsia-500/12 text-fuchsia-500 dark:text-fuchsia-400 border-fuchsia-500/25",
  "bg-lime-500/12 text-lime-600 dark:text-lime-400 border-lime-500/25",
];

function sectorClass(sector: string): string {
  let h = 0;
  for (let i = 0; i < sector.length; i++) h = (h * 31 + sector.charCodeAt(i)) >>> 0;
  return SECTOR_PALETTE[h % SECTOR_PALETTE.length];
}

function prettySector(sector: string): string {
  return sector.replace(/_/g, " ");
}

/** A coloured, capitalized sector chip — stable colour per sector. */
export function SectorChip({ sector, className }: { sector: string; className?: string }) {
  if (!sector) return null;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-medium capitalize",
        sectorClass(sector),
        className,
      )}
    >
      {prettySector(sector)}
    </span>
  );
}

const STATUS_LABEL: Record<string, string> = {
  pending: "pending",
  evaluating: "evaluating",
  alpha: "alpha",
  not_alpha: "not alpha",
};
const STATUS_TONE: Record<string, Tone> = {
  pending: "muted",
  evaluating: "neutral",
  alpha: "bull",
  not_alpha: "bear",
};
const STATUS_PILL: Record<Tone, string> = {
  bull: "bg-bull/15 text-bull border-bull/30",
  bear: "bg-bear/15 text-bear border-bear/30",
  neutral: "bg-neutral/15 text-neutral border-neutral/30",
  muted: "bg-muted/10 text-muted border-border",
};

/** Candidate status as a pill, with a spinner while evaluating. */
export function StatusPill({ status }: { status: string }) {
  const tone = STATUS_TONE[status] ?? "muted";
  const label = STATUS_LABEL[status] ?? status;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-[11px] font-medium",
        STATUS_PILL[tone],
      )}
    >
      {status === "evaluating" ? (
        <Spinner className="h-3 w-3 border-[1.5px]" />
      ) : (
        <span className={cn("h-1.5 w-1.5 rounded-full", DOT[tone])} />
      )}
      {status === "alpha" ? "★ " : ""}
      {label}
    </span>
  );
}

/**
 * Badge describing where price sits relative to a setup's trigger, for an alpha verdict /
 * thesis `action_state`. Mirrors the StatusPill styling (pill, tone-tinted, whitespace-nowrap).
 * Renders nothing for unknown / "" states. Labels are deliberately descriptive rather than
 * directive — they report structure, not an action to take. The "extended" state is the
 * load-bearing one: its amber caution tone makes a stretched entry obvious at a glance. Uses
 * only existing tokens (bull/bear/brand/muted) plus the amber already in the sector palette.
 */
type ActionTone = "bull" | "brand" | "amber" | "bear" | "muted";

const ACTION_STATE_META: Record<string, { label: string; tone: ActionTone }> = {
  in_range: { label: "In range", tone: "bull" },
  awaiting_break: { label: "Awaiting break", tone: "brand" },
  extended: { label: "Past range", tone: "amber" },
  not_yet: { label: "Forming", tone: "muted" },
  played_out: { label: "Target reached", tone: "bear" },
  invalid: { label: "No setup", tone: "muted" },
};

const ACTION_STATE_PILL: Record<ActionTone, string> = {
  bull: "bg-bull/15 text-bull border-bull/30",
  brand: "bg-brand/10 text-brand border-brand/30",
  amber: "bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30",
  bear: "bg-bear/15 text-bear border-bear/30",
  muted: "bg-muted/10 text-muted border-border",
};

const ACTION_STATE_DOT: Record<ActionTone, string> = {
  bull: "bg-bull",
  brand: "bg-brand",
  amber: "bg-amber-500",
  bear: "bg-bear",
  muted: "bg-muted",
};

export function ActionStateBadge({
  state,
  className,
}: {
  state: string | null | undefined;
  className?: string;
}) {
  const meta = state ? ACTION_STATE_META[state] : undefined;
  if (!meta) return null;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-[11px] font-medium",
        ACTION_STATE_PILL[meta.tone],
        className,
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", ACTION_STATE_DOT[meta.tone])} />
      {meta.label}
    </span>
  );
}

/**
 * A compact horizontal bar for a 0..100 score, tinted by tone. Used in the candidate
 * table in place of a bare number so relative strength is visible at a glance.
 */
export function ScoreBar({ score, tone }: { score: number; tone?: Tone }) {
  const pct = Math.max(0, Math.min(100, score));
  const t: Tone = tone ?? (pct >= 66 ? "bull" : pct >= 40 ? "neutral" : "muted");
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-border">
        <div
          className={cn("h-full rounded-full transition-all", DOT[t])}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-8 text-right text-xs font-medium tabular-nums text-muted">
        {pct.toFixed(0)}
      </span>
    </div>
  );
}

/** A factor as a compact tag with a status dot. */
export function FactorTag({
  label,
  value,
  status,
}: {
  label: string;
  value: string;
  status?: string;
}) {
  const tone = statusColor(status ?? "neutral");
  return (
    <span className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-md border border-border/60 bg-surface/60 px-2 py-0.5 text-[11px]">
      <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", DOT[tone])} />
      <span className="text-muted">{label}</span>
      <span className="font-medium tabular-nums">{value}</span>
    </span>
  );
}

/**
 * A premium SVG conviction ring (0..100) with the value centered. Tone follows the shared
 * conviction thresholds. Used as the focal point of each ALPHA card.
 */
export function ConvictionRing({
  value,
  size = 64,
  stroke = 6,
}: {
  value: number;
  size?: number;
  stroke?: number;
}) {
  const v = Math.max(0, Math.min(100, value));
  const tone = convictionTone(v);
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - v / 100);
  const colorVar = tone === "bull" ? "var(--bull)" : tone === "neutral" ? "var(--neutral)" : "var(--bear)";
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--border)"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={colorVar}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
          className="transition-[stroke-dashoffset] duration-500"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center leading-none">
        <span className={cn("text-base font-semibold tabular-nums", TEXT[tone])}>
          {v.toFixed(0)}
        </span>
        <span className="mt-0.5 text-[9px] uppercase tracking-wide text-muted">conv</span>
      </div>
    </div>
  );
}

// ---- Levels to watch ----

/** Visual treatment per KeyLevel.kind — highs/breakouts read bullish, support neutral. */
const LEVEL_KIND: Record<string, { icon: LucideIcon; tone: Tone; label: string }> = {
  "52w_high": { icon: Trophy, tone: "bull", label: "52w high" },
  all_time_high: { icon: Trophy, tone: "bull", label: "all-time high" },
  breakout: { icon: TrendingUp, tone: "bull", label: "breakout" },
  resistance: { icon: TrendingDown, tone: "bear", label: "resistance" },
  support: { icon: TrendingUp, tone: "neutral", label: "support" },
};

const LEVEL_ICON_TINT: Record<Tone, string> = {
  bull: "bg-bull/12 text-bull",
  bear: "bg-bear/12 text-bear",
  neutral: "bg-neutral/15 text-neutral",
  muted: "bg-muted/10 text-muted",
};

/**
 * A compact "levels to watch" list — price, the human label, and the signed distance from
 * the current price. Backend order is preserved (nearest first). Renders nothing if empty.
 */
export function LevelsToWatch({ levels }: { levels: KeyLevel[] }) {
  if (!levels || levels.length === 0) return null;
  return (
    <div>
      <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-muted">
        Levels to watch
      </div>
      <div className="overflow-hidden rounded-lg border border-border/60">
        {levels.map((lvl, i) => {
          const meta = LEVEL_KIND[lvl.kind] ?? {
            icon: Flag,
            tone: "muted" as Tone,
            label: lvl.kind.replace(/_/g, " "),
          };
          const Icon = meta.icon;
          const dist = lvl.distance_pct ?? 0;
          return (
            <div
              key={i}
              className="flex items-center gap-3 border-b border-border/60 px-3 py-2 last:border-0 odd:bg-surface/30"
            >
              <span
                className={cn(
                  "flex h-6 w-6 shrink-0 items-center justify-center rounded-md",
                  LEVEL_ICON_TINT[meta.tone],
                )}
              >
                <Icon size={13} />
              </span>
              <span className="font-semibold tabular-nums">{fmt(lvl.price)}</span>
              <span className="min-w-0 flex-1 truncate text-sm capitalize text-muted">
                {lvl.label || meta.label}
              </span>
              <span
                className={cn(
                  "shrink-0 text-xs font-medium tabular-nums",
                  dist > 0 ? TEXT.bull : dist < 0 ? TEXT.bear : "text-muted",
                )}
              >
                {fmtSigned(dist, 1)}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---- Notable gaps ----

/** Distinct tone per gap kind. */
const GAP_KIND: Record<string, { tone: Tone; label: string }> = {
  breakaway: { tone: "bull", label: "breakaway" },
  runaway: { tone: "neutral", label: "runaway" },
  exhaustion: { tone: "bear", label: "exhaustion" },
};

const GAP_BADGE: Record<Tone, string> = {
  bull: "bg-bull/15 text-bull border-bull/30",
  bear: "bg-bear/15 text-bear border-bear/30",
  neutral: "bg-neutral/15 text-neutral border-neutral/30",
  muted: "bg-muted/10 text-muted border-border",
};

/**
 * Notable (non-common) price gaps. Each gap shows its kind (distinct tone), direction
 * (up/down arrow), the gap zone (lower–upper), the date, a filled/unfilled marker, and the
 * plain-English note. Already filtered server-side, so we render all that arrive.
 */
export function NotableGaps({ gaps }: { gaps: GapNote[] }) {
  if (!gaps || gaps.length === 0) return null;
  return (
    <div>
      <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-muted">
        Notable gaps
      </div>
      <div className="flex flex-col gap-2">
        {gaps.map((g, i) => {
          const meta = GAP_KIND[g.kind] ?? { tone: "muted" as Tone, label: g.kind };
          const up = g.direction === "up";
          const DirIcon = up ? ArrowUpRight : ArrowDownRight;
          const date = new Date(g.date);
          const dateLabel = Number.isNaN(date.getTime())
            ? g.date
            : date.toLocaleDateString();
          return (
            <div
              key={i}
              className="rounded-lg border border-border/60 bg-surface/40 px-3 py-2"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium capitalize",
                    GAP_BADGE[meta.tone],
                  )}
                >
                  <DirIcon size={12} />
                  {meta.label}
                </span>
                <span className="inline-flex items-center gap-1 text-xs tabular-nums text-muted">
                  <Maximize2 size={11} className="rotate-45" />
                  {fmt(g.lower)}
                  <span className="text-border">–</span>
                  {fmt(g.upper)}
                </span>
                <span className="text-xs font-medium tabular-nums text-muted">
                  {fmtSigned(g.gap_pct, 1)}%
                </span>
                <span
                  className={cn(
                    "rounded px-1.5 py-px text-[10px] font-medium uppercase tracking-wide",
                    g.filled ? "bg-muted/10 text-muted" : "bg-brand/10 text-brand",
                  )}
                >
                  {g.filled ? "filled" : "open"}
                </span>
                <span className="ml-auto text-xs text-muted">{dateLabel}</span>
              </div>
              {g.note ? (
                <p className="mt-1.5 text-sm leading-relaxed text-muted">{g.note}</p>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
