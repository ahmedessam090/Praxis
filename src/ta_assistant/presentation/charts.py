"""Annotated candlestick rendering — light, TradingView-style.

Interactive: tuned Plotly (white theme, MA overlays, volume + RSI panes, recent default
zoom, y-autoscale from the candles so a degenerate level can neither smear labels nor wreck
the scale, pattern geometry as real diagonal SEGMENTS, an H&S arc, labelled pivots, and
TradingView-style colored level pills at the right edge).

Static: mplfinance PNGs — a per-timeframe overview, a clean image for the vision analyst
(no geometry), and a focused per-pattern image zoomed to one structure.

All annotations are positioned by TIMESTAMP, so the renderer is independent of the bar
window used during detection.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import pandas as pd

from ta_assistant.synthesis.schema import (
    DetectedPattern,
    PriceNote,
    Shape,
    ShapeKind,
    TimeframeThesis,
)

# mplfinance's classic title/labels request font weights (medium/semibold) that the bundled
# fonts lack — the fallback is fine, but it spams the worker log. Quiet just that logger.
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)

# Light TradingView palette
_BG = "#ffffff"
_GRID = "#e1e3ea"
_TEXT = "#131722"
_AXIS = "#787b86"
_UP = "#089981"
_DOWN = "#f23645"
_MA = [(50, "#2962ff"), (150, "#ff9800"), (200, "#9c27b0")]
# level name -> (color, plotly dash)
_LEVELS = {
    "breakout": ("#2962ff", "dot"),
    "target": ("#089981", "dash"),
    "stop": ("#f23645", "dash"),
}
# pattern geometry color by role
_ROLE_COLOR = {"primary": "#2962ff", "secondary": "#7e57c2", "cap": "#f23645"}
DEFAULT_BARS = {"daily": 130, "weekly": 110, "monthly": 60}


def _pivot_labels(p: DetectedPattern) -> list[str]:
    t, n = p.pattern_type, len(p.pivots)
    if "head_and_shoulders" in t and n == 5:
        return ["LS", "", "Head", "", "RS"]
    if "double" in t and n == 3:
        return ["1", "neck", "2"]
    if "triple" in t and n >= 5:
        return (["1", "", "2", "", "3"] + [""] * n)[:n]
    if "cup" in t and n == 3:
        return ["rim", "cup", "rim"]
    return [""] * n


def _select(patterns: Sequence[DetectedPattern], k: int = 3) -> list[DetectedPattern]:
    """Draw geometry for the consensus-surfaced structures (primary/secondary/cap). Falls
    back to the top-k by confidence if roles were never assigned (defensive)."""
    surfaced = [p for p in patterns if p.role in ("primary", "secondary", "cap")]
    if surfaced:
        order = {"primary": 0, "secondary": 1, "cap": 2}
        return sorted(surfaced, key=lambda p: order.get(p.role, 9))
    return sorted(patterns, key=lambda p: p.confidence, reverse=True)[:k]


def render_plotly(
    bars: pd.DataFrame,
    patterns: Sequence[DetectedPattern],
    title: str = "",
    *,
    default_bars: int | None = None,
    show_rsi: bool = True,
) -> Any:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    from ta_assistant.patterns.indicators import rsi as rsi_fn

    rows = 3 if show_rsi else 2
    heights = [0.62, 0.18, 0.20] if show_rsi else [0.78, 0.22]
    fig = make_subplots(
        rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.02, row_heights=heights
    )

    fig.add_trace(
        go.Candlestick(
            x=bars.index,
            open=bars["open"],
            high=bars["high"],
            low=bars["low"],
            close=bars["close"],
            name="price",
            increasing_line_color=_UP,
            decreasing_line_color=_DOWN,
            increasing_fillcolor=_UP,
            decreasing_fillcolor=_DOWN,
            line={"width": 1},
        ),
        row=1,
        col=1,
    )
    for length, color in _MA:
        if len(bars) >= length:
            ma = bars["close"].rolling(length, min_periods=length).mean()
            fig.add_trace(
                go.Scatter(
                    x=bars.index,
                    y=ma,
                    mode="lines",
                    name=f"MA{length}",
                    line={"color": color, "width": 1.1},
                ),
                row=1,
                col=1,
            )

    up = bars["close"].to_numpy() >= bars["open"].to_numpy()
    fig.add_trace(
        go.Bar(
            x=bars.index,
            y=bars["volume"],
            name="vol",
            marker_line_width=0,
            opacity=0.5,
            marker_color=[_UP if u else _DOWN for u in up],
        ),
        row=2,
        col=1,
    )
    if show_rsi:
        fig.add_trace(
            go.Scatter(
                x=bars.index,
                y=rsi_fn(bars["close"]),
                mode="lines",
                name="RSI",
                line={"color": "#5d606b", "width": 1},
            ),
            row=3,
            col=1,
        )
        for lvl in (30, 70):
            fig.add_hline(y=lvl, line={"color": "#b2b5be", "width": 1, "dash": "dot"}, row=3, col=1)
        fig.update_yaxes(range=[0, 100], row=3, col=1)

    # default window + y-range from the VISIBLE candles (+ only nearby levels)
    n = len(bars)
    width = default_bars or 130
    win = bars.iloc[max(0, n - width) :]
    draw = _select(patterns)
    lo, hi = float(win["low"].min()), float(win["high"].max())
    for p in draw:
        for key in ("breakout", "target", "stop"):
            v = p.levels.get(key)
            if v is not None and lo * 0.85 <= v <= hi * 1.15:
                lo, hi = min(lo, v), max(hi, v)
    pad = (hi - lo) * 0.06 or 1.0
    y_range = [lo - pad, hi + pad]
    last_x = bars.index[-1]
    last_close = float(bars["close"].to_numpy(dtype=float)[-1])

    def y_at(p: DetectedPattern, idx: int) -> float:
        return p.levels["neckline_slope"] * idx + p.levels["neckline_intercept"]

    for p in draw:
        pat_color = _ROLE_COLOR.get(p.role, "#7e57c2")
        # diagonal neckline / trendline segment
        if "neckline_slope" in p.levels and "neckline_intercept" in p.levels:
            fig.add_shape(
                type="line",
                row=1,
                col=1,
                x0=p.region_start,
                x1=p.region_end,
                y0=y_at(p, p.region_start_idx),
                y1=y_at(p, p.region_end_idx),
                line={"color": pat_color, "width": 1.8, "dash": "solid"},
            )
        # H&S arc through the three extreme pivots (smooth spline)
        if "head_and_shoulders" in p.pattern_type and len(p.pivots) == 5:
            arc = [p.pivots[0], p.pivots[2], p.pivots[4]]
            fig.add_trace(
                go.Scatter(
                    x=[pv.ts for pv in arc],
                    y=[pv.price for pv in arc],
                    mode="lines",
                    line={"color": pat_color, "width": 1.6, "shape": "spline"},
                    showlegend=False,
                    hoverinfo="skip",
                ),
                row=1,
                col=1,
            )
        # rising support / channel rail through the swing lows
        lows = [pv for pv in p.pivots if pv.kind == "L"]
        if p.pattern_type in ("ascending_triangle", "ascending_channel") and len(lows) >= 2:
            fig.add_shape(
                type="line",
                row=1,
                col=1,
                x0=lows[0].ts,
                y0=lows[0].price,
                x1=lows[-1].ts,
                y1=lows[-1].price,
                line={"color": pat_color, "width": 1.5},
            )
        # measured-move target box
        bo, tg = p.levels.get("breakout"), p.levels.get("target")
        if bo is not None and tg is not None and p.role != "cap":
            fig.add_shape(
                type="rect",
                row=1,
                col=1,
                x0=p.region_end,
                x1=last_x,
                y0=min(bo, tg),
                y1=max(bo, tg),
                fillcolor="rgba(8,153,129,0.07)",
                line_width=0,
                layer="below",
            )
        # pivot markers + role-aware labels
        fig.add_trace(
            go.Scatter(
                x=[pv.ts for pv in p.pivots],
                y=[pv.price for pv in p.pivots],
                mode="markers+text",
                marker={
                    "size": 7,
                    "color": pat_color,
                    "line": {"width": 1, "color": _BG},
                    "symbol": [
                        "triangle-down" if pv.kind == "H" else "triangle-up" for pv in p.pivots
                    ],
                },
                text=_pivot_labels(p),
                textposition=[
                    "top center" if pv.kind == "H" else "bottom center" for pv in p.pivots
                ],
                textfont={"size": 9, "color": _TEXT},
                showlegend=False,
                hoverinfo="skip",
            ),
            row=1,
            col=1,
        )
        # horizontal levels: short line + filled right-edge pill, skip if out of band
        for key, (color, dash) in _LEVELS.items():
            v = p.levels.get(key)
            if v is None or not (y_range[0] <= v <= y_range[1]):
                continue
            fig.add_shape(
                type="line",
                row=1,
                col=1,
                x0=p.region_end,
                x1=last_x,
                y0=v,
                y1=v,
                line={"color": color, "width": 1, "dash": dash},
            )
            fig.add_annotation(
                x=1.0,
                xref="paper",
                y=v,
                yref="y",
                text=f"{v:.2f}",
                showarrow=False,
                xanchor="left",
                font={"size": 10, "color": "#ffffff"},
                bgcolor=color,
                borderpad=3,
            )

    # current price marker
    fig.add_hline(
        y=last_close, line={"color": _AXIS, "width": 1, "dash": "dot"}, row=1, col=1
    )
    fig.add_annotation(
        x=1.0,
        xref="paper",
        y=last_close,
        yref="y",
        text=f"{last_close:.2f}",
        showarrow=False,
        xanchor="left",
        font={"size": 10, "color": "#ffffff"},
        bgcolor=_AXIS,
        borderpad=3,
    )

    fig.update_layout(
        title={"text": title, "font": {"color": _TEXT}},
        template="plotly_white",
        paper_bgcolor=_BG,
        plot_bgcolor=_BG,
        font={"color": _TEXT},
        height=760,
        margin={"l": 8, "r": 78, "t": 40, "b": 8},
        hovermode="x unified",
        dragmode="pan",
        bargap=0.0,
        xaxis_rangeslider_visible=False,
        legend={"orientation": "h", "y": 1.02, "x": 0, "bgcolor": "rgba(0,0,0,0)"},
    )
    fig.update_xaxes(
        range=[win.index[0], last_x],
        gridcolor=_GRID,
        showspikes=True,
        spikemode="across",
        spikecolor=_AXIS,
        spikethickness=1,
    )
    fig.update_yaxes(range=y_range, gridcolor=_GRID, row=1, col=1, side="right")
    fig.update_yaxes(gridcolor=_GRID, row=2, col=1)
    return fig


# --------------------------- static (mplfinance) -----------------------------


def _mpf_style() -> Any:
    import mplfinance as mpf

    mc = mpf.make_marketcolors(
        up=_UP, down=_DOWN, edge="inherit", wick="inherit", volume="in"
    )
    return mpf.make_mpf_style(
        base_mpf_style="classic",
        marketcolors=mc,
        facecolor=_BG,
        edgecolor="#cccccc",
        figcolor=_BG,
        gridcolor=_GRID,
        gridstyle="-",
        rc={
            "axes.labelcolor": _TEXT,
            "axes.edgecolor": "#cccccc",
            "xtick.color": _AXIS,
            "ytick.color": _AXIS,
            "text.color": _TEXT,
        },
    )


def _draw_geometry(ax: Any, plot_df: pd.DataFrame, patterns: Sequence[DetectedPattern]) -> None:
    """Draw each pattern's region shade, neckline/support segments, H&S arc and pivots."""
    width = len(plot_df)

    def pos(ts: object) -> int:
        loc = plot_df.index.get_indexer([pd.Timestamp(ts)], method="nearest")
        return int(loc[0]) if len(loc) else 0

    for p in patterns:
        color = _ROLE_COLOR.get(p.role, "#7e57c2")
        start, end = max(0, pos(p.region_start)), min(width - 1, pos(p.region_end))
        if end >= 0 and start < width:
            ax.axvspan(start, end, color=color, alpha=0.06)
        # neckline / trendline segment
        if "neckline_slope" in p.levels and "neckline_intercept" in p.levels:
            y0 = p.levels["neckline_slope"] * p.region_start_idx + p.levels["neckline_intercept"]
            y1 = p.levels["neckline_slope"] * p.region_end_idx + p.levels["neckline_intercept"]
            ax.plot([start, end], [y0, y1], color=color, linewidth=1.6)
        # rising support rail
        lows = [pv for pv in p.pivots if pv.kind == "L"]
        if p.pattern_type in ("ascending_triangle", "ascending_channel") and len(lows) >= 2:
            ax.plot(
                [pos(lows[0].ts), pos(lows[-1].ts)],
                [lows[0].price, lows[-1].price],
                color=color,
                linewidth=1.4,
            )
        # H&S arc
        if "head_and_shoulders" in p.pattern_type and len(p.pivots) == 5:
            arc = [p.pivots[0], p.pivots[2], p.pivots[4]]
            ax.plot(
                [pos(pv.ts) for pv in arc],
                [pv.price for pv in arc],
                color=color,
                linewidth=1.5,
            )
        # pivots
        for piv in p.pivots:
            x = pos(piv.ts)
            if 0 <= x < width:
                ax.scatter(
                    [x],
                    [piv.price],
                    marker="v" if piv.kind == "H" else "^",
                    s=60,
                    color=color,
                    zorder=5,
                )


