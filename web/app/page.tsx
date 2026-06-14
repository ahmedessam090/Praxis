"use client";

import { RefreshCw } from "lucide-react";
import { LevelLadder, type Rung, ScoreMeter } from "@/components/level/level";
import { PillarCard } from "@/components/regime/pillar-card";
import { Badge, Button, Card, CardBody, Spinner } from "@/components/ui/primitives";
import { useRefreshRegime, useRegime } from "@/lib/api";
import { titleCase } from "@/lib/utils";

const STATE_RUNGS: Rung[] = [
  { key: "bear", label: "Bear", tone: "bear" },
  { key: "correction", label: "Correction", tone: "bear" },
  { key: "neutral", label: "Neutral", tone: "neutral" },
  { key: "uptrend_under_pressure", label: "Pressure", tone: "neutral" },
  { key: "confirmed_uptrend", label: "Uptrend", tone: "bull" },
];
const POSTURE_RUNGS: Rung[] = [
  { key: "cash", label: "Cash", tone: "bear" },
  { key: "defensive", label: "Defensive", tone: "bear" },
  { key: "selective", label: "Selective", tone: "neutral" },
  { key: "aggressive", label: "Aggressive", tone: "bull" },
];

export default function RegimePage() {
  const { data: snap, isLoading } = useRegime();
  const refresh = useRefreshRegime();

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Market Regime</h1>
          <p className="mt-1 text-sm text-muted">
            Current market conditions — Dow Theory · Weinstein · O&apos;Neil/Minervini · Murphy
            intermarket. Should you be buying breakouts now?
          </p>
        </div>
        <Button onClick={() => refresh.mutate()} disabled={refresh.isPending}>
          {refresh.isPending ? <Spinner /> : <RefreshCw size={16} />}
          {refresh.isPending ? "Reading the market…" : "Refresh"}
        </Button>
      </div>

      {refresh.isError ? (
        <Card>
          <CardBody className="pt-5 text-sm text-bear">
            Refresh failed: {(refresh.error as Error).message}. Is the worker running
            (`make worker`) and Temporal up (`make temporal-up`)?
          </CardBody>
        </Card>
      ) : null}

      {isLoading ? (
        <Card>
          <CardBody className="flex items-center gap-2 pt-5 text-sm text-muted">
            <Spinner /> Loading latest snapshot…
          </CardBody>
        </Card>
      ) : !snap ? (
        <Card>
          <CardBody className="pt-5 text-sm text-muted">
            No regime snapshot yet — click <span className="font-medium">Refresh</span> to compute
            one.
          </CardBody>
        </Card>
      ) : (
        <>
          {/* Hero: the ladder + meter leveling */}
          <Card>
            <CardBody className="pt-5">
              <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-lg font-semibold">{snap.headline}</div>
                  <div className="text-sm text-muted">{snap.mood}</div>
                </div>
                <div className="flex items-center gap-2 text-xs text-muted">
                  <Badge tone={snap.source === "llm" ? "bull" : "muted"}>
                    Mood by {snap.source === "llm" ? "LLM" : "rules"}
                  </Badge>
                  <span>{new Date(snap.generated_at).toLocaleString()}</span>
                </div>
              </div>
              <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
                <LevelLadder label="Overall regime" rungs={STATE_RUNGS} currentKey={snap.overall_state} />
                <LevelLadder label="Long posture" rungs={POSTURE_RUNGS} currentKey={snap.long_posture} />
                <ScoreMeter score={snap.score} />
              </div>
            </CardBody>
          </Card>

          {/* AI narrative */}
          {snap.narrative ? (
            <Card>
              <CardBody className="pt-5">
                <div className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">
                  The read
                </div>
                <p className="text-sm leading-relaxed">{snap.narrative}</p>
              </CardBody>
            </Card>
          ) : null}

          {/* Pillars */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {(snap.pillars ?? []).map((p) => (
              <PillarCard
                key={p.key}
                pillar={p}
                charts={(snap.charts ?? []).filter((c) => c.pillar_key === p.key)}
              />
            ))}
          </div>

          <p className="pb-4 text-center text-xs text-muted">
            {titleCase(snap.overall_state)} · proxies labelled where exchange-wide breadth data
            isn&apos;t available. Decision support, not financial advice.
          </p>
        </>
      )}
    </div>
  );
}
