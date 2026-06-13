"""Layer 2 — rule-based pattern-recognition engine (Phase 1+).

Detect swing highs/lows, fit trendlines, and template-match classical formations
(ascending/descending triangles, rectangles, head-and-shoulders, flags, wedges),
emitting geometry + entry/breakout/stop/target levels. Interpretable by design;
ML detection is a deliberately deferred, optional upgrade. Imported and run inside
activities, never in workflow code.
"""
