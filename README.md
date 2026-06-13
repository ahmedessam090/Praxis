# TA Assistant — Technical-Analysis Swing-Trading Decision-Support

A **personal, local-only** decision-support analyst for **LONG-side** swing trading based
on **classical technical analysis** (breakout + range trading within chart patterns,
Peter Brandt / Mark Minervini style). It detects patterns, annotates charts, and argues a
reasoned case — **you always place the trades.** Not short selling, not day trading, not
fundamentals, not auto-execution.

Every analysis runs as a **durable [Temporal](https://temporal.io) workflow** of
**activities**, so it survives worker crashes and retries transient failures without
redoing completed work.

**Detection is hybrid:** deterministic code (numpy/scipy) finds the swing pivots, fits the
trendlines, and computes the *exact* levels — neckline, breakout, measured-move target,
stop, prior resistance — then **OpenAI's vision model** validates/scores the candidate over
the annotated chart and writes the rationale. Exact, reproducible levels + LLM judgment.

> **Status: Phase 1 COMPLETE** — the pattern-recognition engine + single-ticker analysis +
> annotated charts + a Streamlit UI, proven by **46 automated tests** (incl. a worker-crash
> durability proof) and verified end-to-end on real data + a live OpenAI call. The 5 LONG
> patterns: inverse H&S, double bottom, ascending triangle, cup-and-handle, bull flag,
> detected across daily/weekly/monthly with multi-timeframe nesting. Next: the **Alpha list**
> (auto-screening a universe).

## Architecture

```
 Temporal Server (Docker, Postgres-backed)      durable event history = source of truth
   gRPC :7233   ·   Web UI :8088
        ▲  poll task-queue "ta-default"
        │
 Python Worker (temporalio)
   Workflows = PURE orchestration (replayed, deterministic) — NO I/O
   Activities = ALL I/O (retried, idempotent) ──► SQLite domain store (data/ta.db)
                                              └──► data providers (Alpaca/FRED/yf — Phase 1)
```

Two **separate** databases: Temporal keeps its own history in **Postgres (Docker)**;
our application data lives in **SQLite** (`data/ta.db`, SQLAlchemy + Alembic, WAL mode).
Workflows never touch I/O; everything fallible/non-deterministic is an activity.

### Layout (maps to the eventual 5 layers)

```
src/ta_assistant/
  config.py            # pydantic-settings
  temporal/            # orchestration spine: client, worker, sandbox, workflows/, activities/
  db/                  # Layer 1 substrate: engine (WAL PRAGMAs), session, models
  data/                # Layer 1 providers — Alpaca/FRED/yfinance stubs (Phase 1)
  patterns/            # Layer 2 — rule-based pattern engine (Phase 1+)
  regime/              # Layer 3 — macro/regime + sector rotation (Phase 3)
  synthesis/           # Layer 4 — LLM narrative verdict (Phase 4)
  presentation/        # Layer 5 — backtest + annotated charts + alerts (Phase 4-5)
```

## Quickstart

```bash
make install            # pin Python 3.12, create venv, sync deps (incl. data/viz/ui/llm)
cp .env.example .env    # set OPENAI_API_KEY (or OPENAI_KEY) for LLM validation; optional otherwise
make temporal-up        # start Temporal (Postgres + server + UI). UI: http://localhost:8088
make migrate            # create data/ta.db + tables
make worker             # terminal A: run the durable worker
make ui                 # terminal B: Streamlit UI -> type a ticker -> see annotated analysis
```

### Analyzing a ticker

Type a symbol (e.g. `AAPL`) in the UI and the durable `AnalyzeTickerWorkflow` runs:
fetch all-time history → detect patterns on daily/weekly/monthly → render annotated charts →
OpenAI validates + narrates → persist. You get interactive Plotly charts, the annotated PNG
the LLM reviewed, and per-pattern detail (entry/breakout, neckline, target, stop, R:R,
status, confidence, nesting, and the analyst rationale). The deterministic engine runs with
**no key** (set `LLM_ENABLED=false` or omit the key); add the OpenAI key to enable validation.

## The durability proof (the headline)

**Automated** (`make integration` → `tests/integration/test_worker_crash_recovery.py`):
a real worker subprocess starts a workflow, gets **SIGKILLed mid-activity**, a fresh
worker takes over, and the workflow completes with the **same run id** (resumed, not
restarted) and an **exactly-once** side effect (the re-dispatched activity is idempotent).

**Manual** (watch it in the UI):

```bash
make temporal-up && make migrate
make worker                                  # terminal A
uv run python scripts/start_analysis.py AAPL # terminal B — starts a workflow
# While it runs, Ctrl-C terminal A to kill the worker.
# Open http://localhost:8088 — the workflow stays "Running" (history safe in Postgres).
make worker                                  # restart: it RESUMES; completed activities
                                             # are not re-run; one row lands in data/ta.db.
```

## Tests

```bash
make unit          # in-process: config, migrations, activities, workflow logic, retry, replay
make integration   # worker-crash recovery (SIGKILL → resume) + end-to-end persistence
make test          # unit + integration (no Docker needed; spins its own dev server)
make smoke         # live-stack end-to-end (needs `make temporal-up` + a worker)
make lint typecheck
```

`make help` lists every target.

## Determinism rules (enforced by the sandbox + tests + review)

- Workflows: no wall-clock (`workflow.now()`), no `random`/`uuid` (`workflow.random()`),
  no `asyncio.sleep` (`workflow.sleep`), no threads, **no I/O/DB/network**.
- All I/O lives in **activities**, which are **idempotent** via a stable dedup key
  (`workflow_id` + step — never attempt/now/random), because they can run more than once.
- Heavy libs (pandas, alpaca, mplfinance, anthropic) are imported **inside activities**,
  never at workflow-module import time, so they stay out of the sandbox.
- The committed golden history (`tests/histories/candidate_v1.json`) replays in
  `test_determinism_replay.py`; regenerate it with `make golden` after an intentional
  change to the workflow's orchestration.

## Roadmap

- **Pre-phase (done):** Temporal + SQLite skeleton, durable sample pipeline, full test gate.
- **Phase 1 (next):** the **Alpha list** — wire `data/` providers, build `patterns/`
  (swing highs/lows, trendlines, breakout/range detection), turn the
  `CandidateAnalysisWorkflow` activities into real fetch→indicators→pattern→persist, add
  `watchlist`/`patterns`/`alerts` tables, render annotated charts.
- **Phases 3-5:** regime/sector layer, LLM synthesis + diff-driven alerts, backtesting,
  and a real-time upgrade. The tiered scheduler becomes Temporal **Schedules**.

## Notes

- **Python is pinned to 3.12** (`.python-version`) for mature wheels across the
  temporalio Rust core / pandas / numpy / pydantic-core stack; the system's 3.14 is
  intentionally not used. Bumping later is a one-line change.
- **Ports** avoid the host's existing services: Temporal's Postgres is on **5433** (not
  5432), gRPC **7233**, UI **8088**.
- The fast time-skipping unit tests use a test server that runs x64-under-Rosetta on
  Apple Silicon; `conftest.py` falls back to a local dev server if it can't start, so the
  suite is not hard-blocked on Rosetta. Integration tests use the dev server directly.
- Alternative (no Docker): `brew install temporal && temporal server start-dev
  --db-filename .temporal/temporal.db --ui-port 8233`, then point `TEMPORAL_ADDRESS` at it.
```
