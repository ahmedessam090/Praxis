"use client";

import {
  ArrowDownRight,
  ChevronDown,
  ChevronRight,
  HelpCircle,
  Layers,
  Plus,
  RefreshCw,
  Radar,
  Search,
  Sparkles,
  Target,
  Trash2,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AlphaDetail } from "@/components/screener/alpha-detail";
import { AlphaVerdictCard } from "@/components/screener/alpha-verdict-card";
import {
  ConvictionRing,
  FactorTag,
  ScoreBar,
  SectorChip,
  StatusPill,
} from "@/components/screener/screener-ui";
import {
  Badge,
  Button,
  Card,
  CardBody,
  GhostButton,
  Input,
  Spinner,
} from "@/components/ui/primitives";
import {
  type AlphaItem,
  type ScreenerCandidate,
  useAddCandidate,
  useAlpha,
  useCandidates,
  useClearCandidates,
  useDeleteCandidate,
  useDowngraded,
  useEvaluate,
  useRefreshAlpha,
  useRunScan,
  useScreenerJobs,
} from "@/lib/api";
import { cn, fmt, fmtSigned } from "@/lib/utils";

type Tab = "scanner" | "alpha" | "downgraded";

const DOT: Record<string, string> = { bull: "bg-bull", neutral: "bg-neutral", bear: "bg-bear" };

/** Friendly, on-theme empty state shared across the tabs. */
function EmptyState({
  icon: Icon,
  title,
  hint,
}: {
  icon: typeof Search;
  title: string;
  hint: React.ReactNode;
}) {
  return (
    <Card>
      <CardBody className="flex flex-col items-center justify-center gap-3 py-14 text-center">
        <span className="flex h-12 w-12 items-center justify-center rounded-full border border-border bg-surface text-muted">
          <Icon size={22} />
        </span>
        <div className="text-sm font-medium">{title}</div>
        <p className="max-w-sm text-sm text-muted">{hint}</p>
      </CardBody>
    </Card>
  );
}

const COL_COUNT = 7;

/** The verdict detail shown inline beneath a row when "Why?" is expanded. */
function WhyDetail({ c }: { c: ScreenerCandidate }) {
  if (!c.verdict) return null;
  return (
    <div className="space-y-3 border-l-2 border-brand/60 bg-surface/30 px-4 py-3.5 pl-5">
      <div className="flex items-center gap-2 text-xs font-medium">
        <HelpCircle size={14} className="text-brand" />
        <span>
          Why {c.symbol} is{" "}
          <span className={c.verdict.is_alpha ? "text-bull" : "text-muted"}>
            {c.verdict.is_alpha ? "ALPHA" : "not alpha"}
          </span>
        </span>
      </div>
      <AlphaVerdictCard verdict={c.verdict} />
      {c.verdict.inputs ? (
        <details>
          <summary className="cursor-pointer text-xs font-medium text-brand">
            Inputs the agent received
          </summary>
          <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-surface p-3 text-[11px] text-muted">
            {c.verdict.inputs}
          </pre>
        </details>
      ) : null}
    </div>
  );
}

