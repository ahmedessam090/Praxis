"""The symbols the Market Regime read pulls, grouped by role.

Grouped so the workflow can fan out the fetch. yfinance symbols; `get_daily_history`
falls back to Stooq on failure. Index symbols use the `^` prefix; commodities use
continuous futures (`=F`) with a liquid ETF as the robust trend proxy.
"""

from __future__ import annotations

# --- Primary indices (Dow Theory / Weinstein stage / O'Neil supply-demand) ---
SP500 = "^GSPC"
NASDAQ = "^IXIC"
DOW_INDUSTRIALS = "^DJI"
DOW_TRANSPORTS = "^DJT"
DOW_UTILITIES = "^DJU"
VIX = "^VIX"

INDICES = [SP500, NASDAQ, DOW_INDUSTRIALS, DOW_TRANSPORTS, DOW_UTILITIES, VIX]

# --- Commodities (Murphy intermarket) — futures price + ETF trend proxy ---
# (symbol -> (primary futures, ETF fallback/proxy))
GOLD = "GC=F"
SILVER = "SI=F"
OIL = "CL=F"
COPPER = "HG=F"
COMMODITY_ETF = {GOLD: "GLD", SILVER: "SLV", OIL: "USO", COPPER: "CPER"}
COMMODITIES = [GOLD, SILVER, OIL, COPPER]
COMMODITY_ETFS = list(COMMODITY_ETF.values())

# --- US Dollar Index (DXY) with fallbacks ---
DXY = "DX-Y.NYB"
DXY_FALLBACKS = ["DX=F", "UUP"]

# --- Intermarket ETFs (risk-on/off leadership, credit, bonds) ---
SPY = "SPY"
RSP = "RSP"  # equal-weight S&P — breadth proxy vs SPY
DISCRETIONARY = "XLY"
STAPLES = "XLP"
TECH = "XLK"
SEMIS = "SMH"
SOFTWARE = "IGV"  # long-duration growth — sensitive liquidity-cycle barometer
UTILITIES_ETF = "XLU"
TRANSPORTS_ETF = "IYT"
HIGH_YIELD = "HYG"  # credit risk appetite
LONG_TREASURY = "TLT"
IG_CREDIT = "LQD"
HIGH_BETA = "SPHB"
LOW_VOL = "SPLV"

INTERMARKET = [
    SPY,
    RSP,
    DISCRETIONARY,
    STAPLES,
    TECH,
    SEMIS,
    SOFTWARE,
    UTILITIES_ETF,
    TRANSPORTS_ETF,
    HIGH_YIELD,
    LONG_TREASURY,
    IG_CREDIT,
    HIGH_BETA,
    LOW_VOL,
]

# --- Breadth basket: ~45 liquid, sector-spread large caps (proxy for % above MA /
# net new highs-lows, since yfinance lacks an exchange-wide A/D feed). Reusable later
# for the Alpha-list universe screener. ---
BREADTH_BASKET = [
    # Technology / semis
    "AAPL", "MSFT", "NVDA", "AVGO", "AMD", "ORCL", "CRM", "ADBE", "CSCO", "QCOM",
    # Communication
    "GOOGL", "META", "NFLX", "DIS", "TMUS",
    # Consumer discretionary
    "AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX",
    # Consumer staples
    "WMT", "COST", "PG", "KO", "PEP",
    # Financials
    "JPM", "BAC", "GS", "V", "MA", "BRK-B",
    # Health care
    "UNH", "JNJ", "LLY", "ABBV", "MRK",
    # Industrials
    "CAT", "BA", "GE", "HON", "UPS",
    # Energy / materials
    "XOM", "CVX", "LIN",
]


def all_symbols() -> list[str]:
    """Every symbol a refresh needs, de-duplicated, in a stable order."""
    seen: dict[str, None] = {}
    for group in (
        INDICES,
        COMMODITIES,
        COMMODITY_ETFS,
        [DXY, *DXY_FALLBACKS],
        INTERMARKET,
        BREADTH_BASKET,
    ):
        for s in group:
            seen.setdefault(s, None)
    return list(seen)


def fetch_groups() -> list[list[str]]:
    """Symbols split into balanced buckets for parallel fan-out (cap basket bucket
    size to keep any one activity bounded and avoid yfinance throttling)."""
    groups: list[list[str]] = [
        INDICES,
        [*COMMODITIES, *COMMODITY_ETFS, DXY, *DXY_FALLBACKS],
        INTERMARKET,
    ]
    basket = BREADTH_BASKET
    chunk = 15
    for start in range(0, len(basket), chunk):
        groups.append(basket[start : start + chunk])
    return groups
