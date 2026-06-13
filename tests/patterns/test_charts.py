"""Chart rendering: mplfinance writes a PNG; Plotly returns a populated figure."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from synth import double_bottom_df

from ta_assistant.patterns.assemble import to_detected_pattern
from ta_assistant.patterns.context import build_context
from ta_assistant.patterns.detectors import detect_all
from ta_assistant.presentation.charts import render_mpl, render_plotly
from ta_assistant.synthesis.schema import DetectedPattern


def _patterns(df: pd.DataFrame) -> list[DetectedPattern]:
    cands = detect_all(build_context(df, "daily"))
    return [to_detected_pattern(c, f"p{i}", df.index) for i, c in enumerate(cands)]


def test_render_mpl_writes_png(tmp_path: Path) -> None:
    df = double_bottom_df()
    out = tmp_path / "chart.png"
    render_mpl(df, _patterns(df), str(out), title="TEST daily")
    assert out.exists()
    assert out.stat().st_size > 5000  # a real rendered image


def test_render_plotly_has_traces() -> None:
    df = double_bottom_df()
    fig = render_plotly(df, _patterns(df), title="TEST")
    assert len(fig.data) >= 2  # candlestick + volume (+ pivots)