function CandidateRow({
  c,
  checked,
  evaluating,
  expanded,
  onToggle,
  onDelete,
  onWhy,
}: {
  c: ScreenerCandidate;
  checked: boolean;
  evaluating: boolean;
  expanded: boolean;
  onToggle: () => void;
  onDelete: () => void;
  onWhy: () => void;
}) {
  const status = evaluating && c.status === "pending" ? "evaluating" : c.status;
  const factors = c.factors ?? [];
  return (
    <>
      <tr
        className={cn(
          "border-b transition-colors",
          expanded ? "border-transparent" : "border-border/60",
          checked
            ? "bg-brand/[0.06]"
            : expanded
              ? "bg-surface/50"
              : "odd:bg-surface/20 hover:bg-surface/60",
        )}
      >
        <td className="w-9 px-3 py-2.5">
          <div className="flex items-center">
            <span
              aria-hidden
              className={cn(
                "-ml-3 mr-2 h-7 w-0.5 rounded-full transition-colors",
                checked ? "bg-brand" : "bg-transparent",
              )}
            />
            <input
              type="checkbox"
              checked={checked}
              onChange={onToggle}
              className="h-3.5 w-3.5 accent-brand"
            />
          </div>
        </td>
        <td className="px-3 py-2.5">
          <div className="flex items-center gap-2">
            <span className="font-semibold tracking-tight">{c.symbol}</span>
            {c.source === "llm" ? (
              <span className="rounded border border-border px-1 py-px text-[9px] font-medium uppercase tracking-wide text-muted">
                LLM
              </span>
            ) : null}
          </div>
        </td>
        <td className="px-3 py-2.5">
          <SectorChip sector={c.sector} />
        </td>
        <td className="px-3 py-2.5">
          <ScoreBar score={c.score} />
        </td>
        <td className="w-28 px-3 py-2.5">
          <StatusPill status={status} />
        </td>
        <td className="px-3 py-2.5">
          {factors.length === 0 ? (
            <span className="text-xs text-muted">—</span>
          ) : (
            <div className="flex flex-nowrap items-center gap-1.5 overflow-hidden">
              {factors.slice(0, 3).map((f, i) => (
                <FactorTag
                  key={i}
                  label={f.label}
                  value={f.value}
                  status={f.status ?? "neutral"}
                />
              ))}
              {factors.length > 3 && (
                <span
                  title={factors
                    .slice(3)
                    .map((f) => `${f.label} ${f.value}`)
                    .join(" · ")}
                  className="inline-flex shrink-0 items-center rounded-md border border-border/60 bg-surface/60 px-1.5 py-0.5 text-[11px] text-muted"
                >
                  +{factors.length - 3}
                </span>
              )}
            </div>
          )}
        </td>
        <td className="w-24 px-3 py-2.5">
          <div className="flex items-center justify-end gap-0.5">
            {c.verdict ? (
              <button
                onClick={onWhy}
                aria-expanded={expanded}
                className={cn(
                  "inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition",
                  expanded
                    ? "bg-brand/10 text-brand"
                    : "text-brand hover:bg-brand/10",
                )}
              >
                Why?
                <ChevronDown
                  size={13}
                  className={cn("transition-transform", expanded && "rotate-180")}
                />
              </button>
            ) : null}
            <button
              onClick={onDelete}
              className="rounded-md p-1.5 text-muted transition hover:bg-bear/10 hover:text-bear"
              aria-label="delete"
            >
              <Trash2 size={15} />
            </button>
          </div>
        </td>
      </tr>
      <tr className={cn(!expanded && "border-b border-border/60", checked && "bg-brand/[0.06]")}>
        <td colSpan={COL_COUNT} className="p-0">
          <div
            className={cn(
              "grid transition-all duration-300 ease-out",
              expanded ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0",
            )}
          >
            <div className="overflow-hidden">{expanded ? <WhyDetail c={c} /> : null}</div>
          </div>
        </td>
      </tr>
    </>
  );
}