def _level_pills(ax: Any, width: int, patterns: Sequence[DetectedPattern]) -> None:
    """TradingView-style filled price pills at the right edge for each level."""
    seen: set[str] = set()
    for p in patterns:
        for key, (color, _dash) in _LEVELS.items():
            v = p.levels.get(key)
            if v is None:
                continue
            tag = f"{key}:{round(v, 2)}"
            if tag in seen:
                continue
            seen.add(tag)
            ax.axhline(v, color=color, linewidth=0.9, linestyle="--", alpha=0.7)
            ax.annotate(
                f"{v:.2f}",
                xy=(width - 1, v),
                xytext=(4, 0),
                textcoords="offset points",
                va="center",
                ha="left",
                fontsize=8,
                color="white",
                bbox={"boxstyle": "round,pad=0.25", "fc": color, "ec": color},
                zorder=6,
            )


def _apply_log_scale(ax: Any) -> None:
    """LOG price axis with plain-number tick labels — equal % moves are equal height, so
    multi-year trendlines/patterns read correctly (a $40->$280 stock is no longer distorted)."""
    from matplotlib.ticker import FuncFormatter, LogLocator

    ax.set_yscale("log")
    ax.yaxis.set_major_locator(LogLocator(base=10, subs=(1.0, 2.0, 3.0, 5.0, 7.0)))
    ax.yaxis.set_minor_locator(LogLocator(base=10, subs=(1.5, 2.5, 4.0, 6.0, 8.0, 9.0)))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.yaxis.set_minor_formatter(FuncFormatter(lambda v, _: ""))


