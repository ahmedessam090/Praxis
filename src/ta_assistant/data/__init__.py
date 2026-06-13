"""Layer 1 — data providers (Phase 1 stubs).

Activities call these; workflows never do. Real implementations import their heavy
SDKs (alpaca-py, fredapi, yfinance — the `data` dependency group) INSIDE functions
so those imports never reach the Temporal workflow sandbox.
"""
