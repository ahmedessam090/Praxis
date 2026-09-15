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
export type ScreenerCandidate = S["ScreenerCandidate"];
export type ScreenerGroup = S["ScreenerGroup"];
export type ScreenFactor = S["ScreenFactor"];
export type AlphaItem = S["AlphaItem"];
export type AlphaVerdict = S["AlphaVerdict"];
export type AlphaReason = S["AlphaReason"];
export type DowngradedItem = S["DowngradedItem"];
// Levels-to-watch + notable-gaps attached to each ALPHA item. These derive from the
// generated schemas (api-types.ts already carries them on AlphaItem.levels / .gaps).
export type KeyLevel = S["KeyLevel"];
export type GapNote = S["GapNote"];

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

// ---- Alpha screener ----

export function useScreenerJobs() {
  return useQuery({
    queryKey: ["screener-jobs"],
    queryFn: () => api<{ scan: boolean; evaluate: boolean; refresh: boolean }>(
      "/api/screener/jobs",
    ),
    refetchInterval: 5000,
  });
}

// The named scanner groups (custom / scan / ai). Polled so a freshly-created scan/ai group
// (and its live candidate count) shows up without a manual refresh.
export function useGroups() {
  return useQuery({
    queryKey: ["groups"],
    queryFn: () => api<ScreenerGroup[]>("/api/screener/groups"),
    refetchInterval: 5000,
  });
}

// Poll the lists so they update as Temporal persists results (incrementally, even
// mid-evaluate). Minor delay is fine; these are tiny reads. Pass a group to scope to it;
// omit it to read every candidate. The group is part of the query key so detail views cache
// independently and the right one invalidates.
export function useCandidates(group?: string) {
  return useQuery({
    queryKey: group ? ["candidates", group] : ["candidates"],
    queryFn: () =>
      api<ScreenerCandidate[]>(
        group
          ? `/api/screener/candidates?group=${encodeURIComponent(group)}`
          : "/api/screener/candidates",
      ),
    refetchInterval: 4000,
  });
}

export function useAlpha() {
  return useQuery({
    queryKey: ["alpha"],
    queryFn: () => api<AlphaItem[]>("/api/screener/alpha"),
    refetchInterval: 4000,
  });
}

export function useDowngraded() {
  return useQuery({
    queryKey: ["downgraded"],
    queryFn: () => api<DowngradedItem[]>("/api/screener/downgraded"),
    refetchInterval: 8000,
  });
}

export function useCreateGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      api<ScreenerGroup>("/api/screener/groups", {
        method: "POST",
        body: JSON.stringify({ name }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["groups"] }),
  });
}

export function useDeleteGroup() {
  const qc = useQueryClient();
  return useMutation({
    // Removes the group AND every candidate in it, so both lists must refresh.
    mutationFn: (name: string) =>
      api<{ removed: number }>(`/api/screener/groups/${encodeURIComponent(name)}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["groups"] });
      qc.invalidateQueries({ queryKey: ["candidates"] });
    },
  });
}

export function useAddCandidate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ symbol, group }: { symbol: string; group?: string }) =>
      api<ScreenerCandidate>("/api/screener/candidates", {
        method: "POST",
        body: JSON.stringify({ symbol, ...(group ? { group } : {}) }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["candidates"] });
      qc.invalidateQueries({ queryKey: ["groups"] });
    },
  });
}

export function useRunScan() {
  const qc = useQueryClient();
  return useMutation({
    // The rally-screen: shallow-screens the rallying sectors into `group` (auto-named when
    // omitted). Async like the other workflows — poll status, then refresh groups + candidates.
    mutationFn: async (group?: string) => {
      const qs = group ? `?group=${encodeURIComponent(group)}` : "";
      const { workflow_id } = await api<{ workflow_id: string }>(
        `/api/screener/scan${qs}`,
        { method: "POST" },
      );
      await waitForWorkflow(`/api/screener/status?workflow_id=${workflow_id}`);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["candidates"] });
      qc.invalidateQueries({ queryKey: ["groups"] });
    },
  });
}

export function useAiPick() {
  const qc = useQueryClient();
  return useMutation({
    // Synchronous and slow (~10–25s): the LLM proposes good-performer tickers matching the
    // description, shallow-scores them, and drops them into the group. No polling needed.
    mutationFn: ({ query, group, limit }: { query: string; group?: string; limit?: number }) =>
      api<{ added: number; group: string; symbols: string[] }>("/api/screener/ai-pick", {
        method: "POST",
        body: JSON.stringify({ query, ...(group ? { group } : {}), ...(limit ? { limit } : {}) }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["candidates"] });
      qc.invalidateQueries({ queryKey: ["groups"] });
    },
  });
}

export function useEvaluate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (symbols: string[]) => {
      const { workflow_id } = await api<{ workflow_id: string }>(
        "/api/screener/alpha/evaluate",
        { method: "POST", body: JSON.stringify({ symbols }) },
      );
      await waitForWorkflow(`/api/screener/status?workflow_id=${workflow_id}`);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alpha"] });
      qc.invalidateQueries({ queryKey: ["candidates"] });
    },
  });
}

export function useRefreshAlpha() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (symbols: string[]) => {
      const { workflow_id } = await api<{ workflow_id: string }>(
        "/api/screener/alpha/refresh",
        { method: "POST", body: JSON.stringify({ symbols }) },
      );
      await waitForWorkflow(`/api/screener/status?workflow_id=${workflow_id}`);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alpha"] });
      qc.invalidateQueries({ queryKey: ["downgraded"] });
    },
  });
}

export function useDeleteCandidate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbol: string) =>
      api(`/api/screener/candidates/${encodeURIComponent(symbol)}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["candidates"] });
      qc.invalidateQueries({ queryKey: ["groups"] });
    },
  });
}

export function useClearCandidates() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api("/api/screener/candidates", { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["candidates"] });
      qc.invalidateQueries({ queryKey: ["groups"] });
    },
  });
}