def _plot_base(plot_df: pd.DataFrame, title: str, *, volume: bool = True) -> Any:
    import mplfinance as mpf

    addplots = []
    width = len(plot_df)
    for length, color in _MA:
        if width >= length:
            ma = plot_df["Close"].rolling(length, min_periods=length).mean()
            addplots.append(mpf.make_addplot(ma, color=color, width=0.8))
    kwargs: dict[str, object] = {
        "type": "candle",
        "volume": volume,
        "style": _mpf_style(),
        "returnfig": True,
        "figsize": (14, 8),
        "title": title,
        "warn_too_much_data": 10_000_000,
        "tight_layout": True,
    }
    if addplots:
        kwargs["addplot"] = addplots
    fig, axlist = mpf.plot(plot_df, **kwargs)
    _apply_log_scale(axlist[0])  # price pane -> logarithmic
    return fig, axlist


def _to_plot_df(bars: pd.DataFrame) -> pd.DataFrame:
    df = bars.rename(
        columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
    )[["Open", "High", "Low", "Close", "Volume"]]
    df.index = pd.DatetimeIndex(df.index)
    return df


def render_mpl(
    bars: pd.DataFrame,
    patterns: Sequence[DetectedPattern],
    out_path: str,
    title: str = "",
    max_bars: int = 220,
) -> str:
    """Per-timeframe overview PNG (light). With no patterns it is a clean chart — used as
    the vision analyst's input image."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    window = bars.iloc[-max_bars:] if len(bars) > max_bars else bars
    plot_df = _to_plot_df(window)
    draw = _select(patterns)
    fig, axlist = _plot_base(plot_df, title)
    ax = axlist[0]
    _draw_geometry(ax, plot_df, draw)
    _level_pills(ax, len(plot_df), draw)
    fig.savefig(out_path, dpi=120, bbox_inches="tight", facecolor=_BG)
    plt.close(fig)
    return out_path


def render_pattern_png(
    bars: pd.DataFrame, pattern: DetectedPattern, out_path: str, title: str = ""
) -> str:
    """Focused PNG zoomed to ONE structure: its region + margin, its geometry, level pills
    and a shaded measured-move target box."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    full = _to_plot_df(bars)
    idx = full.index
    s = idx.get_indexer([pd.Timestamp(pattern.region_start)], method="nearest")[0]
    e = idx.get_indexer([pd.Timestamp(pattern.region_end)], method="nearest")[0]
    span = max(e - s, 5)
    left = max(0, s - int(span * 0.6) - 5)
    right = min(len(idx), e + int(span * 0.9) + 8)
    plot_df = full.iloc[left:right]
    if len(plot_df) < 3:
        plot_df = full.iloc[-60:]

    fig, axlist = _plot_base(plot_df, title)
    ax = axlist[0]
    _draw_geometry(ax, plot_df, [pattern])
    width = len(plot_df)
    # measured-move target box across the right portion
    bo, tg = pattern.levels.get("breakout"), pattern.levels.get("target")
    if bo is not None and tg is not None:
        box_color = _UP if pattern.direction == "bullish" else _DOWN
        ax.axhspan(min(bo, tg), max(bo, tg), xmin=0.55, color=box_color, alpha=0.08)
    _level_pills(ax, width, [pattern])
    fig.savefig(out_path, dpi=120, bbox_inches="tight", facecolor=_BG)
    plt.close(fig)
    return out_path


