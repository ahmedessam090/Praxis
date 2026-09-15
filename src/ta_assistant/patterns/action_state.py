"""Where is a (long) setup in its life-cycle relative to its trigger price?

This is the single source of truth for the structural question "is this setup pre-trigger,
in range, past range, or done", shared by the pattern detectors (candidate level) and the
alpha gate (thesis level). It is deliberately light (stdlib + pydantic only — no pandas, no
imports from `synthesis.schema`) so it can be imported from anywhere, including the schema.

The vocabulary is deliberately descriptive rather than directive: these values name where
price sits relative to the measured pivot, and are not instructions to transact.

Key guard: it validates the EFFECTIVE entry (`stop < entry < target`), which is the exact hole
the MU bug slipped through — a re-break entry of 1091 above an already-hit target of 1043.85.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BeforeValidator

# PatternStatus values (kept as literals so this module imports nothing from the schema).
_FORMING = "forming"
_CONFIRMED = "confirmed"
_TRIGGERED = "triggered"
_INVALIDATED = "invalidated"

_DEFAULT_BAND = 0.04  # price is still within ~4% above the pivot
_ATR_K = 1.0  # widen the trigger range by ~1 ATR for volatile names


class ActionState(StrEnum):
    """Where price sits relative to the setup's measured trigger. Descriptive, not directive."""

    NOT_YET = "not_yet"  # structure incomplete — no defined trigger yet
    AWAITING_BREAK = "awaiting_break"  # formed base, price still below the pivot
    IN_RANGE = "in_range"  # broke the pivot, price still inside the trigger range
    EXTENDED = "extended"  # broke out and ran past the trigger range, target not yet reached
    PLAYED_OUT = "played_out"  # already reached/exceeded the target — the move is done
    INVALID = "invalid"  # incoherent levels (e.g. entry above target) or invalidated


# Values persisted before the vocabulary was made descriptive. Old rows in `alpha_items`,
# `analyses.payload_json` and `llm_cache` still carry these, so everything that reads a
# stored state normalises through `normalize_state` rather than matching the enum directly.
_LEGACY_STATES = {
    "buy_now": ActionState.IN_RANGE.value,
    "buy_on_break": ActionState.AWAITING_BREAK.value,
}


def normalize_state(state: object) -> str:
    """Map a possibly-legacy stored state onto the current vocabulary.

    Unknown strings pass through unchanged, so a value added later never silently becomes ''.
    Anything that isn't a non-empty string normalises to '' (the "not computed" sentinel),
    which makes this safe to use as a pydantic `BeforeValidator` on untrusted stored JSON.
    """
    if not isinstance(state, str) or not state:
        return ""
    return _LEGACY_STATES.get(state, state)


# Drop-in field type for the two schema models that persist a state: normalises legacy values
# on deserialisation, so rows written before the rename still resolve on read.
ActionStateStr = Annotated[str, BeforeValidator(normalize_state)]


def trigger_zone(breakout: float, atr: float | None = None) -> tuple[float, float]:
    """The band just above a breakout pivot within which price is still close to the trigger.
    Percent-based, widened by ATR when available so a volatile name gets a proportionally
    wider range."""
    band = _DEFAULT_BAND
    if atr is not None and atr > 0 and breakout > 0:
        band = max(_DEFAULT_BAND, _ATR_K * atr / breakout)
    return breakout, breakout * (1.0 + band)


def action_state(
    entry: float | None,
    breakout: float | None,
    target: float | None,
    stop: float | None,
    status: str,
    last_close: float,
    atr: float | None = None,
) -> tuple[ActionState, float | None, float | None]:
    """Classify a LONG setup's life-cycle. Returns (state, trigger_zone_low, trigger_zone_high).

    Only IN_RANGE / AWAITING_BREAK / EXTENDED describe a setup with a live trigger; NOT_YET
    (forming), PLAYED_OUT, and INVALID do not. The zone is None unless a trigger exists.
    """
    s = str(status)
    if s == _INVALIDATED:
        return ActionState.INVALID, None, None
    if s == _FORMING:  # structure not complete — nothing to act on yet (no firm levels needed)
        return ActionState.NOT_YET, None, None
    # Confirmed / triggered must carry coherent levels: the EFFECTIVE entry sits between a
    # positive stop and target, and so does the breakout. This rejects the MU case outright.
    eff_entry = entry if entry is not None else breakout
    if (
        breakout is None
        or target is None
        or stop is None
        or eff_entry is None
        or last_close <= 0
        or not (0 < stop < eff_entry < target)
        or not (0 < stop < breakout < target)
    ):
        return ActionState.INVALID, None, None
    if last_close >= target:  # the measured move is already done
        return ActionState.PLAYED_OUT, None, None

    zone_low, zone_high = trigger_zone(breakout, atr)
    if s == _CONFIRMED:  # complete base, price still below its pivot
        return ActionState.AWAITING_BREAK, zone_low, zone_high
    if s == _TRIGGERED:  # broke out — inside the trigger range, or past it
        if last_close <= zone_high:
            return ActionState.IN_RANGE, zone_low, zone_high
        return ActionState.EXTENDED, zone_low, zone_high
    return ActionState.NOT_YET, None, None  # unknown status — don't guess it's tradeable
