"""Vision CONSENSUS over detected patterns.

The geometry engine over-generates candidates and dedups them into distinct structures
(one representative per cluster). This module asks an analyst — OpenAI vision by default,
a deterministic NullConsensus with no key — to look at ONE timeframe's chart and the list
of candidate structures and decide the *big picture*: which is the dominant, currently
tradeable LONG structure (`primary`), an optional nested continuation (`secondary`), an
optional bearish ceiling (`cap`, context only — we never short), relabelling each to its
human-recognizable classical name (e.g. cup geometry the eye reads as an ascending
triangle). It scores and narrates but never moves the engine's exact levels. Cached by
content hash so repeat runs are free.
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
PROMPT_VERSION = "consensus-v2"

_ROLES = {"primary", "secondary", "cap", "considered"}


class PatternVerdict(BaseModel):
    id: str
    is_valid: bool = True
    role: str = "considered"  # primary | secondary | cap | considered
    label: str | None = None  # human-recognizable classical name
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    rationale: str = ""


class ConsensusResult(BaseModel):
    timeframe: str = ""
    read: str = ""  # one-paragraph plain-English read of the chart's big picture
    verdicts: list[PatternVerdict] = Field(default_factory=list)
    source: str = "llm"  # "llm" | "deterministic" — only real LLM results are cached


class ConsensusValidator(Protocol):
    def consensus(
        self, timeframe: str, image_path: str | None, candidates: list[DetectedPattern]
    ) -> ConsensusResult: ...


def _deterministic(timeframe: str, candidates: list[DetectedPattern]) -> ConsensusResult:
    """Keep the engine's (deterministic) roles; used when the LLM is off or fails."""
    return ConsensusResult(
        timeframe=timeframe,
        read="",
        source="deterministic",
        verdicts=[
            PatternVerdict(
                id=c.id,
                is_valid=c.role != "considered",
                role=c.role,
                label=c.pattern_type,
                confidence=c.confidence,
                rationale="(LLM disabled) deterministic geometry consensus.",
            )
            for c in candidates
        ],
    )


class NullConsensus:
    """Pass the deterministic geometry consensus through unchanged (no key / tests)."""

    def consensus(
        self, timeframe: str, image_path: str | None, candidates: list[DetectedPattern]
    ) -> ConsensusResult:
        return _deterministic(timeframe, candidates)


_SYSTEM = (
    "You are a classical technical-analysis chartist in the Brandt/Minervini tradition, "
    "LONG side only — you never recommend shorting. You are given ONE timeframe's chart "
    "image and a list of CANDIDATE structures a geometry engine already found and "
    "de-duplicated, each with an id, the engine's label, exact levels (breakout/target/"
    "stop), and status. Decide the chart's DOMINANT, currently-actionable big picture. "
    "Respond ONLY as JSON: {\"read\": str, \"verdicts\": [{\"id\": str, \"is_valid\": "
    "bool, \"role\": one of 'primary'|'secondary'|'cap'|'considered', \"label\": str, "
    "\"confidence\": 0..1, \"rationale\": str}]}. Rules: at most ONE 'primary' (the "
    "single dominant tradeable LONG structure); at most one 'secondary' (a nested "
    "continuation such as a flag, or a larger enclosing base); at most one 'cap' (a "
    "bearish structure that caps upside — context only). Everything else is 'considered'. "
    "Set 'label' to the human-recognizable classical name even when it differs from the "
    "engine's label (e.g. relabel a cup as an 'ascending triangle' or an 'inverse head "
    "and shoulders' if that is what the chart shows). This is a long-side decision-support "
    "tool: whenever a reasonable bullish thesis exists (a continuation, a reversal base, or "
    "a consolidation/triangle breakout), pick the most plausible one as 'primary', and use "
    "'cap' for a bearish structure that would threaten its target — surfacing the interlock "
    "between them. Reserve all-'considered' for when there is genuinely no long thesis (e.g. "
    "a clean sustained downtrend). Only use ids from the provided candidates; never invent "
    "levels."
)