# --------------------- AI-thesis shapes (the analyst's drawing) ---------------------

_SHAPE_COLOR = {
    "primary": "#2962ff",
    "resistance": "#2962ff",
    "neckline": "#2962ff",
    "entry": "#2962ff",
    "breakout": "#2962ff",
    "secondary": "#7e57c2",
    "support": "#089981",
    "target": "#089981",
    "stop": "#f23645",
    "cap": "#f23645",
    "context": "#90a4ae",  # muted blue-gray: supporting CONTEXT (rounding bottom etc.)
}


def _draw_shapes(ax: Any, plot_df: pd.DataFrame, shapes: Sequence[Shape]) -> None:
    """Draw the shapes the AI analyst specified (rails, arcs, levels, zones, markers)."""
    width = len(plot_df)

    def pos(ts: object) -> int:
        loc = plot_df.index.get_indexer([pd.Timestamp(ts)], method="nearest")
        return int(loc[0]) if len(loc) else 0

    for sh in shapes:
        color = sh.color or _SHAPE_COLOR.get(sh.role, "#7e57c2")
        pts = sh.points
        if sh.kind in (ShapeKind.TRENDLINE, ShapeKind.CURVE) and len(pts) >= 2:
            # thick, solid bounding rail (resistance / support / neckline)
            ax.plot([pos(p.ts) for p in pts], [p.price for p in pts], color=color, linewidth=2.4)
        elif sh.kind == ShapeKind.HLINE and pts:
            ax.axhline(pts[0].price, color=color, linestyle="--", linewidth=1.2, alpha=0.8)
        elif sh.kind == ShapeKind.ZONE and len(pts) >= 2:
            ax.axhspan(
                min(p.price for p in pts), max(p.price for p in pts), color=color, alpha=0.08
            )
        elif sh.kind == ShapeKind.MARKER:
            for p in pts:
                x = pos(p.ts)
                if 0 <= x < width:
                    ax.scatter([x], [p.price], color=color, s=34, zorder=5)
                    if sh.label:
                        ax.annotate(
                            sh.label,
                            xy=(x, p.price),
                            xytext=(0, -12),
                            textcoords="offset points",
                            ha="center",
                            va="top",
                            fontsize=8,
                            color=color,
                            zorder=6,
                        )


