import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "./api-types";

type S = components["schemas"];
export type RegimeSnapshot = S["RegimeSnapshot"];
export type RegimePillar = S["RegimePillar"];
export type RegimeMetric = S["RegimeMetric"];
export type RegimeChart = S["RegimeChart"];
export type RegimeSeries = S["RegimeSeries"];
export type RegimePoint = S["RegimePoint"];
export type RegimeCandle = S["RegimeCandle"];
export type ChartMarker = S["ChartMarker"];
export type TickerAnalysis = S["TickerAnalysis"];
export type TimeframeThesis = S["TimeframeThesis"];
export type Candle = S["Candle"];
export type Shape = S["Shape"];
export type PriceNote = S["PriceNote"];
export type AnalyticalNote = S["AnalyticalNote"];
export type IndicatorSnapshot = S["IndicatorSnapshot"];

export type LlmUsage = {
  enabled: boolean;
  ui_url: string;
  provider: string;
  model: string | null;
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new Error(`${init?.method ?? "GET"} ${path} → ${res.status}`);
  return (await res.json()) as T;
}

const TERMINAL_OK = "COMPLETED";
const TERMINAL_BAD = ["FAILED", "TERMINATED", "TIMED_OUT", "CANCELED"];

async function waitForWorkflow(statusPath: string): Promise<void> {
  for (let i = 0; i < 240; i++) {
    const { status } = await api<{ status: string }>(statusPath);
    if (status === TERMINAL_OK) return;
    if (TERMINAL_BAD.includes(status)) throw new Error(`Workflow ${status}`);
    await sleep(2500);
  }
  throw new Error("Workflow timed out");
}

// ---- Market Regime ----

export function useRegime() {
  return useQuery({
    queryKey: ["regime"],
    queryFn: () => api<RegimeSnapshot | null>("/api/regime/latest"),
  });
}

export function useRefreshRegime() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { workflow_id } = await api<{ workflow_id: string }>("/api/regime/refresh", {
        method: "POST",
      });
      await waitForWorkflow(`/api/regime/status?workflow_id=${workflow_id}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["regime"] }),
  });
}

// ---- Ticker Analysis ----

export function useAnalysis(symbol: string) {
  return useQuery({
    queryKey: ["analysis", symbol],
    queryFn: () => api<TickerAnalysis | null>(`/api/analysis/${encodeURIComponent(symbol)}`),
    enabled: symbol.length > 0,
  });
}

export function useRefreshAnalysis(symbol: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { workflow_id } = await api<{ workflow_id: string }>("/api/analysis/refresh", {
        method: "POST",
        body: JSON.stringify({ symbol }),
      });
      await waitForWorkflow(`/api/analysis/status/${workflow_id}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["analysis", symbol] }),
  });
}

export function useBars(symbol: string, timeframe: string) {
  return useQuery({
    queryKey: ["bars", symbol, timeframe],
    queryFn: () =>
      api<Candle[]>(`/api/bars?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`),
    enabled: symbol.length > 0,
  });
}

export function useLlmUsage() {
  return useQuery({ queryKey: ["llm-usage"], queryFn: () => api<LlmUsage>("/api/llm/usage") });
}
