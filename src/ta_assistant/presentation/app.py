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
from ta_assistant.presentation.charts import render_plotly
from ta_assistant.synthesis.schema import TickerAnalysis, Timeframe
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
    cols = st.columns(4)
    cols[0].metric("Bias", summary.overall_bias.value)
    cols[1].metric("Last price", _fmt(summary.price_now))
    cols[2].metric("Patterns", str(len(analysis.patterns)))
    cols[3].metric("Timeframes", ", ".join(tf.value for tf in analysis.timeframes) or "—")
    if summary.narrative:
        st.write(summary.narrative)

    if not analysis.timeframes:
        st.warning("No timeframes had enough history to analyze.")
    tabs = st.tabs([tf.value.capitalize() for tf in analysis.timeframes])
    for tab, tf in zip(tabs, analysis.timeframes, strict=False):
        with tab:
            bars = load_bars(analysis.symbol, _TF_CODE[tf])
            patterns = analysis.patterns_for(tf)
            if len(bars):
                st.plotly_chart(
                    render_plotly(bars, patterns, title=f"{analysis.symbol} — {tf.value}"),
                    use_container_width=True,
                )
            png = next((c.png_path for c in analysis.charts if c.timeframe == tf), None)
            if png and Path(png).exists():
                st.image(png, caption="Annotated view (sent to the LLM validator)")

            if not patterns:
                st.info("No patterns detected on this timeframe.")
            for p in patterns:
                header = f"{p.pattern_type} — {p.status.value} · confidence {p.confidence:.2f}"
                with st.expander(header):
                    lc = st.columns(4)
                    lc[0].metric("Entry / breakout", _fmt(p.entry))
                    lc[1].metric("Target", _fmt(p.target))
                    lc[2].metric("Stop", _fmt(p.stop))
                    lc[3].metric("R : R", _fmt(p.rr_ratio))
                    if p.parent_id:
                        st.caption(
                            f"Nested inside pattern `{p.parent_id}` (larger-timeframe structure)"
                        )
                    st.json(p.levels)
                    if p.llm_rationale:
                        st.markdown(f"**Analyst rationale:** {p.llm_rationale}")
