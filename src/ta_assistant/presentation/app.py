"""Streamlit UI: type a ticker -> run the durable AnalyzeTickerWorkflow -> view the
annotated charts (interactive Plotly + the LLM-validated PNG) and the detailed
per-pattern breakdown. Run with `make ui` (needs `make temporal-up` + `make worker`).
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import streamlit as st

from ta_assistant.config import get_settings
from ta_assistant.data.bars_repo import load_bars
from ta_assistant.presentation.charts import DEFAULT_BARS, render_plotly
from ta_assistant.synthesis.schema import DetectedPattern, TickerAnalysis, Timeframe
from ta_assistant.temporal.client import get_client
from ta_assistant.temporal.workflows.analyze_ticker import AnalyzeTickerWorkflow

_TF_CODE = {Timeframe.DAILY: "D", Timeframe.WEEKLY: "W", Timeframe.MONTHLY: "M"}


async def _run_analysis(symbol: str) -> TickerAnalysis:
    settings = get_settings()
    client = await get_client()
    return await client.execute_workflow(
        AnalyzeTickerWorkflow.run,
        symbol,
        id=f"analyze-{symbol}-{uuid.uuid4().hex[:8]}",
        task_queue=settings.temporal_task_queue,
    )


def _fmt(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "—"


_ROLE_TAG = {"primary": "🎯 Primary", "secondary": "↳ Secondary", "cap": "⚠️ Bearish cap"}


def _pattern_header(p: DetectedPattern) -> str:
    tag = _ROLE_TAG.get(p.role, p.role)
    return f"{tag} · {p.display_label} — {p.status.value} · conf {p.confidence:.2f}"


st.set_page_config(page_title="TA Assistant", layout="wide")
st.title("📈 TA Assistant — long-side classical pattern analysis")
st.caption("Decision support, not financial advice. You place the trades.")

symbol = st.text_input("Ticker", value="AAPL").strip().upper()
if st.button("Analyze", type="primary") and symbol:
    with st.spinner(f"Analyzing {symbol} via the durable workflow…"):
        try:
            st.session_state["analysis"] = asyncio.run(_run_analysis(symbol))
        except Exception as exc:  # noqa: BLE001 - surface any failure in the UI
            st.error(f"Analysis failed: {exc}")
            st.info("Start the stack (`make temporal-up`) and a worker (`make worker`).")

analysis: TickerAnalysis | None = st.session_state.get("analysis")
if analysis is not None:
    summary = analysis.summary
    st.subheader(summary.headline)
    surfaced_total = sum(len(analysis.surfaced_for(tf)) for tf in analysis.timeframes)
    cols = st.columns(4)
    cols[0].metric("Bias", summary.overall_bias.value)
    cols[1].metric("Last price", _fmt(summary.price_now))
    cols[2].metric("Surfaced", f"{surfaced_total} of {len(analysis.patterns)} found")
    cols[3].metric("Timeframes", ", ".join(tf.value for tf in analysis.timeframes) or "—")
    if summary.narrative:
        st.info(summary.narrative)

    # Notes & warnings (color-coded by severity)
    if analysis.notes:
        st.markdown("#### Notes & warnings")
        render = {"warning": st.error, "caution": st.warning, "info": st.info}
        for note in analysis.notes:
            render.get(note.severity.value, st.info)(note.message)

    # Daily indicator snapshot
    daily_ind = next((i for i in analysis.indicators if i.timeframe.value == "daily"), None)
    if daily_ind is not None:
        with st.expander("Indicators (daily)"):
            ic = st.columns(4)
            ic[0].metric(
                "RSI(14)", f"{daily_ind.rsi14:.0f}" if daily_ind.rsi14 is not None else "—"
            )
            ic[1].metric(
                "ATR %", f"{daily_ind.atr_pct:.1f}%" if daily_ind.atr_pct is not None else "—"
            )
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
            surfaced = analysis.surfaced_for(tf)
            considered = analysis.considered_for(tf)
            if len(bars):
                st.plotly_chart(
                    render_plotly(
                        bars,
                        surfaced,
                        title=f"{analysis.symbol} — {tf.value}",
                        default_bars=DEFAULT_BARS.get(tf.value, 130),
                    ),
                    use_container_width=True,
                    theme=None,
                    config={
                        "scrollZoom": True,
                        "displaylogo": False,
                        "modeBarButtonsToRemove": ["lasso2d", "select2d"],
                    },
                )

            if not surfaced:
                st.info("No clean, currently-actionable structure on this timeframe.")
            for p in surfaced:
                with st.expander(_pattern_header(p), expanded=(p.role == "primary")):
                    if p.caution:
                        st.warning(p.caution)
                    lc = st.columns(4)
                    lc[0].metric("Entry / breakout", _fmt(p.entry))
                    lc[1].metric("Target", _fmt(p.target))
                    lc[2].metric("Stop", _fmt(p.stop))
                    lc[3].metric("R : R", _fmt(p.rr_ratio))
                    if p.chart_png and Path(p.chart_png).exists():
                        st.image(p.chart_png, caption=f"{p.display_label} — {tf.value}")
                    if p.llm_rationale:
                        st.markdown(f"**Analyst read:** {p.llm_rationale}")
                    if p.label_override and p.label_override != p.pattern_type:
                        st.caption(f"Engine geometry: `{p.pattern_type}` · exact levels below")
                    if p.parent_id:
                        st.caption(f"Nested inside `{p.parent_id}` (larger-timeframe structure)")
                    st.json(p.levels)

            if considered:
                with st.expander(f"Also considered ({len(considered)}) — not surfaced"):
                    for p in considered:
                        arrow = "▲" if p.direction == "bullish" else "▼"
                        st.caption(
                            f"{arrow} {p.pattern_type} · {p.status.value} · "
                            f"conf {p.confidence:.2f} · breakout {_fmt(p.entry)}"
                        )
