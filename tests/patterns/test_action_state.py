"""The shared 'where is price vs the trigger' life-cycle classifier."""

from __future__ import annotations

from ta_assistant.patterns.action_state import (
    ActionState,
    action_state,
    normalize_state,
    trigger_zone,
)


def _state(entry, breakout, target, stop, status, last_close, atr=None) -> ActionState:
    return action_state(entry, breakout, target, stop, status, last_close, atr)[0]


def test_mu_regression_entry_above_target_is_invalid() -> None:
    # The exact reported bug: a re-break entry of 1091 above an already-hit target of 1043.85.
    assert _state(1091.0, 818.67, 1043.85, 854.35, "triggered", 1050.0) is ActionState.INVALID


def test_forming_is_not_yet() -> None:
    assert _state(100.0, 100.0, 130.0, 90.0, "forming", 95.0) is ActionState.NOT_YET


def test_confirmed_is_awaiting_break() -> None:
    state, low, high = action_state(100.0, 100.0, 130.0, 90.0, "confirmed", 96.0)
    assert state is ActionState.AWAITING_BREAK
    assert low == 100.0 and high is not None and high > 100.0


def test_triggered_in_zone_is_in_range() -> None:
    # 4% default zone -> up to 104; price at 102 is still inside the trigger range.
    assert _state(100.0, 100.0, 130.0, 90.0, "triggered", 102.0) is ActionState.IN_RANGE


def test_triggered_past_zone_is_extended() -> None:
    # Above the trigger range (104) but below target (130) -> extended.
    state, low, high = action_state(100.0, 100.0, 130.0, 90.0, "triggered", 118.0)
    assert state is ActionState.EXTENDED
    assert high is not None and 118.0 > high


def test_price_at_or_past_target_is_played_out() -> None:
    assert _state(100.0, 100.0, 130.0, 90.0, "triggered", 130.0) is ActionState.PLAYED_OUT
    assert _state(100.0, 100.0, 130.0, 90.0, "confirmed", 131.0) is ActionState.PLAYED_OUT


def test_invalidated_status_is_invalid() -> None:
    assert _state(100.0, 100.0, 130.0, 90.0, "invalidated", 95.0) is ActionState.INVALID


def test_missing_or_misordered_levels_are_invalid() -> None:
    assert _state(None, None, 130.0, 90.0, "confirmed", 95.0) is ActionState.INVALID
    assert _state(100.0, 100.0, 90.0, 95.0, "confirmed", 92.0) is ActionState.INVALID  # target<stop


def test_atr_widens_the_trigger_zone() -> None:
    _, narrow_high = trigger_zone(100.0)  # 4% default -> 104
    _, wide_high = trigger_zone(100.0, atr=8.0)  # 8% ATR > 4% default -> wider
    assert wide_high > narrow_high


def test_legacy_states_normalize_to_the_current_vocabulary() -> None:
    # Rows persisted before the rename must still resolve on read.
    assert normalize_state("buy_now") == ActionState.IN_RANGE.value
    assert normalize_state("buy_on_break") == ActionState.AWAITING_BREAK.value


def test_normalize_state_passes_through_and_defaults_safely() -> None:
    assert normalize_state("extended") == ActionState.EXTENDED.value
    assert normalize_state("some_future_state") == "some_future_state"
    assert normalize_state(None) == ""
    assert normalize_state("") == ""
    assert normalize_state(123) == ""  # non-str stored JSON -> "not computed"
