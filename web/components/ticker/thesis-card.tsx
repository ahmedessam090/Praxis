"use client";

import { useState } from "react";
import { Badge, Card, CardBody } from "@/components/ui/primitives";
import type { TimeframeThesis } from "@/lib/api";
import { fmt } from "@/lib/utils";

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border/60 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-muted">{label}</div>
      <div className="text-sm font-semibold tabular-nums">{value}</div>
    </div>
  );
}

export function ThesisCard({ thesis }: { thesis: TimeframeThesis }) {
  const [showTrace, setShowTrace] = useState(false);
  const bull = thesis.direction === "bullish";
  const supporting = thesis.supporting_factors ?? [];
  const priceNotes = thesis.price_notes ?? [];
  const transcript = thesis.transcript ?? [];

  // No clean pattern on this timeframe is a valid, expected outcome — show it explicitly
  // instead of rendering a forced/blank card.
  const noPattern =
    /no clean|no setup/i.test(thesis.pattern_label) ||
    ((thesis.confidence ?? 0) === 0 && thesis.entry == null && thesis.target == null);
  if (noPattern) {
    return (
      <Card>
        <CardBody className="pt-5">
          <div className="rounded-lg border border-dashed border-border bg-surface/40 px-4 py-6 text-center">
            <div className="text-sm font-medium text-muted">
              No clear pattern on this timeframe
            </div>
            <p className="mt-1 text-xs text-muted">
              The analyzer found no clean, textbook setup here — and that&apos;s fine.
            </p>
            {supporting.length > 0 ? (
              <p className="mt-3 text-xs text-muted">
                🧩 Supporting structure: {supporting.join(" · ")}
              </p>
            ) : null}
          </div>
        </CardBody>
      </Card>
    );
  }
  // Defining lines (trendlines / curves) that touch real swings — surface the touch count
  // so the user can see the line is anchored to actual price action, not drawn arbitrarily.
  const definingLines = (thesis.shapes ?? []).filter(
    (s) => (s.kind === "trendline" || s.kind === "curve") && (s.touch_count ?? 0) > 0,
  );
  return (
    <Card>
      <CardBody className="pt-5">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Badge tone={bull ? "bull" : "bear"}>{bull ? "▲ long" : "▼ caution"}</Badge>
          <span className="text-base font-semibold">{thesis.pattern_label}</span>
          <span className="text-sm text-muted">· {thesis.status}</span>
          <span className="text-sm text-muted">· conf {fmt(thesis.confidence, 2)}</span>
          {thesis.source !== "llm" ? (
            <Badge tone="muted">engine fallback</Badge>
          ) : null}
        </div>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat label="Entry / breakout" value={fmt(thesis.entry ?? thesis.breakout)} />
          <Stat label="Target" value={fmt(thesis.target)} />
          <Stat label="Stop" value={fmt(thesis.stop)} />
          <Stat label="R : R" value={fmt(thesis.rr_ratio)} />
        </div>

        {thesis.rationale ? (
          <p className="mt-3 text-sm leading-relaxed">
            <span className="font-medium">Analyst read: </span>
            {thesis.rationale}
          </p>
        ) : null}

        {supporting.length > 0 ? (
          <p className="mt-2 text-xs text-muted">
            🧩 Supporting (context, not the trade): {supporting.join(" · ")}
          </p>
        ) : null}

        {priceNotes.length > 0 ? (
          <p className="mt-2 text-xs text-muted">
            Levels: {priceNotes.map((n) => n.label).join("  ·  ")}
          </p>
        ) : null}

        {definingLines.length > 0 ? (
          <p className="mt-2 text-xs text-muted">
            Defining lines:{" "}
            {definingLines
              .map((s) => {
                const n = s.touch_count ?? 0;
                const name = s.label || s.role;
                return `${name} (${n} ${n === 1 ? "touch" : "touches"})`;
              })
              .join("  ·  ")}
          </p>
        ) : null}

        {transcript.length > 0 ? (
          <div className="mt-3">
            <button
              onClick={() => setShowTrace((s) => !s)}
              className="text-xs font-medium text-brand hover:underline"
            >
              {showTrace ? "Hide" : "How the analyst worked"} ({transcript.length} tool calls)
            </button>
            {showTrace ? (
              <pre className="mt-2 overflow-x-auto rounded-lg border border-border bg-surface p-3 text-[11px] text-muted">
                {transcript.join("\n")}
              </pre>
            ) : null}
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}
