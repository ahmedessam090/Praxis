"use client";

import { Search } from "lucide-react";
import { useEffect, useState } from "react";
import { CandleChart } from "@/components/charts/charts";
import { ThesisCard } from "@/components/ticker/thesis-card";
import {
  Badge,
  Button,
  Card,
  CardBody,
  Input,
  Spinner,
} from "@/components/ui/primitives";
import { useAnalysis, useBars, useRefreshAnalysis } from "@/lib/api";
import { cn, fmt, statusColor } from "@/lib/utils";

const SEVERITY: Record<string, string> = {
  warning: "text-bear",
  caution: "text-neutral",
  info: "text-muted",
};

export default function TickerPage() {
  const [input, setInput] = useState("AAPL");
  const [symbol, setSymbol] = useState("AAPL");
  const [tf, setTf] = useState("daily");

  const { data: analysis, isLoading } = useAnalysis(symbol);
  const refresh = useRefreshAnalysis(symbol);
  const { data: bars } = useBars(symbol, tf);

  useEffect(() => {
    if (analysis?.timeframes?.length && !(analysis.timeframes as string[]).includes(tf)) {
      setTf(analysis.timeframes[0]);
    }
  }, [analysis, tf]);

  const run = () => {
    setSymbol(input.trim().toUpperCase());
    refresh.mutate();
  };
  const thesis = analysis?.theses?.find((t) => t.timeframe === tf) ?? null;
  const dailyInd = analysis?.indicators?.find((i) => i.timeframe === "daily");

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Ticker Analysis</h1>
        <p className="mt-1 text-sm text-muted">
          The AI chartist&apos;s per-timeframe read, drawn on candlesticks.
        </p>
      </div>

      <div className="flex items-center gap-2">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && run()}
          placeholder="Ticker, e.g. AAPL"
          className="w-44 uppercase"
        />
        <Button onClick={run} disabled={refresh.isPending || !input.trim()}>
          {refresh.isPending ? <Spinner /> : <Search size={16} />}
          {refresh.isPending ? "Analyzing…" : "Analyze"}
        </Button>
      </div>

      {refresh.isError ? (
        <Card>
          <CardBody className="pt-5 text-sm text-bear">
            Analysis failed: {(refresh.error as Error).message}.
          </CardBody>
        </Card>
      ) : null}

      {isLoading ? (
        <Card>
          <CardBody className="flex items-center gap-2 pt-5 text-sm text-muted">
            <Spinner /> Loading…
          </CardBody>
        </Card>
      ) : !analysis ? (
        <Card>
          <CardBody className="pt-5 text-sm text-muted">
            No stored analysis for {symbol}. Click <span className="font-medium">Analyze</span>.
          </CardBody>
        </Card>
      ) : (
        <>
          <Card>
            <CardBody className="pt-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <span className="text-lg font-semibold">{analysis.symbol}</span>
                  <Badge tone={statusColor(analysis.summary.overall_bias)}>
                    {analysis.summary.overall_bias}
                  </Badge>
                  <span className="text-sm text-muted">
                    last {fmt(analysis.summary.price_now)}
                  </span>
                </div>
                {dailyInd ? (
                  <div className="flex gap-4 text-xs text-muted">
                    <span>RSI {dailyInd.rsi14 ? dailyInd.rsi14.toFixed(0) : "—"}</span>
                    <span>ATR {dailyInd.atr_pct ? dailyInd.atr_pct.toFixed(1) + "%" : "—"}</span>
                    <span>Trend tmpl {dailyInd.trend_template_pass ? "PASS" : "no"}</span>
                  </div>
                ) : null}
              </div>
              <p className="mt-2 text-sm font-medium">{analysis.summary.headline}</p>
              {analysis.summary.narrative ? (
                <p className="mt-1 text-sm leading-relaxed text-muted">
                  {analysis.summary.narrative}
                </p>
              ) : null}
              {(analysis.notes ?? []).length > 0 ? (
                <div className="mt-3 space-y-1">
                  {(analysis.notes ?? []).map((n, i) => (
                    <div key={i} className={cn("text-xs", SEVERITY[n.severity] ?? "text-muted")}>
                      • {n.message}
                    </div>
                  ))}
                </div>
              ) : null}
            </CardBody>
          </Card>

          {/* timeframe tabs */}
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

          <Card>
            <CardBody className="pt-4">
              {bars && bars.length > 0 ? (
                <CandleChart
                  candles={bars}
                  shapes={thesis?.shapes ?? []}
                  priceNotes={thesis?.price_notes ?? []}
                />
              ) : (
                <div className="py-10 text-center text-sm text-muted">No bars for this timeframe.</div>
              )}
            </CardBody>
          </Card>

          {thesis ? <ThesisCard thesis={thesis} /> : null}
        </>
      )}

      <p className="pb-4 text-center text-xs text-muted">
        An LLM&apos;s reading of chart geometry, not a recommendation — entry/target/stop are
        measured levels, not price predictions. Decision support, not financial advice; you
        place every trade. Capital at risk.
      </p>
    </div>
  );
}
