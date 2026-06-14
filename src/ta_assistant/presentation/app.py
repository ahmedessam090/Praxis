"""Streamlit UI. Two pages:
- Ticker Analysis: type a ticker -> run the durable AnalyzeTickerWorkflow -> view the AI
  chartist's per-timeframe thesis on a TradingView (lightweight-charts) chart.
- Market Regime: click Refresh -> run the durable MarketRegimeWorkflow -> a charted
  dashboard of classical market-conditions metrics + the LLM-integrated mood.
Run with `make ui` (needs `make temporal-up` + `make worker`).
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from ta_assistant.config import get_settings
from ta_assistant.data.bars_repo import load_bars
from ta_assistant.presentation.charts import DEFAULT_BARS, render_plotly
from ta_assistant.presentation.lwcharts import build_lwc_html, build_regime_chart_html
from ta_assistant.regime.pillars import state_label
from ta_assistant.regime.repo import latest_regime
from ta_assistant.synthesis.schema import (
    Bias,
    RegimeSnapshot,
    RegimeState,
    TickerAnalysis,
    Timeframe,
)
from ta_assistant.temporal.client import get_client
from ta_assistant.temporal.workflows.analyze_ticker import AnalyzeTickerWorkflow
from ta_assistant.temporal.workflows.market_regime import MarketRegimeWorkflow

_TF_CODE = {Timeframe.DAILY: "D", Timeframe.WEEKLY: "W", Timeframe.MONTHLY: "M"}
_DOT = {Bias.BULLISH: "🟢", Bias.NEUTRAL: "⚪", Bias.BEARISH: "🔴"}


async def _run_analysis(symbol: str) -> TickerAnalysis:
    settings = get_settings()
    client = await get_client()
    return await client.execute_workflow(
        AnalyzeTickerWorkflow.run,
        symbol,
        id=f"analyze-{symbol}-{uuid.uuid4().hex[:8]}",
        task_queue=settings.temporal_task_queue,
    )


async def _run_regime() -> RegimeSnapshot:
    settings = get_settings()
    client = await get_client()
    return await client.execute_workflow(
        MarketRegimeWorkflow.run,
        id=f"regime-{uuid.uuid4().hex[:8]}",
        task_queue=settings.temporal_task_queue,
    )


def _fmt(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "—"


def render_ticker_page() -> None:
    st.subheader("📈 AI chartist (long-side)")
    engine = st.sidebar.radio("Chart engine", ["TradingView", "Plotly"], index=0)
    symbol = st.text_input("Ticker", value="AAPL").strip().upper()
    if st.button("Analyze", type="primary") and symbol:
        with st.spinner(f"Analyzing {symbol} via the durable workflow…"):
            try:
                st.session_state["analysis"] = asyncio.run(_run_analysis(symbol))
            except Exception as exc:  # noqa: BLE001 - surface any failure in the UI
                st.error(f"Analysis failed: {exc}")
                st.info("Start the stack (`make temporal-up`) and a worker (`make worker`).")

    analysis: TickerAnalysis | None = st.session_state.get("analysis")
    if analysis is None:
        return
    summary = analysis.summary
    syn = analysis.synthesis
    st.subheader(summary.headline)
    cols = st.columns(4)
    cols[0].metric("Bias", summary.overall_bias.value)
    cols[1].metric("Last price", _fmt(summary.price_now))
    cols[2].metric(
        "Primary TF", syn.primary_timeframe.value if syn and syn.primary_timeframe else "—"
    )
    cols[3].metric("Timeframes", ", ".join(tf.value for tf in analysis.timeframes) or "—")
    if summary.narrative:
        st.info(summary.narrative)
    if syn and (syn.nested_context or syn.long_term_forming):
        if syn.nested_context:
            st.caption(f"**Across timeframes:** {syn.nested_context}")
        if syn.long_term_forming:
            st.caption(f"**Long-term:** {syn.long_term_forming}")

    if analysis.notes:
        st.markdown("#### Notes & warnings")
        render = {"warning": st.error, "caution": st.warning, "info": st.info}
        for note in analysis.notes:
            render.get(note.severity.value, st.info)(note.message)

    daily_ind = next((i for i in analysis.indicators if i.timeframe.value == "daily"), None)
    if daily_ind is not None:
        with st.expander("Indicators (daily)"):
            ic = st.columns(4)
            rsi = f"{daily_ind.rsi14:.0f}" if daily_ind.rsi14 is not None else "—"
            atrp = f"{daily_ind.atr_pct:.1f}%" if daily_ind.atr_pct is not None else "—"
            ic[0].metric("RSI(14)", rsi)
            ic[1].metric("ATR %", atrp)
            ic[2].metric(
                "% from 52w high",
                f"{daily_ind.pct_from_52w_high:+.1f}%"
                if daily_ind.pct_from_52w_high is not None
                else "—",
            )
            ic[3].metric("Trend template", "PASS" if daily_ind.trend_template_pass else "no")

    if not analysis.timeframes:
        st.warning("No timeframes had enough history to analyze.")
    tabs = st.tabs([tf.value.capitalize() for tf in analysis.timeframes])
    for tab, tf in zip(tabs, analysis.timeframes, strict=False):
        with tab:
            bars = load_bars(analysis.symbol, _TF_CODE[tf])
            thesis = analysis.thesis_for(tf)
            visible = DEFAULT_BARS.get(tf.value, 130)
            if len(bars):
                if engine == "TradingView":
                    components.html(
                        build_lwc_html(
                            bars,
                            thesis,
                            title=f"{analysis.symbol} — {tf.value}",
                            visible_bars=visible,
                        ),
                        height=680,
                        scrolling=False,
                    )
                else:
                    st.plotly_chart(
                        render_plotly(
                            bars,
                            analysis.surfaced_for(tf),
                            title=f"{analysis.symbol} — {tf.value}",
                            default_bars=visible,
                        ),
                        use_container_width=True,
                        theme=None,
                        config={"scrollZoom": True, "displaylogo": False},
                    )

            if thesis is None:
                st.info("No analysis for this timeframe.")
                continue

            tag = "▲ long" if thesis.direction == "bullish" else "▼ caution"
            fallback = " · _engine fallback_" if thesis.source != "llm" else ""
            st.markdown(
                f"**{tag} · {thesis.pattern_label}** — {thesis.status.value} · "
                f"conf {thesis.confidence:.2f}{fallback}"
            )
            lc = st.columns(4)
            lc[0].metric("Entry / breakout", _fmt(thesis.entry or thesis.breakout))
            lc[1].metric("Target", _fmt(thesis.target))
            lc[2].metric("Stop", _fmt(thesis.stop))
            lc[3].metric("R : R", _fmt(thesis.rr_ratio))
            if thesis.target2 is not None:
                st.caption(f"Second target: {thesis.target2:.2f}")
            if thesis.rationale:
                st.markdown(f"**Analyst read:** {thesis.rationale}")
            if thesis.supporting_factors:
                st.caption("🧩 Supporting (context, not the trade): "
                           + " · ".join(thesis.supporting_factors))
            if thesis.price_notes:
                st.caption("Levels: " + "  ·  ".join(n.label for n in thesis.price_notes))

            png = next((c.png_path for c in analysis.charts if c.timeframe == tf), None)
            if png and Path(png).exists():
                with st.expander("Static snapshot"):
                    st.image(png)
            if thesis.transcript:
                with st.expander("How the analyst worked (tool calls)"):
                    st.code("\n".join(thesis.transcript))


_STATE_BANNER = {
    RegimeState.CONFIRMED_UPTREND: st.success,
    RegimeState.UPTREND_UNDER_PRESSURE: st.warning,
    RegimeState.NEUTRAL: st.info,
    RegimeState.CORRECTION: st.warning,
    RegimeState.BEAR: st.error,
}


def _render_regime(snap: RegimeSnapshot) -> None:
    banner = _STATE_BANNER.get(snap.overall_state, st.info)
    banner(f"**{snap.headline}** — {snap.mood}")
    cols = st.columns(4)
    cols[0].metric("State", state_label(snap.overall_state))
    cols[1].metric("Long posture", snap.long_posture.value.upper())
    cols[2].metric("Score (−1…+1)", f"{snap.score:+.2f}")
    cols[3].metric("Mood by", "LLM" if snap.source == "llm" else "rules")
    st.caption(f"As of {snap.generated_at:%Y-%m-%d %H:%M} · classical charting, decision support")
    if snap.narrative:
        st.info(snap.narrative)

    for p in snap.pillars:
        st.markdown(f"### {_DOT.get(p.status, '⚪')} {p.name}")
        if p.summary:
            st.caption(p.summary)
        for m in p.metrics:
            detail = f" — {m.detail}" if m.detail else ""
            st.markdown(
                f"- {_DOT.get(m.status, '⚪')} **{m.label}:** {m.value}  "
                f"<span style='color:#9aa0a6;font-size:0.85em'>({m.source_tag})</span>{detail}",
                unsafe_allow_html=True,
            )
        for chart in snap.charts_for(p.key):
            components.html(build_regime_chart_html(chart), height=340, scrolling=False)


def render_regime_page() -> None:
    st.subheader("🌐 Market Regime — current conditions")
    st.caption(
        "Classical only: Dow Theory · Weinstein stage · O'Neil/Minervini supply-demand · "
        "Murphy intermarket (incl. the liquidity cycle). Decision support, not advice."
    )
    if st.button("🔄 Refresh Market Regime", type="primary"):
        with st.spinner("Reading the market via the durable workflow…"):
            try:
                st.session_state["regime"] = asyncio.run(_run_regime())
            except Exception as exc:  # noqa: BLE001 - surface any failure in the UI
                st.error(f"Regime refresh failed: {exc}")
                st.info("Start the stack (`make temporal-up`) and a worker (`make worker`).")
    snap: RegimeSnapshot | None = st.session_state.get("regime")
    if snap is None:
        snap = latest_regime()
    if snap is None:
        st.info("No regime snapshot yet — click **Refresh Market Regime** to compute one.")
        return
    _render_regime(snap)


st.set_page_config(page_title="TA Assistant", layout="wide")
st.title("TA Assistant")
st.caption("Long-side classical technical analysis. Decision support, not financial advice.")

_PAGE = st.sidebar.radio("Page", ["📈 Ticker Analysis", "🌐 Market Regime"], index=0)
if _PAGE.endswith("Market Regime"):
    render_regime_page()
else:
    render_ticker_page()
