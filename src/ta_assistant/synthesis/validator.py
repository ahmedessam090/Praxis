"""LLM validation/narration over detected patterns.

A `PatternValidator` judges a deterministic candidate (given its exact levels and
an annotated chart) and writes the narrative. OpenAI is the default; a NullValidator
keeps the engine fully functional with no key. Results are content-hash cached.
The LLM can only *nudge* levels within a tight bound — it never invents them.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from ta_assistant.config import Settings, get_settings
from ta_assistant.synthesis.schema import DetectedPattern

logger = logging.getLogger(__name__)
PROMPT_VERSION = "v1"


class ValidationResult(BaseModel):
    is_valid: bool = True
    best_label: str | None = None
    refined_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    volume_confirmation: str = "neutral"
    caveats: list[str] = Field(default_factory=list)
    rationale: str = ""
    level_adjustments: dict[str, float] = Field(default_factory=dict)


class PatternValidator(Protocol):
    def validate(self, pattern: DetectedPattern, image_path: str | None) -> ValidationResult: ...


class NullValidator:
    """Pass deterministic geometry through unchanged (LLM disabled / tests)."""

    def validate(self, pattern: DetectedPattern, image_path: str | None = None) -> ValidationResult:
        return ValidationResult(
            is_valid=True,
            best_label=pattern.pattern_type,
            refined_confidence=pattern.geometry_confidence,
            rationale="(LLM disabled) deterministic geometry only.",
        )


_SYSTEM = (
    "You are a classical technical-analysis validator in the Brandt/Minervini tradition, "
    "LONG side only. You receive a candidate pattern found by a deterministic geometry engine, "
    "its exact computed levels, and an annotated chart image. Decide if it is a clean, tradeable "
    "instance or geometric noise; you may suggest small level nudges but never invent levels; "
    "prefer rejecting marginal patterns (precision over recall). Respond ONLY as JSON with keys: "
    "is_valid (bool), best_label (str), refined_confidence (0..1), volume_confirmation "
    "('confirms'|'weak'|'absent'|'neutral'), caveats (list[str]), rationale (str), "
    "level_adjustments (object mapping level name -> price)."
)


class OpenAIPatternValidator:
    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    def validate(self, pattern: DetectedPattern, image_path: str | None = None) -> ValidationResult:
        from openai import OpenAI

        client = OpenAI(api_key=self._api_key)
        features = {
            "pattern_type": pattern.pattern_type,
            "timeframe": pattern.timeframe.value,
            "status": pattern.status.value,
            "geometry_confidence": pattern.geometry_confidence,
            "levels": pattern.levels,
            "volume": pattern.volume,
            "pivots": [
                {"ts": p.ts.isoformat(), "price": p.price, "kind": p.kind} for p in pattern.pivots
            ],
        }
        content: list[dict[str, object]] = [
            {"type": "text", "text": f"Candidate features:\n{json.dumps(features, indent=2)}"}
        ]
        if image_path and Path(image_path).exists():
            b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
            content.append(
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
            )

        resp = client.chat.completions.create(  # type: ignore[call-overload]
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": content},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        raw = resp.choices[0].message.content or "{}"
        try:
            return ValidationResult.model_validate_json(raw)
        except Exception:  # noqa: BLE001 - tolerate a malformed LLM response
            logger.warning("LLM returned unparseable JSON; passing geometry through")
            return ValidationResult(
                is_valid=True,
                best_label=pattern.pattern_type,
                refined_confidence=pattern.geometry_confidence,
                rationale=raw[:500],
            )


def get_validator(settings: Settings | None = None) -> PatternValidator:
    s = settings or get_settings()
    if s.llm_active and s.openai_api_key:
        return OpenAIPatternValidator(api_key=s.openai_api_key, model=s.openai_model)
    return NullValidator()


def apply_validation(
    pattern: DetectedPattern, result: ValidationResult, max_frac: float = 0.02
) -> None:
    """Apply the LLM verdict to the pattern; clamp level nudges to +/- max_frac."""
    pattern.llm_is_valid = result.is_valid
    pattern.llm_label = result.best_label
    pattern.llm_rationale = result.rationale
    pattern.confidence = float(result.refined_confidence)
    for name, proposed in result.level_adjustments.items():
        old = pattern.levels.get(name)
        if old is None:
            continue
        bound = abs(old) * max_frac
        clamped = max(old - bound, min(old + bound, proposed))
        pattern.levels[name] = clamped
        if name == "breakout":
            pattern.entry = clamped
        elif name == "stop":
            pattern.stop = clamped
        elif name == "target":
            pattern.target = clamped
    if pattern.entry and pattern.stop and pattern.target and pattern.entry > pattern.stop:
        pattern.rr_ratio = (pattern.target - pattern.entry) / (pattern.entry - pattern.stop)


def content_hash(pattern: DetectedPattern, image_path: str | None, model: str) -> str:
    digest = hashlib.sha256()
    fingerprint = {
        "type": pattern.pattern_type,
        "tf": pattern.timeframe.value,
        "levels": {k: round(v, 4) for k, v in sorted(pattern.levels.items())},
        "model": model,
        "prompt": PROMPT_VERSION,
    }
    digest.update(json.dumps(fingerprint, sort_keys=True).encode())
    if image_path and Path(image_path).exists():
        digest.update(Path(image_path).read_bytes())
    return digest.hexdigest()


def validate_cached(
    validator: PatternValidator,
    pattern: DetectedPattern,
    image_path: str | None,
    model: str,
    db_path: str | None = None,
) -> ValidationResult:
    from ta_assistant.db.models import LlmCache
    from ta_assistant.db.session import session_scope

    key = content_hash(pattern, image_path, model)
    with session_scope(db_path) as session:
        row = session.get(LlmCache, key)
        if row is not None:
            return ValidationResult.model_validate_json(row.result_json)

    result = validator.validate(pattern, image_path)
    with session_scope(db_path) as session:
        if session.get(LlmCache, key) is None:
            session.add(
                LlmCache(content_hash=key, model=model, result_json=result.model_dump_json())
            )
    return result