function AlphaCard({ item, onView }: { item: AlphaItem; onView: () => void }) {
  const v = item.verdict;
  const conv = Math.max(0, Math.min(100, v.conviction ?? 0));
  const refresh = useRefreshAlpha();
  const reasons = (v.reasons ?? []).slice(0, 3);
  const levelCount = item.levels?.length ?? 0;
  const gapCount = item.gaps?.length ?? 0;
  const nearestLevel = item.levels?.[0];
  return (
    <Card
      onClick={onView}
      className="group cursor-pointer transition hover:border-brand/40 hover:shadow-md"
    >
      <CardBody className="pt-4">
        <div className="flex items-start gap-3">
          <ConvictionRing value={conv} size={60} />
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-base font-semibold tracking-tight">{item.symbol}</span>
                {v.is_alpha ? <Badge tone="bull">★ ALPHA</Badge> : null}
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  refresh.mutate([item.symbol]);
                }}
                disabled={refresh.isPending}
                className="rounded-md p-1.5 text-muted transition hover:bg-surface hover:text-foreground disabled:opacity-50"
                aria-label="refresh"
              >
                {refresh.isPending ? <Spinner /> : <RefreshCw size={15} />}
              </button>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              {v.sector ? <SectorChip sector={v.sector} /> : null}
              {v.regime_alignment ? (
                <span className="inline-flex items-center gap-1 text-[11px] text-muted">
                  <span className="h-1 w-1 rounded-full bg-muted" />
                  {v.regime_alignment} regime
                </span>
              ) : null}
              {v.stage ? (
                <span className="text-[11px] capitalize text-muted">{v.stage}</span>
              ) : null}
            </div>
          </div>
        </div>

        <div className="mt-3 grid grid-cols-4 divide-x divide-border/60 rounded-lg border border-border/60 bg-surface/40 text-center">
          {[
            { label: "Entry", value: fmt(v.entry), text: "text-foreground" },
            { label: "Stop", value: fmt(v.stop), text: "text-bear" },
            { label: "Target", value: fmt(v.target), text: "text-bull" },
            { label: "R : R", value: fmt(v.rr), text: "text-foreground" },
          ].map((s) => (
            <div key={s.label} className="px-1 py-2">
              <div className="text-[10px] uppercase tracking-wide text-muted">{s.label}</div>
              <div className={cn("text-sm font-semibold tabular-nums", s.text)}>{s.value}</div>
            </div>
          ))}
        </div>

        {v.summary ? (
          <p className="mt-3 line-clamp-2 text-sm leading-relaxed text-muted">{v.summary}</p>
        ) : null}

        {reasons.length > 0 ? (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {reasons.map((r, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1.5 rounded-md border border-border/60 bg-surface/60 px-2 py-0.5 text-[11px] capitalize text-muted"
              >
                <span
                  className={cn(
                    "h-1.5 w-1.5 rounded-full",
                    r.status === "bullish"
                      ? DOT.bull
                      : r.status === "bearish"
                        ? DOT.bear
                        : DOT.neutral,
                  )}
                />
                {r.category}
              </span>
            ))}
          </div>
        ) : null}

        {levelCount > 0 || gapCount > 0 ? (
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted">
            {nearestLevel ? (
              <span className="inline-flex items-center gap-1">
                <Target size={12} className="text-brand" />
                <span className="font-medium text-foreground">{fmt(nearestLevel.price)}</span>
                <span className="capitalize">{nearestLevel.label}</span>
                <span
                  className={cn(
                    "tabular-nums",
                    nearestLevel.distance_pct > 0
                      ? "text-bull"
                      : nearestLevel.distance_pct < 0
                        ? "text-bear"
                        : "text-muted",
                  )}
                >
                  {fmtSigned(nearestLevel.distance_pct, 1)}%
                </span>
              </span>
            ) : null}
            {levelCount > 1 ? <span>+{levelCount - 1} more levels</span> : null}
            {gapCount > 0 ? (
              <span className="inline-flex items-center gap-1">
                <Layers size={12} />
                {gapCount} {gapCount === 1 ? "gap" : "gaps"}
              </span>
            ) : null}
          </div>
        ) : null}

        <div className="mt-3 flex items-center justify-end border-t border-border/60 pt-2">
          <span className="inline-flex items-center gap-1 text-xs font-medium text-brand transition group-hover:gap-1.5">
            View detail
            <ChevronRight size={14} className="transition-transform group-hover:translate-x-0.5" />
          </span>
        </div>
      </CardBody>
    </Card>
  );
}