def _candidate_payload(candidates: list[DetectedPattern]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for c in candidates:
        out.append(
            {
                "id": c.id,
                "engine_label": c.pattern_type,
                "direction": c.direction,
                "status": c.status.value,
                "breakout": c.entry,
                "target": c.target,
                "stop": c.stop,
                "geometry_confidence": round(c.geometry_confidence, 2),
                "pivots": [round(p.price, 2) for p in c.pivots],
            }
        )
    return out


class OpenAIConsensus:
    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    def consensus(
        self, timeframe: str, image_path: str | None, candidates: list[DetectedPattern]
    ) -> ConsensusResult:
        from openai import OpenAI

        client = OpenAI(api_key=self._api_key)
        payload = {"timeframe": timeframe, "candidates": _candidate_payload(candidates)}
        content: list[dict[str, object]] = [
            {"type": "text", "text": f"Chart context:\n{json.dumps(payload, indent=2)}"}
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
            result = ConsensusResult.model_validate_json(raw)
            result.timeframe = timeframe
            valid_ids = {c.id for c in candidates}
            result.verdicts = [
                v for v in result.verdicts if v.id in valid_ids and v.role in _ROLES
            ]
            return result
        except Exception:  # noqa: BLE001 - tolerate a malformed LLM response
            logger.warning("LLM consensus unparseable; falling back to deterministic roles")
            return _deterministic(timeframe, candidates)


def get_validator(settings: Settings | None = None) -> ConsensusValidator:
    s = settings or get_settings()
    if s.llm_active and s.openai_api_key:
        return OpenAIConsensus(api_key=s.openai_api_key, model=s.openai_model)
    return NullConsensus()


def apply_consensus(patterns: list[DetectedPattern], result: ConsensusResult) -> None:
    """Apply the consensus verdicts to the candidate patterns (roles/label/confidence/
    rationale). Enforces at most one 'primary' (extra primaries demote to secondary, then
    considered). Levels are never touched — the engine owns those."""
    by_id = {p.id: p for p in patterns}
    seen_primary = False
    # apply in the verdict order, strongest-confidence first for deterministic demotion
    for v in sorted(result.verdicts, key=lambda x: x.confidence, reverse=True):
        p = by_id.get(v.id)
        if p is None:
            continue
        role = v.role if v.role in _ROLES else "considered"
        if not v.is_valid:
            role = "considered"
        if role == "primary":
            role = "primary" if not seen_primary else "secondary"
            seen_primary = seen_primary or role == "primary"
        p.role = role
        if v.label:
            p.label_override = v.label
        p.confidence = float(v.confidence)
        p.llm_is_valid = v.is_valid
        p.llm_label = v.label
        p.llm_rationale = v.rationale


def content_hash(
    timeframe: str, candidates: list[DetectedPattern], image_path: str | None, model: str
) -> str:
    digest = hashlib.sha256()
    fingerprint = {
        "tf": timeframe,
        "model": model,
        "prompt": PROMPT_VERSION,
        "candidates": [
            {
                "type": c.pattern_type,
                "dir": c.direction,
                "levels": {k: round(v, 4) for k, v in sorted(c.levels.items())},
            }
            for c in candidates
        ],
    }
    digest.update(json.dumps(fingerprint, sort_keys=True).encode())
    if image_path and Path(image_path).exists():
        digest.update(Path(image_path).read_bytes())
    return digest.hexdigest()


def consensus_cached(
    validator: ConsensusValidator,
    timeframe: str,
    image_path: str | None,
    candidates: list[DetectedPattern],
    model: str,
    db_path: str | None = None,
) -> ConsensusResult:
    from ta_assistant.db.models import LlmCache
    from ta_assistant.db.session import session_scope

    key = content_hash(timeframe, candidates, image_path, model)
    with session_scope(db_path) as session:
        row = session.get(LlmCache, key)
        if row is not None:
            return ConsensusResult.model_validate_json(row.result_json)

    result = validator.consensus(timeframe, image_path, candidates)
    if result.source != "llm":  # never cache deterministic/fallback results
        return result
    with session_scope(db_path) as session:
        if session.get(LlmCache, key) is None:
            session.add(
                LlmCache(content_hash=key, model=model, result_json=result.model_dump_json())
            )
    return result
