"""Layer 4 — decision / synthesis layer (Phase 4).

Deterministic code computes the numbers (pattern fits, indicators, regime score,
sizing); an LLM then writes the reasoned, graded verdict (skip / watch / take
small / take full). Code for math, LLM for judgment. The LLM call lives in an
activity (the `llm` dependency group), never in workflow code.
"""