export default function ScreenerPage() {
  const [tab, setTab] = useState<Tab>("scanner");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [detail, setDetail] = useState<AlphaItem | null>(null);
  // Which candidate row has its inline "Why?" accordion open (one at a time).
  const [expanded, setExpanded] = useState<string | null>(null);
  const [addSym, setAddSym] = useState("");

  const jobs = useScreenerJobs();
  const add = useAddCandidate();
  const candidates = useCandidates();
  const alpha = useAlpha();
  const downgraded = useDowngraded();
  const scan = useRunScan();
  const evaluate = useEvaluate();
  const refreshAll = useRefreshAlpha();
  const del = useDeleteCandidate();
  const clear = useClearCandidates();

  const cands = useMemo(() => candidates.data ?? [], [candidates.data]);
  const j = jobs.data;
  const scanBusy = scan.isPending || (j?.scan ?? false);
  const evalBusy = evaluate.isPending || (j?.evaluate ?? false);
  const refreshBusy = refreshAll.isPending || (j?.refresh ?? false);

  // Keep selection + the open accordion in sync with the live candidate list: prune any
  // symbol that no longer exists (deleted/cleared) so stale checkboxes never linger, and
  // drop the count/select-all into a consistent state after any action settles.
  useEffect(() => {
    const live = new Set(cands.map((c) => c.symbol));
    setSelected((prev) => {
      const next = new Set([...prev].filter((s) => live.has(s)));
      return next.size === prev.size ? prev : next;
    });
    setExpanded((prev) => (prev && !live.has(prev) ? null : prev));
  }, [cands]);

  const toggle = (sym: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(sym)) next.delete(sym);
      else next.add(sym);
      return next;
    });
  const allChecked = cands.length > 0 && cands.every((c) => selected.has(c.symbol));

  // Summary header data — leading sectors by candidate count.
  const sectorCounts = cands.reduce<Record<string, number>>((acc, c) => {
    if (c.sector) acc[c.sector] = (acc[c.sector] ?? 0) + 1;
    return acc;
  }, {});
  const leadingSectors = Object.entries(sectorCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([s]) => s);

  const alphaCount = alpha.data?.length ?? 0;
  const downCount = downgraded.data?.length ?? 0;

  if (detail) {
    return (
      <div className="mx-auto max-w-6xl">
        <AlphaDetail item={detail} onBack={() => setDetail(null)} />
      </div>
    );
  }

  const TAB_META: Record<Tab, { label: string; count: number }> = {
    scanner: { label: "Scanner", count: cands.length },
    alpha: { label: "ALPHA", count: alphaCount },
    downgraded: { label: "Downgraded", count: downCount },
  };

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Stock Screener</h1>
        <p className="mt-1 text-sm text-muted">
          Scan for candidates riding the leading sectors, then judge them as alpha opportunities.
        </p>
      </div>

      <div className="flex gap-1 rounded-xl border border-border bg-surface p-1">
        {(["scanner", "alpha", "downgraded"] as Tab[]).map((t) => {
          const meta = TAB_META[t];
          const active = tab === t;
          return (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                "flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition",
                active
                  ? "bg-brand/15 text-brand shadow-sm"
                  : "text-muted hover:bg-card hover:text-foreground",
              )}
            >
              {meta.label}
              {meta.count > 0 ? (
                <span
                  className={cn(
                    "rounded-full px-1.5 py-px text-[10px] font-semibold tabular-nums",
                    active ? "bg-brand/20 text-brand" : "bg-border text-muted",
                  )}
                >
                  {meta.count}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      {tab === "scanner" ? (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={() => scan.mutate()} disabled={scanBusy}>
              {scanBusy ? <Spinner /> : <Search size={16} />}
              {scan.isPending ? "Scanning…" : "Run Scanner"}
            </Button>
            <Button
              onClick={() =>
                evaluate.mutate([...selected], { onSuccess: () => setSelected(new Set()) })
              }
              disabled={evalBusy || selected.size === 0}
            >
              {evaluate.isPending ? <Spinner /> : <Sparkles size={16} />}
              {evaluate.isPending
                ? "Evaluating…"
                : `Evaluate selected → Alpha${selected.size ? ` (${selected.size})` : ""}`}
            </Button>
            <GhostButton
              onClick={() => clear.mutate(undefined, { onSuccess: () => setSelected(new Set()) })}
              disabled={cands.length === 0}
            >
              <Trash2 size={15} /> Clear all
            </GhostButton>
            <div className="ml-auto flex items-center gap-2">
              <Input
                value={addSym}
                onChange={(e) => setAddSym(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && addSym.trim())
                    add.mutate(addSym.trim().toUpperCase(), { onSuccess: () => setAddSym("") });
                }}
                placeholder="Add ticker…"
                className="w-36 uppercase"
              />
              <GhostButton
                onClick={() =>
                  add.mutate(addSym.trim().toUpperCase(), { onSuccess: () => setAddSym("") })
                }
                disabled={!addSym.trim() || add.isPending}
              >
                {add.isPending ? <Spinner /> : <Plus size={15} />} Add
              </GhostButton>
            </div>
          </div>
          {add.isError ? (
            <div className="text-xs text-bear">
              Couldn&apos;t add that ticker — check the symbol exists and has data.
            </div>
          ) : null}
          {scan.isError || evaluate.isError ? (
            <Card>
              <CardBody className="pt-5 text-sm text-bear">
                Job failed: {((scan.error || evaluate.error) as Error)?.message}. Is the worker +
                Temporal running?
              </CardBody>
            </Card>
          ) : null}
          {cands.length === 0 ? (
            <EmptyState
              icon={Radar}
              title="No candidates yet"
              hint={
                <>
                  Click <span className="font-medium text-foreground">Run Scanner</span> to sweep
                  the leading sectors, or add a ticker manually above.
                </>
              }
            />
          ) : (
            <Card className="overflow-hidden">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-border bg-surface/40 px-4 py-2.5 text-xs text-muted">
                <span className="font-medium text-foreground">{cands.length}</span> candidates
                {selected.size > 0 ? (
                  <>
                    <span className="text-border">·</span>
                    <span className="font-medium text-brand">{selected.size} selected</span>
                  </>
                ) : null}
                {leadingSectors.length > 0 ? (
                  <>
                    <span className="text-border">·</span>
                    <span>favouring</span>
                    <span className="flex flex-wrap gap-1">
                      {leadingSectors.map((s) => (
                        <SectorChip key={s} sector={s} />
                      ))}
                    </span>
                  </>
                ) : null}
              </div>
              <CardBody className="overflow-x-auto px-0 pb-0 pt-0">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 z-1 bg-card/95 text-left text-[11px] uppercase tracking-wide text-muted backdrop-blur">
                    <tr className="border-b border-border">
                      <th className="w-9 px-3 py-2.5 font-medium">
                        <input
                          type="checkbox"
                          checked={allChecked}
                          onChange={() =>
                            setSelected(
                              allChecked ? new Set() : new Set(cands.map((c) => c.symbol)),
                            )
                          }
                          className="h-3.5 w-3.5 accent-brand"
                          aria-label="select all"
                        />
                      </th>
                      <th className="px-3 py-2.5 font-medium">Symbol</th>
                      <th className="px-3 py-2.5 font-medium">Sector</th>
                      <th className="px-3 py-2.5 font-medium">Score</th>
                      <th className="w-28 px-3 py-2.5 font-medium">Status</th>
                      <th className="px-3 py-2.5 font-medium">Factors</th>
                      <th className="w-24 px-3 py-2.5 text-right font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cands.map((c) => (
                      <CandidateRow
                        key={c.symbol}
                        c={c}
                        checked={selected.has(c.symbol)}
                        evaluating={evalBusy && selected.has(c.symbol)}
                        expanded={expanded === c.symbol}
                        onToggle={() => toggle(c.symbol)}
                        onDelete={() => del.mutate(c.symbol)}
                        onWhy={() =>
                          setExpanded((prev) => (prev === c.symbol ? null : c.symbol))
                        }
                      />
                    ))}
                  </tbody>
                </table>
              </CardBody>
            </Card>
          )}
        </>
      ) : null}

      {tab === "alpha" ? (
        <>
          <div className="flex items-center justify-between gap-2">
            <Button
              onClick={() => refreshAll.mutate([])}
              disabled={refreshBusy || alphaCount === 0}
            >
              {refreshAll.isPending ? <Spinner /> : <RefreshCw size={16} />}
              {refreshAll.isPending ? "Refreshing…" : "Refresh all"}
            </Button>
            {alphaCount > 0 ? (
              <span className="text-xs text-muted">
                <span className="font-medium text-foreground">{alphaCount}</span> live alpha{" "}
                {alphaCount === 1 ? "name" : "names"}
              </span>
            ) : null}
          </div>
          {alphaCount === 0 ? (
            <EmptyState
              icon={Sparkles}
              title="No alpha names yet"
              hint={
                <>
                  Select candidates in the{" "}
                  <span className="font-medium text-foreground">Scanner</span> tab and hit{" "}
                  <span className="font-medium text-foreground">Evaluate → Alpha</span> to surface
                  high-conviction setups here.
                </>
              }
            />
          ) : (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              {(alpha.data ?? []).map((item) => (
                <AlphaCard key={item.symbol} item={item} onView={() => setDetail(item)} />
              ))}
            </div>
          )}
        </>
      ) : null}

      {tab === "downgraded" ? (
        downCount === 0 ? (
          <EmptyState
            icon={ArrowDownRight}
            title="Nothing downgraded"
            hint="When a refreshed alpha name loses conviction, it'll drop here with the reason it was cut."
          />
        ) : (
          <div className="flex flex-col gap-2">
            {(downgraded.data ?? []).map((d) => (
              <Card key={d.symbol} className="bg-card/60">
                <CardBody className="flex items-start justify-between gap-4 pt-4">
                  <div className="flex min-w-0 items-start gap-3">
                    <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-bear/10 text-bear">
                      <ArrowDownRight size={15} />
                    </span>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold tracking-tight">{d.symbol}</span>
                        <span className="inline-flex items-center gap-1 text-xs text-muted">
                          <span className="text-bull/80">conv {d.prior_conviction}</span>
                          <span className="text-border">→</span>
                          <Badge tone="bear">downgraded</Badge>
                        </span>
                      </div>
                      <p className="mt-1 text-sm text-muted">{d.downgrade_reason}</p>
                    </div>
                  </div>
                  <span className="shrink-0 text-xs text-muted">
                    {new Date(d.downgraded_at).toLocaleDateString()}
                  </span>
                </CardBody>
              </Card>
            ))}
          </div>
        )
      ) : null}
    </div>
  );
}