def _note_pills(ax: Any, width: int, notes: Sequence[PriceNote]) -> None:
    """TradingView-style filled price pills for the analyst's price notes (deduped)."""
    seen: set[float] = set()
    for n in notes:
        r = round(n.price, 2)
        if r in seen:
            continue
        seen.add(r)
        color = _SHAPE_COLOR.get(n.kind, "#2962ff")
        ax.axhline(n.price, color=color, linewidth=0.9, linestyle="--", alpha=0.6)
        ax.annotate(
            n.label or f"{n.price:.2f}",
            xy=(width - 1, n.price),
            xytext=(4, 0),
            textcoords="offset points",
            va="center",
            ha="left",
            fontsize=8,
            color="white",
            bbox={"boxstyle": "round,pad=0.25", "fc": color, "ec": color},
            zorder=6,
        )


def render_thesis_png(
    bars: pd.DataFrame, thesis: TimeframeThesis, out_path: str, title: str = "", max_bars: int = 200
) -> str:
    """Static PNG of the AI analyst's thesis (its shapes + price notes) on a recent window."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    window = bars.iloc[-max_bars:] if len(bars) > max_bars else bars
    plot_df = _to_plot_df(window)
    fig, axlist = _plot_base(plot_df, title or thesis.pattern_label)
    ax = axlist[0]
    _draw_shapes(ax, plot_df, thesis.shapes)
    _note_pills(ax, len(plot_df), thesis.price_notes)
    fig.savefig(out_path, dpi=120, bbox_inches="tight", facecolor=_BG)
    plt.close(fig)
    return out_path
