# Praxis — Classical Technical Analysis, Made Reproducible

A **personal, local-only** decision-support tool for **long-side** swing trading built on
**classical technical analysis** — chart patterns, trendlines, stage analysis and market
breadth. It reads the market regime, screens a universe for structurally sound setups, and
argues a reasoned case over an annotated chart. **It never places a trade.**

Not short selling, not day trading, not fundamentals, not auto-execution.

> ⚠️ **Not financial advice.** This is a personal research and educational tool that
> outputs the author's own charting heuristics. Nothing it produces is investment advice,
> a recommendation, or a solicitation to buy or sell anything, and none of it is tailored
> to your circumstances. Labels such as "ALPHA", "In range" and the entry/stop/target
> levels are mechanical descriptions of chart geometry, not guidance. Technical analysis
> does not predict prices, past performance says nothing about future results, and you can
> lose money — including more than you expect. Do your own research and consider taking
> advice from someone authorised by the FCA. The software is provided **"as is", without
> warranty of any kind**; see [Legal](#legal) and [LICENSE](LICENSE). You alone are
> responsible for every trade you place.

## What it does

Three surfaces, each backed by a durable workflow:

**1. Market Regime** — the top-down read, before any individual stock. Six book-grounded
pillars scored from computed metrics: Primary Trend (Dow Theory + Weinstein stage),
Institutional Supply/Demand (distribution days, follow-through day, Power Trend), Market
Breadth, Intermarket & Commodities (including the dollar and a liquidity-cycle read), Sector
& Industry Leadership, and Volatility. Produces a regime state and a characterisation of how
hospitable the tape has been to breakouts.

**2. Screener → ALPHA list** — bottom-up candidate discovery. Build named groups by hand,
sweep the rallying sectors with a deterministic pre-screen (trend template, relative strength
vs SPY), or describe what you want and let the model propose tickers. Promising candidates go
through full multi-timeframe analysis and an **ALPHA verdict**: a conviction score, the
measured levels, and a per-factor breakdown of why it qualified. Names that lose conviction
on refresh drop to a **Downgraded** list with the reason.

**3. Ticker Analysis** — the deep read on one symbol across daily, weekly and monthly, with
the detected structure drawn on an interactive candlestick chart: rails, necklines, curves,
labelled pivots, and every level annotated.

## How detection works

Detection is **hybrid**, and the split is deliberate:

- **Deterministic code (numpy/scipy)** finds the swing pivots, fits the trendlines, and
  computes the *exact* levels — neckline, breakout pivot, measured-move target, stop, prior
  resistance, trigger range. **18 pattern detectors** cover the classical vocabulary:
  triangles (ascending, descending, symmetrical), channels, wedges, flags, rectangles,
  cup-and-handle, head-and-shoulders (and inverse), double/triple bottoms and tops, and
  rounding bottoms. Bearish structures are detected too — not to trade short, but to surface
  a **cap** that threatens a long thesis.
- **An LLM chartist** then works the chart like a human would, through a **tool loop**: list
  pivots, fit a rail through the pivots *it* chooses, check breakout volume, classify status,
  and only then submit a thesis. It can confirm, refine or override the engine's candidates,
  but it can never invent a level — every number must come back from a tool.
- **A pattern judge** vets each surfaced setup independently, rejecting mislabelled geometry
  (an "ascending triangle" whose rails aren't real, a tilted-neckline "H&S"), with a
  deterministic floor that still works when no LLM key is present.

The result: exact, reproducible levels plus argued judgment — and a deterministic path that
runs with **no API key at all** (`LLM_ENABLED=false`).

Setup states are deliberately **descriptive rather than directive** — `awaiting_break`,
`in_range`, `extended`, `not_yet`, `played_out`, `invalid` — because they describe where price
sits relative to a measured pivot, not what anyone should do about it.

## Architecture

```
 Next.js 15 + React 19 (:3000)            Temporal Server (Docker, Postgres :5433)
   Regime · Screener · Ticker                gRPC :7233   ·   Web UI :8088
        │  fetch                                   ▲  poll task-queue "ta-default"
        ▼                                          │
 FastAPI (127.0.0.1:8000) ──starts workflows──► Python Worker (temporalio)
   serves JSON, triggers runs                Workflows = PURE orchestration (replayed) — NO I/O
                                             Activities = ALL I/O (retried, idempotent)
                                                     ├──► SQLite domain store (data/ta.db)
                                                     └──► yfinance / Stooq
```

Two **separate** databases: Temporal keeps its own event history in **Postgres** (Docker);
application data lives in **SQLite** (`data/ta.db`, SQLAlchemy + Alembic, WAL mode).
Workflows never touch I/O; everything fallible or non-deterministic is an activity, so a
crashed worker resumes instead of restarting.

Seven workflows: `AnalyzeTickerWorkflow`, `ScannerWorkflow`, `AlphaCandidateWorkflow`,
`AlphaRefreshWorkflow`, `MarketRegimeWorkflow`, `CandidateAnalysisWorkflow`, and a
`CrashDemoWorkflow` used by the durability test.

### Layout

```
src/ta_assistant/          # the Python package (the repo is named Praxis; the module is not)
  config.py                # pydantic-settings
  temporal/                # orchestration spine: client, worker, sandbox, workflows/, activities/
  db/                      # engine (WAL PRAGMAs), session, models
  data/                    # providers: yfinance (primary), Stooq (fallback), earnings
  patterns/                # geometry engine: pivots, trendlines, 18 detectors, consensus, action_state
  analyst/                 # LLM chartist: prompts, tool loop, pattern judge, cache, observability
  screener/                # universe, deterministic pre-screen, ALPHA gate, groups, repo
  regime/                  # the six pillars, metrics, sectors, breadth
  synthesis/               # the output contract (pydantic) + vision consensus validator
  presentation/            # chart rendering (Lightweight Charts, Plotly, mplfinance)
  api/                     # FastAPI routers: analysis, screener, regime, llm, health
web/                       # Next.js app (App Router, Tailwind 4, TanStack Query)
```

## Quickstart

```bash
make install            # pin Python 3.12, create venv, sync all dependency groups
cp .env.example .env    # optional: add OPENAI_API_KEY for the LLM chartist
make temporal-up        # start Temporal (Postgres + server + UI at :8088)
make migrate            # create data/ta.db + tables
make dev                # worker + FastAPI + Next.js together — open http://localhost:3000
```

`make dev` runs all three processes; Ctrl-C stops them. To run them separately use `make
worker`, `make api` and `make web` in three terminals. `make help` lists every target.

The deterministic engine needs **no API key**. Add `OPENAI_API_KEY` to enable the LLM
chartist, the ALPHA judge and the narratives; set `LLM_ENABLED=false` to force the
deterministic path. `make langfuse-up` starts a self-hosted [Langfuse](https://langfuse.com)
at :3001 for LLM cost and trace visibility.

> The Streamlit UI (`make ui`) is the original frontend, kept working but superseded by the
> Next.js app.

## The durability proof

Every analysis is a Temporal workflow, which is what makes a long multi-step LLM pipeline
survivable. This is tested, not asserted:

**Automated** (`make integration` → `tests/integration/test_worker_crash_recovery.py`): a
real worker subprocess starts a workflow, gets **SIGKILLed mid-activity**, a fresh worker
takes over, and the workflow completes with the **same run id** — resumed, not restarted —
with an **exactly-once** side effect, because the re-dispatched activity is idempotent.

**Manual** (watch it happen):

```bash
make temporal-up && make migrate
make worker                                  # terminal A
uv run python scripts/start_analysis.py AAPL # terminal B — starts a workflow
# While it runs, Ctrl-C terminal A to kill the worker.
# Open http://localhost:8088 — the workflow stays "Running" (history is safe in Postgres).
make worker                                  # restart: it RESUMES; completed activities
                                             # are not re-run; one row lands in data/ta.db.
```

## Tests

**276 tests**, no Docker required — the suite spins up its own Temporal test server.

```bash
make unit          # config, migrations, activities, workflow logic, retry, replay, geometry
make integration   # worker-crash recovery (SIGKILL → resume) + end-to-end persistence
make test          # unit + integration
make smoke         # live-stack end-to-end (needs `make temporal-up` + a worker)
make lint typecheck
```

`typecheck` is **mypy strict** across the package.

## Determinism rules (enforced by the sandbox, the tests, and review)

- Workflows: no wall-clock (`workflow.now()`), no `random`/`uuid` (`workflow.random()`), no
  `asyncio.sleep` (`workflow.sleep`), no threads, **no I/O, DB or network**.
- All I/O lives in **activities**, which are **idempotent** via a stable dedup key
  (`workflow_id` + step — never attempt, now, or random), because they can run more than once.
- Heavy libs (pandas, mplfinance, openai, anthropic) are imported **inside activities**, never
  at workflow-module import time, so they stay out of the sandbox.
- The committed golden history (`tests/histories/candidate_v1.json`) replays in
  `test_determinism_replay.py`; regenerate it with `make golden` after an intentional change
  to a workflow's orchestration.

## Tuning it

The ALPHA rubric lives in **plain English** in
[`src/ta_assistant/analyst/alpha_rules.md`](src/ta_assistant/analyst/alpha_rules.md). Edit
it and the next run picks it up — the file is hashed into the verdict cache key, so cached
verdicts recompute on their own with no code change and no version bump. A deterministic
gate in `screener/alpha.py` mirrors the rubric's spirit for the no-LLM path.

## Notes

- **Python is pinned to 3.12** (`.python-version`) for mature wheels across the temporalio
  Rust core / pandas / numpy / pydantic-core stack.
- **Ports** avoid clashing with common local services: Temporal's Postgres on **5433**, gRPC
  **7233**, Temporal UI **8088**, FastAPI **8000**, Next.js **3000**, Langfuse **3001**.
- The API binds to **127.0.0.1** with CORS limited to localhost. It is not built to be
  exposed; there is no auth.
- The fast time-skipping unit tests use a test server that runs x64-under-Rosetta on Apple
  Silicon; `conftest.py` falls back to a local dev server if it can't start, so the suite is
  not hard-blocked on Rosetta.
- Alternative to Docker: `brew install temporal && temporal server start-dev --db-filename
  .temporal/temporal.db --ui-port 8233`, then point `TEMPORAL_ADDRESS` at it.

## Data sources

Price history comes from **Yahoo Finance** (via [yfinance](https://github.com/ranaroussi/yfinance),
no key) with **[Stooq](https://stooq.com)** as the fallback when Yahoo rate-limits or returns
nothing. Both are fetched **at runtime**; no vendor market data is committed to this repo, and
the local SQLite cache (`data/ta.db`) is gitignored.

Your use of those sources is governed by their terms, not by this project's licence. Yahoo's
terms contemplate personal, non-commercial use and restrict redistribution of their data, so
treat anything the tool caches as yours to look at and not yours to republish. If you need
data you can rely on or redistribute, buy a licensed feed — the `data/` providers sit behind a
small interface precisely so you can swap one in.

The screener's ~186-ticker universe (`src/ta_assistant/screener/universe.py`) and the ~45-name
breadth basket (`src/ta_assistant/regime/universe.py`) are **hand-curated lists of liquid US
large/mid caps**, not the constituent list of any index. Index membership data is the licensed
property of its publisher; don't paste one in.

## Legal

**Not financial advice.** Read the disclaimer at the top of this file. In short: this is a
personal, local-only research tool. It does not place trades — there is no broker integration
and no order-placement code path — and it does not send signals to anyone. It runs on your
machine, against your API keys, under a rubric you can edit
(`src/ta_assistant/analyst/alpha_rules.md`). Every output is a description of chart geometry
for you to accept or reject; every decision and every order is yours.

If you fork this and turn it into something that advises other people — a hosted version, a
paid tier, a public signal feed, a subscription list — that is a materially different activity
from publishing source code, and in the UK it may fall inside the FCA's perimeter (see the
FCA's [PERG 8.30](https://www.handbook.fca.org.uk/handbook/PERG/8/30.html) on software that
generates buy/sell signals, and [PERG 2.3](https://www.handbook.fca.org.uk/handbook/PERG/2/3.html)
on the business test). Take your own advice before you do that.

**No warranty.** Licensed under Apache-2.0, which provides this software on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, and excludes liability for damages arising from
its use. See [LICENSE](LICENSE) sections 7 and 8.

**Not affiliated.** This project references the work of Mark Minervini, Peter Brandt, Stan
Weinstein, William O'Neil, John Murphy and others **descriptively**, to credit the school of
classical technical analysis each rule comes from. The implementations are the author's own
reading of publicly discussed ideas; no text from any book or paid course is reproduced here.
Those names may be trade marks of their respective owners. This project is independent and is
**not affiliated with, sponsored by, endorsed by, or connected to** any of them, nor with
TradingView, Yahoo, Stooq, or any data or brokerage provider.

## Licence

[Apache License 2.0](LICENSE) — © 2026 ahmedcoder01.

Third-party attributions, including the vendored TradingView Lightweight Charts build, are
recorded in [NOTICE](NOTICE).
