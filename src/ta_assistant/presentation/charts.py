"""Annotated candlestick rendering. Two backends share the same patterns:
mplfinance -> static PNG (user view + OpenAI vision input); Plotly -> interactive.

Annotations are positioned by TIMESTAMP (mapped to the plotted window), so the
renderer is independent of whatever bar window detection used.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from ta_assistant.synthesis.schema import DetectedPattern

_LEVEL_STYLE = {
    "breakout": ("#1565C0", "dash"),
    "target": ("#2E7D32", "dot"),
    "stop": ("#C62828", "dash"),
}


def render_mpl(
    bars: pd.DataFrame,
    patterns: Sequence[DetectedPattern],
    out_path: str,
    title: str = "",
    max_bars: int = 520,
) -> str:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import mplfinance as mpf

    window = bars.iloc[-max_bars:] if len(bars) > max_bars else bars
    plot_df = window.rename(
        columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
    )[["Open", "High", "Low", "Close", "Volume"]]
    plot_df.index = pd.DatetimeIndex(plot_df.index)
    width = len(plot_df)

    def pos(ts: object) -> int:
        loc = plot_df.index.get_indexer([pd.Timestamp(ts)], method="nearest")
        return int(loc[0]) if len(loc) else 0

    hlines: list[float] = []
    hcolors: list[str] = []
    for p in patterns:
        for key, (color, _dash) in _LEVEL_STYLE.items():
            value = p.levels.get(key)
            if value is not None:
                hlines.append(value)
                hcolors.append(color)

    plot_kwargs: dict[str, object] = {
        "type": "candle",
        "volume": True,
        "style": "yahoo",
        "returnfig": True,
        "figsize": (14, 8),
        "title": title,
        "warn_too_much_data": 10_000_000,
    }
    if hlines:
        plot_kwargs["hlines"] = {
            "hlines": hlines,
            "colors": hcolors,
            "linestyle": "--",
            "linewidths": 1.0,
        }
    fig, axlist = mpf.plot(plot_df, **plot_kwargs)
    ax = axlist[0]
    for p in patterns:
        start, end = pos(p.region_start), pos(p.region_end)
        ax.axvspan(min(start, end), max(start, end), color="#90A4AE", alpha=0.10)
        bo, tg = p.levels.get("breakout"), p.levels.get("target")
        if bo is not None and tg is not None:
            ax.axhspan(min(bo, tg), max(bo, tg), color="#2E7D32", alpha=0.05)
        for piv in p.pivots:
            x = pos(piv.ts)
            if 0 <= x < width:
                ax.scatter(
                    [x],
                    [piv.price],
                    marker="v" if piv.kind == "H" else "^",
                    s=80,
                    color="#37474F",
                    zorder=5,
                )
        highs = [pv for pv in p.pivots if pv.kind == "H"]
        if p.pattern_type == "head_and_shoulders_bottom" and len(highs) >= 2:
            ax.plot(
                [pos(highs[0].ts), pos(highs[-1].ts)],
                [highs[0].price, highs[-1].price],
                color="#6A1B9A",
                linewidth=1.5,
            )

    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return out_path


def render_plotly(bars: pd.DataFrame, patterns: Sequence[DetectedPattern], title: str = ""):  # type: ignore[no-untyped-def]
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, row_heights=[0.78, 0.22], vertical_spacing=0.03
    )
    fig.add_trace(
        go.Candlestick(
            x=bars.index,
            open=bars["open"],
            high=bars["high"],
            low=bars["low"],
            close=bars["close"],
            name="price",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Bar(x=bars.index, y=bars["volume"], name="volume", marker_color="#90A4AE"),
        row=2,
        col=1,
    )
    for p in patterns:
        for key, (color, dash) in _LEVEL_STYLE.items():
            value = p.levels.get(key)
            if value is not None:
                fig.add_hline(
                    y=value,
                    line={"color": color, "dash": dash, "width": 1},
                    annotation_text=f"{p.pattern_type} {key} {value:.2f}",
                    row=1,
                    col=1,
                )
        fig.add_vrect(
            x0=p.region_start,
            x1=p.region_end,
            fillcolor="#90A4AE",
            opacity=0.08,
            line_width=0,
            row=1,
            col=1,
        )
        if p.pivots:
            fig.add_trace(
                go.Scatter(
                    x=[pv.ts for pv in p.pivots],
                    y=[pv.price for pv in p.pivots],
                    mode="markers",
                    marker={"size": 9, "color": "#37474F"},
                    name=p.pattern_type,
                ),
                row=1,
                col=1,
            )
    fig.update_layout(title=title, xaxis_rangeslider_visible=False, height=700, showlegend=False)
    return fig
