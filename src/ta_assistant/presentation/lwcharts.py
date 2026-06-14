"""TradingView lightweight-charts (v5) renderer — embedded as self-contained, OFFLINE HTML.

We build a small JSON payload from the bars + the AI analyst's thesis (candles, MAs,
volume, the shapes to draw as line series, labelled price lines for the price notes, and
pivot markers) and inline it next to the VENDORED standalone library, so the chart renders
with zero network access. `app.py` drops the returned HTML into `st.components.v1.html`.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from ta_assistant.synthesis.schema import RegimeChart, ShapeKind, TimeframeThesis

_VENDOR = Path(__file__).resolve().parent / "vendor" / "lightweight-charts.standalone.production.js"

_UP = "#089981"
_DOWN = "#f23645"
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
    "level": "#787b86",
    "context": "#90a4ae",  # supporting context (rounding bottom saucer)
}
_MA = [(50, "#2962ff"), (150, "#ff9800"), (200, "#9c27b0")]


@lru_cache(maxsize=1)
def _vendor_js() -> str:
    return _VENDOR.read_text(encoding="utf-8") if _VENDOR.exists() else ""


def _d(ts: object) -> int:
    """UNIX seconds. lightweight-charts slots weekly/monthly bars by data point with UNIX
    timestamps; business-day date strings instead leave empty calendar-day gaps (the bars
    get crushed to the right edge). So always emit UNIX time."""
    return int(pd.Timestamp(ts).timestamp())


def _line_series(points: list[Any]) -> list[dict[str, Any]]:
    """Sorted, de-duplicated {time,value} for a lightweight-charts line series."""
    seen: dict[int, float] = {}
    for p in points:
        seen[_d(p.ts)] = round(float(p.price), 4)
    return [{"time": t, "value": v} for t, v in sorted(seen.items())]


def build_payload(
    bars: pd.DataFrame, thesis: TimeframeThesis | None, visible_bars: int
) -> dict[str, Any]:
    # Show a recent window (wide enough to still contain the multi-year rails). Every other
    # series is clipped to `start` so nothing extends LEFT of the candles and crushes them.
    keep = visible_bars + 110
    window = bars.iloc[-keep:] if len(bars) > keep else bars
    start = _d(window.index[0])
    candles = [
        {
            "time": _d(ts),
            "open": round(float(r.open), 4),
            "high": round(float(r.high), 4),
            "low": round(float(r.low), 4),
            "close": round(float(r.close), 4),
        }
        for ts, r in window.iterrows()
    ]
    up = window["close"].to_numpy() >= window["open"].to_numpy()
    volume = [
        {"time": c["time"], "value": int(v), "color": (_UP if u else _DOWN) + "55"}
        for c, v, u in zip(candles, window["volume"].to_numpy(), up, strict=False)
    ]
    mas = []
    for length, color in _MA:
        if len(bars) >= length:  # compute over FULL history, then clip to the window
            ma = bars["close"].rolling(length, min_periods=length).mean()
            data = [
                {"time": _d(ts), "value": round(float(v), 4)}
                for ts, v in ma.items()
                if pd.notna(v) and _d(ts) >= start
            ]
            if data:
                mas.append({"color": color, "data": data})

    lines: list[dict[str, Any]] = []
    markers: list[dict[str, Any]] = []
    price_lines: list[dict[str, Any]] = []
    if thesis is not None:
        for sh in thesis.shapes:
            color = sh.color or _SHAPE_COLOR.get(sh.role, "#7e57c2")
            if sh.kind in (ShapeKind.TRENDLINE, ShapeKind.CURVE) and len(sh.points) >= 2:
                data = [d for d in _line_series(sh.points) if d["time"] >= start]
                if len(data) >= 2:
                    lines.append({"color": color, "data": data})
            elif sh.kind == ShapeKind.HLINE and sh.points:
                price_lines.append(
                    {
                        "price": round(float(sh.points[0].price), 4),
                        "color": color,
                        "title": sh.label,
                    }
                )
            elif sh.kind == ShapeKind.ZONE and len(sh.points) >= 2:
                for p in sh.points:
                    price_lines.append(
                        {"price": round(float(p.price), 4), "color": color, "title": sh.label}
                    )
            elif sh.kind == ShapeKind.MARKER:
                for p in sh.points:
                    tt = _d(p.ts)
                    if tt >= start:
                        markers.append(
                            {
                                "time": tt,
                                "position": "belowBar",
                                "color": color,
                                "shape": "circle",
                                "text": sh.label,
                            }
                        )
        for n in thesis.price_notes:
            price_lines.append(
                {
                    "price": round(float(n.price), 4),
                    "color": _SHAPE_COLOR.get(n.kind, "#2962ff"),
                    "title": n.label,
                }
            )

    # one tag per distinct price level (no stacked/duplicate labels)
    deduped: list[dict[str, Any]] = []
    seen: set[float] = set()
    for pl in price_lines:
        key = round(float(pl["price"]), 2)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(pl)

    markers.sort(key=lambda m: m["time"])  # lightweight-charts requires ascending marker time
    return {
        "candles": candles,
        "volume": volume,
        "mas": mas,
        "lines": lines,
        "priceLines": deduped,
        "markers": markers,
    }


_INIT_JS = """
const D = __PAYLOAD__;
const el = document.getElementById('chart');
const chart = LightweightCharts.createChart(el, {
  autoSize: true, height: 640,
  layout: { background: { color: '#ffffff' }, textColor: '#131722' },
  grid: { vertLines: { color: '#e1e3ea' }, horzLines: { color: '#e1e3ea' } },
  rightPriceScale: { borderColor: '#e1e3ea', mode: 1 },
  timeScale: { borderColor: '#e1e3ea', timeVisible: false },
  crosshair: { mode: 1 },
});
const candle = chart.addSeries(LightweightCharts.CandlestickSeries, {
  upColor: '#089981', downColor: '#f23645', borderVisible: false,
  wickUpColor: '#089981', wickDownColor: '#f23645',
});
candle.setData(D.candles);
(D.mas || []).forEach(m => {
  const s = chart.addSeries(LightweightCharts.LineSeries,
    { color: m.color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
  s.setData(m.data);
});
const vol = chart.addSeries(LightweightCharts.HistogramSeries,
  { priceScaleId: 'vol', priceFormat: { type: 'volume' }, lastValueVisible: false });
vol.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
vol.setData(D.volume);
(D.lines || []).forEach(ln => {
  const s = chart.addSeries(LightweightCharts.LineSeries,
    { color: ln.color, lineWidth: 3, priceLineVisible: false, lastValueVisible: false });
  s.setData(ln.data);
});
(D.priceLines || []).forEach(pl => candle.createPriceLine(
  { price: pl.price, color: pl.color, lineWidth: 1, lineStyle: 2,
    axisLabelVisible: true, title: pl.title || '' }));
if ((D.markers || []).length && LightweightCharts.createSeriesMarkers) {
  LightweightCharts.createSeriesMarkers(candle, D.markers);
}
// only the recent window was sent -> fitContent fills the width. Re-fit on resize because
// the iframe often has width 0 at first paint (fitContent then would size to nothing).
const __fit = () => { try { chart.timeScale().fitContent(); } catch (e) {} };
__fit();
new ResizeObserver(__fit).observe(el);
setTimeout(__fit, 80); setTimeout(__fit, 350);
"""


def build_lwc_html(
    bars: pd.DataFrame,
    thesis: TimeframeThesis | None,
    *,
    title: str = "",
    visible_bars: int = 130,
    height: int = 660,
) -> str:
    """Self-contained HTML embedding the vendored lightweight-charts library + this chart's
    data. Renders fully offline. If the library isn't vendored, returns a clear notice."""
    js = _vendor_js()
    if not js:
        return (
            "<div style='padding:1rem;font-family:sans-serif;color:#b00'>"
            "lightweight-charts is not vendored — run the build step to download "
            "<code>lightweight-charts.standalone.production.js</code>.</div>"
        )
    payload = json.dumps(build_payload(bars, thesis, visible_bars))
    init = _INIT_JS.replace("__PAYLOAD__", payload)
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<script>{js}</script></head>"
        "<body style='margin:0'>"
        f"<div style='font-family:sans-serif;color:#131722;font-size:14px;"
        f"padding:4px 8px'>{title}</div>"
        f"<div id='chart' style='width:100%;height:{height - 20}px'></div>"
        f"<script>{init}</script>"
        "</body></html>"
    )


# --------------------------- Market Regime charts ---------------------------


def build_regime_payload(chart: RegimeChart) -> dict[str, Any]:
    """Line + candle series + markers for one regime chart (UNIX-seconds time)."""
    series: list[dict[str, Any]] = []
    for s in chart.series:
        if s.kind == "candle":
            data = [
                {
                    "time": _d(c.ts),
                    "open": round(float(c.open), 4),
                    "high": round(float(c.high), 4),
                    "low": round(float(c.low), 4),
                    "close": round(float(c.close), 4),
                }
                for c in s.candles
            ]
            series.append({"type": "candle", "label": s.label, "data": data})
        else:
            data = [{"time": _d(p.ts), "value": round(float(p.value), 4)} for p in s.points]
            series.append(
                {"type": "line", "label": s.label, "color": s.color or "#2962ff", "data": data}
            )
    markers: list[dict[str, Any]] = [
        {
            "time": _d(m.ts),
            "position": m.position or "belowBar",
            "color": m.color or "#787b86",
            "shape": m.shape or "circle",
            "text": m.label,
        }
        for m in chart.markers
    ]
    markers.sort(key=lambda m: m["time"])
    return {"series": series, "markers": markers}


_REGIME_INIT_JS = """
const D = __PAYLOAD__;
const el = document.getElementById('chart');
const chart = LightweightCharts.createChart(el, {
  autoSize: true, height: __HEIGHT__,
  layout: { background: { color: '#ffffff' }, textColor: '#131722' },
  grid: { vertLines: { color: '#eef0f4' }, horzLines: { color: '#eef0f4' } },
  rightPriceScale: { borderColor: '#e1e3ea' },
  timeScale: { borderColor: '#e1e3ea', timeVisible: false },
  crosshair: { mode: 1 },
});
let anchor = null;
(D.series || []).forEach(s => {
  if (s.type === 'candle') {
    const cs = chart.addSeries(LightweightCharts.CandlestickSeries, {
      upColor: '#089981', downColor: '#f23645', borderVisible: false,
      wickUpColor: '#089981', wickDownColor: '#f23645',
    });
    cs.setData(s.data); if (!anchor) anchor = cs;
  } else {
    const ls = chart.addSeries(LightweightCharts.LineSeries,
      { color: s.color, lineWidth: 2, priceLineVisible: false, lastValueVisible: true });
    ls.setData(s.data); if (!anchor) anchor = ls;
  }
});
if ((D.markers || []).length && anchor && LightweightCharts.createSeriesMarkers) {
  LightweightCharts.createSeriesMarkers(anchor, D.markers);
}
const __fit = () => { try { chart.timeScale().fitContent(); } catch (e) {} };
__fit();
new ResizeObserver(__fit).observe(el);
setTimeout(__fit, 80); setTimeout(__fit, 350);
"""


def build_regime_chart_html(chart: RegimeChart, *, height: int = 320) -> str:
    """Self-contained, offline HTML for ONE regime chart (the vendored lightweight-charts
    library inlined + the ResizeObserver fitContent fix), drawing its line/candle series
    and markers. `app.py` drops the result into `st.components.v1.html`."""
    js = _vendor_js()
    if not js:
        return (
            "<div style='padding:1rem;font-family:sans-serif;color:#b00'>"
            "lightweight-charts is not vendored.</div>"
        )
    payload = json.dumps(build_regime_payload(chart))
    init = _REGIME_INIT_JS.replace("__PAYLOAD__", payload).replace("__HEIGHT__", str(height - 26))
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<script>{js}</script></head>"
        "<body style='margin:0'>"
        f"<div style='font-family:sans-serif;color:#131722;font-size:13px;"
        f"padding:2px 8px'>{chart.title}</div>"
        f"<div id='chart' style='width:100%;height:{height - 26}px'></div>"
        f"<script>{init}</script>"
        "</body></html>"
    )
