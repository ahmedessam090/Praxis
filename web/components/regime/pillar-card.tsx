"use client";

import { RegimeChartView } from "@/components/charts/charts";
import { StatusPip } from "@/components/level/level";
import { Badge, Card, CardBody, CardHeader, CardTitle } from "@/components/ui/primitives";
import type { RegimeChart, RegimeMetric, RegimePillar } from "@/lib/api";
import { cn, fmtSigned, statusColor } from "@/lib/utils";

const DOT: Record<string, string> = {
  bull: "bg-bull",
  neutral: "bg-neutral",
  bear: "bg-bear",
};

function MetricRow({ m }: { m: RegimeMetric }) {
  const tone = statusColor(m.status);
  return (
    <div className="flex items-start gap-3 border-b border-border/60 py-2 last:border-0">
      <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", DOT[tone])} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-3">
          <span className="truncate text-sm">{m.label}</span>
          <span className="shrink-0 text-sm font-medium tabular-nums">{m.value}</span>
        </div>
        <div className="mt-0.5 flex items-center justify-between gap-2">
          <span className="truncate text-[11px] text-muted">{m.detail || m.source_tag}</span>
          <StatusPip status={m.status} />
        </div>
      </div>
    </div>
  );
}

export function PillarCard({
  pillar,
  charts,
}: {
  pillar: RegimePillar;
  charts: RegimeChart[];
}) {
  const tone = statusColor(pillar.status);
  return (
    <Card>
      <CardHeader className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className={cn("h-2.5 w-2.5 rounded-full", DOT[tone])} />
          <CardTitle>{pillar.name}</CardTitle>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs tabular-nums text-muted">{fmtSigned(pillar.score)}</span>
          <Badge tone={tone}>{pillar.status}</Badge>
        </div>
      </CardHeader>
      <CardBody>
        {pillar.summary ? (
          <p className="mb-2 text-xs leading-relaxed text-muted">{pillar.summary}</p>
        ) : null}
        <div>
          {(pillar.metrics ?? []).map((m) => (
            <MetricRow key={m.key} m={m} />
          ))}
        </div>
        {charts.length > 0 ? (
          <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
            {charts.map((c) => (
              <div key={c.key} className="rounded-lg border border-border/60 p-2">
                <div className="mb-1 px-1 text-xs font-medium text-muted">{c.title}</div>
                <RegimeChartView chart={c} height={230} />
              </div>
            ))}
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}
