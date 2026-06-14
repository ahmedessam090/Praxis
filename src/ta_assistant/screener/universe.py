"""The curated, sector-tagged candidate universe the scanner screens (~190 liquid US
large/mid caps across the 11 GICS sectors). Static + easy to extend; the favour algorithm
allocates scan budget across sectors by the regime's Sector Leadership ranking. Sector keys
match regime.universe.SECTOR_ETF."""

from __future__ import annotations

from ta_assistant.regime import universe as RU

SECTOR_UNIVERSE: dict[str, list[str]] = {
    "technology": [
        "AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "ADBE", "AMD", "ACN", "CSCO",
        "INTC", "QCOM", "TXN", "IBM", "NOW", "INTU", "AMAT", "MU", "LRCX", "ANET",
        "PANW", "SNPS", "CDNS", "KLAC", "CRWD",
    ],
    "communication": [
        "GOOGL", "META", "NFLX", "DIS", "CMCSA", "TMUS", "VZ", "T", "CHTR", "EA",
        "TTWO", "WBD", "OMC",
    ],
    "discretionary": [
        "AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "LOW", "BKNG", "TJX", "ORLY",
        "CMG", "MAR", "GM", "F", "ABNB", "ROST", "YUM", "HLT",
    ],
    "staples": [
        "WMT", "COST", "PG", "KO", "PEP", "PM", "MO", "MDLZ", "CL", "TGT",
        "KMB", "GIS", "KR", "SYY", "STZ",
    ],
    "health": [
        "LLY", "UNH", "JNJ", "MRK", "ABBV", "TMO", "ABT", "DHR", "PFE", "AMGN",
        "ISRG", "BMY", "GILD", "VRTX", "REGN", "CVS", "MDT", "ELV", "CI",
    ],
    "financials": [
        "JPM", "BAC", "WFC", "GS", "MS", "SPGI", "BLK", "C", "AXP", "SCHW",
        "CB", "PGR", "MMC", "BX", "KKR", "V", "MA", "USB", "PNC",
    ],
    "industrials": [
        "CAT", "GE", "HON", "UNP", "BA", "RTX", "UPS", "DE", "LMT", "ETN",
        "EMR", "GD", "NOC", "CSX", "FDX", "NSC", "WM", "ITW", "PH", "MMM",
    ],
    "energy": [
        "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "WMB",
        "KMI", "HES", "OKE", "DVN", "HAL",
    ],
    "materials": [
        "LIN", "SHW", "APD", "ECL", "FCX", "NEM", "NUE", "DOW", "DD", "CTVA",
        "VMC", "MLM", "PPG", "ALB",
    ],
    "utilities": [
        "NEE", "DUK", "SO", "D", "AEP", "SRE", "EXC", "XEL", "PEG", "ED",
        "WEC", "ES", "PCG", "EIX",
    ],
    "real_estate": [
        "PLD", "AMT", "EQIX", "WELL", "SPG", "PSA", "O", "CCI", "DLR", "VICI",
        "CBRE", "EXR", "AVB", "EQR",
    ],
}


def all_candidates() -> list[str]:
    """Every candidate symbol, de-duplicated, stable order."""
    seen: dict[str, None] = {}
    for names in SECTOR_UNIVERSE.values():
        for s in names:
            seen.setdefault(s, None)
    return list(seen)


def sector_of(symbol: str) -> str | None:
    for sector, names in SECTOR_UNIVERSE.items():
        if symbol in names:
            return sector
    return None


def scan_symbols() -> list[str]:
    """Everything a scan needs to fetch: SPY + sector ETFs + the candidate universe."""
    return [RU.SPY, *RU.SECTOR_ETFS, *all_candidates()]


def screen_fetch_groups(chunk: int = 25) -> list[list[str]]:
    """Scan symbols split into balanced buckets for parallel fan-out fetch."""
    syms = scan_symbols()
    return [syms[i : i + chunk] for i in range(0, len(syms), chunk)]
