"use client";

import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  LineSeries,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useTheme } from "next-themes";
import { useEffect, useRef } from "react";
import type { Candle, PriceNote, RegimeChart, Shape } from "@/lib/api";
import { toUnix } from "@/lib/utils";

const UP = "#0a9d6e";
const DOWN = "#e23645";

function themeColors(dark: boolean) {
  return dark
    ? { text: "#8b97a7", grid: "#1a2333", border: "#1e2738" }
    : { text: "#64748b", grid: "#eef0f4", border: "#e6e9ee" };
}

const ROLE_COLOR: Record<string, string> = {
  primary: "#2962ff",
  resistance: "#2962ff",
  neckline: "#2962ff",
  support: "#089981",
  secondary: "#7e57c2",
  context: "#90a4ae",
  target: "#089981",
  stop: "#f23645",
};
const NOTE_COLOR: Record<string, string> = {
  target: "#089981",
  stop: "#f23645",
  entry: "#2962ff",
  breakout: "#2962ff",
  level: "#787b86",
};

function useChart(height: number) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const { resolvedTheme } = useTheme();
  const dark = resolvedTheme === "dark";

  useEffect(() => {
    if (!ref.current) return;
    const c = themeColors(dark);
    const chart = createChart(ref.current, {
      autoSize: true,
      height,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: c.text },
      grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
      rightPriceScale: { borderColor: c.border },
      timeScale: { borderColor: c.border, timeVisible: false },
      crosshair: { mode: 1 },
    });
    chartRef.current = chart;
    const fit = () => {
      try {
        chart.timeScale().fitContent();
      } catch {
        /* noop */
      }
    };
    const ro = new ResizeObserver(fit);
    ro.observe(ref.current);
    setTimeout(fit, 60);
    setTimeout(fit, 300);
    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [dark, height]);

  return { ref, chartRef };
}

/** Ticker candlestick chart with the AI thesis overlaid (rails, price lines, markers). */
export function CandleChart({
  candles,
  shapes = [],
  priceNotes = [],
  height = 460,
}: {
  candles: Candle[];
  shapes?: Shape[];
  priceNotes?: PriceNote[];
  height?: number;
}) {
  const { ref, chartRef } = useChart(height);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || candles.length === 0) return;
    const candle = chart.addSeries(CandlestickSeries, {
      upColor: UP,
      downColor: DOWN,
      borderVisible: false,
      wickUpColor: UP,
      wickDownColor: DOWN,
    });
    candle.setData(
      candles.map((b) => ({
        time: b.time as UTCTimestamp,
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      })),
    );
    const start = candles[0].time;
    const markers: SeriesMarker<Time>[] = [];
    for (const sh of shapes) {
      const pts = sh.points ?? [];
      if ((sh.kind === "trendline" || sh.kind === "curve") && pts.length >= 2) {
        const data = pts
          .map((p) => ({ time: toUnix(p.ts) as UTCTimestamp, value: p.price }))
          .filter((d) => d.time >= start)
          .sort((a, b) => a.time - b.time);
        if (data.length >= 2) {
          const line = chart.addSeries(LineSeries, {
            color: sh.color || ROLE_COLOR[sh.role] || "#7e57c2",
            lineWidth: 2,
            priceLineVisible: false,
            lastValueVisible: false,
          });
          line.setData(data);
        }
      } else if (sh.kind === "marker") {
        for (const p of pts) {
          const t = toUnix(p.ts);
          if (t >= start)
            markers.push({
              time: t as UTCTimestamp,
              position: "belowBar",
              color: sh.color || ROLE_COLOR[sh.role] || "#787b86",
              shape: "circle",
              text: sh.label,
            });
        }
      }
    }
    for (const n of priceNotes) {
      candle.createPriceLine({
        price: n.price,
        color: NOTE_COLOR[n.kind] || "#2962ff",
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: n.label,
      });
    }
    if (markers.length) {
      markers.sort((a, b) => (a.time as number) - (b.time as number));
      createSeriesMarkers(candle, markers);
    }
    chart.timeScale().fitContent();
    return () => {
      try {
        chart.removeSeries(candle);
      } catch {
        /* chart already disposed */
      }
    };
  }, [candles, shapes, priceNotes, chartRef]);

  return <div ref={ref} style={{ width: "100%", height }} />;
}

/** Render one RegimeChart (candle or line series + markers) from the API. */
export function RegimeChartView({ chart, height = 300 }: { chart: RegimeChart; height?: number }) {
  const { ref, chartRef } = useChart(height);

  useEffect(() => {
    const c = chartRef.current;
    if (!c) return;
    const created: ReturnType<IChartApi["addSeries"]>[] = [];
    let anchor: ReturnType<IChartApi["addSeries"]> | null = null;
    for (const s of chart.series ?? []) {
      if (s.kind === "candle") {
        const cs = c.addSeries(CandlestickSeries, {
          upColor: UP,
          downColor: DOWN,
          borderVisible: false,
          wickUpColor: UP,
          wickDownColor: DOWN,
        });
        cs.setData(
          (s.candles ?? []).map((k) => ({
            time: toUnix(k.ts) as UTCTimestamp,
            open: k.open,
            high: k.high,
            low: k.low,
            close: k.close,
          })),
        );
        created.push(cs);
        anchor ??= cs;
      } else {
        const ls = c.addSeries(LineSeries, {
          color: s.color || "#2962ff",
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: true,
        });
        ls.setData(
          (s.points ?? []).map((p) => ({ time: toUnix(p.ts) as UTCTimestamp, value: p.value })),
        );
        created.push(ls);
        anchor ??= ls;
      }
    }
    const rawMarkers = chart.markers ?? [];
    if (rawMarkers.length && anchor) {
      const markers = rawMarkers
        .map((m) => ({
          time: toUnix(m.ts) as UTCTimestamp,
          position: m.position || "belowBar",
          color: m.color || "#787b86",
          shape: m.shape || "circle",
          text: m.label,
        }))
        .sort((a, b) => (a.time as number) - (b.time as number)) as SeriesMarker<Time>[];
      createSeriesMarkers(anchor, markers);
    }
    c.timeScale().fitContent();
    return () => {
      for (const s of created) {
        try {
          c.removeSeries(s);
        } catch {
          /* chart already disposed */
        }
      }
    };
  }, [chart, chartRef]);

  return <div ref={ref} style={{ width: "100%", height }} />;
}
