"""Vision consensus: deterministic fallback, verdict application, caching, factory."""

from __future__ import annotations

from datetime import datetime

from ta_assistant.config import Settings
from ta_assistant.synthesis.schema import DetectedPattern, PatternStatus, Timeframe
from ta_assistant.synthesis.validator import (
    ConsensusResult,
    ConsensusValidator,
    NullConsensus,
    PatternVerdict,
    apply_consensus,
    consensus_cached,
    get_validator,
)


def _pattern(pid: str = "p1", role: str = "primary", conf: float = 0.6) -> DetectedPattern:
    return DetectedPattern(
        id=pid,
        pattern_type="double_bottom",
        timeframe=Timeframe.DAILY,
        status=PatternStatus.CONFIRMED,
        geometry_confidence=conf,
        confidence=conf,
        role=role,
        levels={"breakout": 100.0, "stop": 90.0, "target": 120.0},
        region_start=datetime(2024, 1, 1),
        region_end=datetime(2024, 3, 1),
        entry=100.0,
        stop=90.0,
        target=120.0,
    )


def test_null_consensus_keeps_deterministic_roles() -> None:
    p = _pattern(role="primary", conf=0.6)
    result = NullConsensus().consensus("daily", None, [p])
    assert result.verdicts[0].role == "primary"
    assert result.verdicts[0].confidence == 0.6


def test_apply_consensus_sets_role_label_confidence() -> None:
    p = _pattern(role="considered")
    apply_consensus(
        [p],
        ConsensusResult(
            timeframe="daily",
            read="ascending triangle forming",
            verdicts=[
                PatternVerdict(
                    id="p1",
                    is_valid=True,
                    role="primary",
                    label="ascending triangle",
                    confidence=0.82,
                    rationale="flat top, rising lows",
                )
            ],
        ),
    )
    assert p.role == "primary"
    assert p.label_override == "ascending triangle"
    assert p.display_label == "ascending triangle"
    assert p.confidence == 0.82
    # levels are owned by geometry and never moved by consensus
    assert p.levels["breakout"] == 100.0


def test_apply_consensus_invalid_becomes_considered() -> None:
    p = _pattern(role="primary")
    apply_consensus(
        [p],
        ConsensusResult(verdicts=[PatternVerdict(id="p1", is_valid=False, role="primary")]),
    )
    assert p.role == "considered"


def test_apply_consensus_enforces_single_primary() -> None:
    a, b = _pattern("a", conf=0.7), _pattern("b", conf=0.9)
    apply_consensus(
        [a, b],
        ConsensusResult(
            verdicts=[
                PatternVerdict(id="a", role="primary", confidence=0.7),
                PatternVerdict(id="b", role="primary", confidence=0.9),
            ]
        ),
    )
    primaries = [p for p in (a, b) if p.role == "primary"]
    assert len(primaries) == 1
    assert primaries[0].id == "b"  # the higher-confidence one keeps primary


def test_consensus_cached_only_calls_once(temp_db: str) -> None:
    class _Counting:
        def __init__(self) -> None:
            self.calls = 0

        def consensus(
            self, timeframe: str, image_path: str | None, candidates: list[DetectedPattern]
        ) -> ConsensusResult:
            self.calls += 1
            return ConsensusResult(timeframe=timeframe, read="x")

    validator = _Counting()
    cands = [_pattern()]
    r1 = consensus_cached(validator, "daily", None, cands, "test-model", db_path=temp_db)
    r2 = consensus_cached(validator, "daily", None, cands, "test-model", db_path=temp_db)
    assert validator.calls == 1  # second served from cache
    assert r1.read == r2.read == "x"


def test_factory_returns_null_when_disabled() -> None:
    assert isinstance(get_validator(Settings(_env_file=None, llm_enabled=False)), NullConsensus)
    assert isinstance(get_validator(Settings(_env_file=None, llm_enabled=True)), NullConsensus)


def test_protocol_is_satisfied() -> None:
    v: ConsensusValidator = NullConsensus()
    assert v.consensus("daily", None, [_pattern()]).verdicts
