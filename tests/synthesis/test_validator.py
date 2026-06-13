"""LLM validator: passthrough, clamped level nudges, content-hash caching, factory."""

from __future__ import annotations

from datetime import datetime

import pytest

from ta_assistant.config import Settings
from ta_assistant.synthesis.schema import DetectedPattern, PatternStatus, Timeframe
from ta_assistant.synthesis.validator import (
    NullValidator,
    PatternValidator,
    ValidationResult,
    apply_validation,
    get_validator,
    validate_cached,
)


def _pattern() -> DetectedPattern:
    return DetectedPattern(
        id="p1",
        pattern_type="double_bottom",
        timeframe=Timeframe.DAILY,
        status=PatternStatus.CONFIRMED,
        geometry_confidence=0.6,
        confidence=0.6,
        levels={"breakout": 100.0, "stop": 90.0, "target": 120.0},
        region_start=datetime(2024, 1, 1),
        region_end=datetime(2024, 3, 1),
        entry=100.0,
        stop=90.0,
        target=120.0,
    )


class _CountingValidator:
    def __init__(self) -> None:
        self.calls = 0

    def validate(self, pattern: DetectedPattern, image_path: str | None = None) -> ValidationResult:
        self.calls += 1
        return ValidationResult(
            is_valid=True, best_label="x", refined_confidence=0.8, rationale="ok"
        )


def test_null_validator_passes_geometry_through() -> None:
    result = NullValidator().validate(_pattern())
    assert result.is_valid
    assert result.refined_confidence == 0.6


def test_apply_validation_clamps_out_of_bounds_nudge() -> None:
    pattern = _pattern()
    apply_validation(
        pattern,
        ValidationResult(
            is_valid=True,
            best_label="x",
            refined_confidence=0.9,
            level_adjustments={"breakout": 130.0},
        ),  # +30% nudge
        max_frac=0.02,
    )
    assert pattern.levels["breakout"] == pytest.approx(102.0)  # clamped to +2%
    assert pattern.entry == pytest.approx(102.0)
    assert pattern.confidence == 0.9


def test_validate_cached_only_calls_once(temp_db: str) -> None:
    validator = _CountingValidator()
    pattern = _pattern()
    r1 = validate_cached(validator, pattern, None, "test-model", db_path=temp_db)
    r2 = validate_cached(validator, pattern, None, "test-model", db_path=temp_db)
    assert validator.calls == 1  # second served from cache
    assert r1.refined_confidence == r2.refined_confidence == 0.8


def test_factory_returns_null_when_disabled() -> None:
    assert isinstance(get_validator(Settings(_env_file=None, llm_enabled=False)), NullValidator)
    # enabled but no key -> still Null (engine runs keyless)
    assert isinstance(get_validator(Settings(_env_file=None, llm_enabled=True)), NullValidator)


def test_protocol_is_satisfied() -> None:
    v: PatternValidator = NullValidator()
    assert v.validate(_pattern(), None).is_valid
