"use client";

import { ArrowLeft, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { CandleChart } from "@/components/charts/charts";
import { AlphaVerdictCard } from "@/components/screener/alpha-verdict-card";
import { LevelsToWatch, NotableGaps } from "@/components/screener/screener-ui";
import { ThesisCard } from "@/components/ticker/thesis-card";
import { Card, CardBody, GhostButton, Spinner } from "@/components/ui/primitives";
import { type AlphaItem, useAnalysis, useBars, useRefreshAlpha } from "@/lib/api";
import { cn } from "@/lib/utils";

export function AlphaDetail({ item, onBack }: { item: AlphaItem; onBack: () => void }) {
  const symbol = item.symbol;
  const [tf, setTf] = useState("daily");
  const { data: analysis } = useAnalysis(symbol);
  const { data: bars } = useBars(symbol, tf);
  const refresh = useRefreshAlpha();

  useEffect(() => {
    if (analysis?.timeframes?.length && !(analysis.timeframes as string[]).includes(tf)) {
      setTf(analysis.timeframes[0]);
    }
  }, [analysis, tf]);

  const thesis = analysis?.theses?.find((t) => t.timeframe === tf) ?? null;
  const levels = item.levels ?? [];
  const gaps = item.gaps ?? [];
  const hasLevelsOrGaps = levels.length > 0 || gaps.length > 0;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <GhostButton onClick={onBack}>
            <ArrowLeft size={16} /> Back
          </GhostButton>
          <span className="text-lg font-semibold">{symbol}</span>
          <span className="text-sm text-muted">{item.verdict.sector}</span>
        </div>
        <GhostButton onClick={() => refresh.mutate([symbol])} disabled={refresh.isPending}>
          {refresh.isPending ? <Spinner /> : <RefreshCw size={16} />}
          Refresh
        </GhostButton>
      </div>

      <AlphaVerdictCard
        verdict={item.verdict}
        triggerZone={
          thesis ? { low: thesis.trigger_zone_low, high: thesis.trigger_zone_high } : undefined
        }
      />

      {hasLevelsOrGaps ? (
        <Card>
          <CardBody className="flex flex-col gap-5 pt-5">
            <LevelsToWatch levels={levels} />
            <NotableGaps gaps={gaps} />
          </CardBody>
        </Card>
      ) : null}

      {analysis?.timeframes?.length ? (
        <div className="flex gap-1 rounded-lg border border-border bg-surface p-1">
          {(analysis.timeframes ?? []).map((t) => (
            <button
              key={t}
              onClick={() => setTf(t)}
              className={cn(
                "flex-1 rounded-md px-3 py-1.5 text-sm font-medium capitalize transition",
                tf === t ? "bg-brand/15 text-brand" : "text-muted hover:text-foreground",
              )}
            >
              {t}
            </button>
          ))}
        </div>
      ) : null}

      <Card>
        <CardBody className="pt-4">
          {bars && bars.length > 0 ? (
            <CandleChart
              candles={bars}
              shapes={thesis?.shapes ?? []}
              priceNotes={thesis?.price_notes ?? []}
            />
          ) : (
            <div className="py-10 text-center text-sm text-muted">
              Analysis still loading or unavailable — try Refresh.
            </div>
          )}
        </CardBody>
      </Card>

      {thesis ? <ThesisCard thesis={thesis} /> : null}
    </div>
  );
}
