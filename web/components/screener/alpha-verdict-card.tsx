"use client";

import { StatusPip } from "@/components/level/level";
import { Badge, Card, CardBody } from "@/components/ui/primitives";
import {
  ActionStateBadge,
  ConvictionRing,
  SectorChip,
} from "@/components/screener/screener-ui";
import type { AlphaVerdict } from "@/lib/api";
import { cn, fmt, statusColor } from "@/lib/utils";

const DOT: Record<string, string> = { bull: "bg-bull", neutral: "bg-neutral", bear: "bg-bear" };

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "bull" | "bear" | "neutral";
}) {
  const text =
    tone === "bull" ? "text-bull" : tone === "bear" ? "text-bear" : "text-foreground";
  return (
    <div className="rounded-lg border border-border/60 bg-surface/40 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-muted">{label}</div>
      <div className={cn("text-sm font-semibold tabular-nums", text)}>{value}</div>
    </div>
  );
}

export function AlphaVerdictCard({
  verdict,
  triggerZone,
}: {
  verdict: AlphaVerdict;
  /** Trigger range from the surfaced thesis (the verdict itself only carries action_state). */
  triggerZone?: { low: number | null | undefined; high: number | null | undefined };
}) {
  const conv = Math.max(0, Math.min(100, verdict.conviction ?? 0));
  const reasons = verdict.reasons ?? [];
  const hasTriggerZone =
    triggerZone != null &&
    triggerZone.low != null &&
    triggerZone.high != null &&
    !Number.isNaN(triggerZone.low) &&
    !Number.isNaN(triggerZone.high);
  return (
    <Card>
      <CardBody className="pt-5">
        <div className="flex items-start gap-4">
          <ConvictionRing value={conv} size={68} />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={verdict.is_alpha ? "bull" : "muted"}>
                {verdict.is_alpha ? "★ ALPHA" : "not alpha"}
              </Badge>
              <ActionStateBadge state={verdict.action_state} />
              {verdict.sector ? <SectorChip sector={verdict.sector} /> : null}
              {verdict.stage ? (
                <span className="text-xs capitalize text-muted">{verdict.stage}</span>
              ) : null}
              {verdict.regime_alignment ? (
                <span className="inline-flex items-center gap-1 text-xs text-muted">
                  <span className="h-1 w-1 rounded-full bg-muted" />
                  {verdict.regime_alignment} regime
                </span>
              ) : null}
            </div>
            {verdict.summary ? (
              <p className="mt-2 text-sm leading-relaxed">{verdict.summary}</p>
            ) : null}
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat label="Entry" value={fmt(verdict.entry)} />
          <Stat label="Stop" value={fmt(verdict.stop)} tone="bear" />
          <Stat label="Target" value={fmt(verdict.target)} tone="bull" />
          <Stat label="R : R" value={fmt(verdict.rr)} />
        </div>

        {hasTriggerZone ? (
          <p className="mt-2 text-xs text-muted">
            <span className="font-medium text-foreground">Trigger range:</span>{" "}
            <span className="tabular-nums">
              {fmt(triggerZone!.low)}
              <span className="px-1 text-border">–</span>
              {fmt(triggerZone!.high)}
            </span>
          </p>
        ) : null}

        {reasons.length > 0 ? (
          <div className="mt-4">
            <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-muted">
              Reasoning
            </div>
            <div className="overflow-hidden rounded-lg border border-border/60">
              {reasons.map((r, i) => {
                const tone = statusColor(r.status ?? "neutral");
                return (
                  <div
                    key={i}
                    className="flex items-start gap-3 border-b border-border/60 px-3 py-2 last:border-0 odd:bg-surface/30"
                  >
                    <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", DOT[tone])} />
                    <div className="min-w-0 flex-1">
                      <span className="text-sm font-medium capitalize">{r.category}</span>
                      <span className="ml-2 text-sm text-muted">{r.detail}</span>
                    </div>
                    <span className="mt-0.5 shrink-0">
                      <StatusPip status={r.status ?? "neutral"} />
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}
