"""The ALPHA rubric is sourced from the editable alpha_rules.md and composed into ALPHA_SYSTEM,
with a content hash that busts the verdict cache when the rubric changes."""

from __future__ import annotations

import hashlib

from ta_assistant.analyst import prompts


def test_rules_loaded_and_comments_stripped() -> None:
    assert len(prompts.ALPHA_RULES) > 100
    assert "<!--" not in prompts.ALPHA_RULES  # human-only HTML comments are stripped
    # Key conventions survive into the rubric the LLM actually sees.
    rules = prompts.ALPHA_RULES.lower()
    assert "stage-2" in rules
    assert "200-week" in rules
    assert "risk:reward" in rules and "not a criterion" in rules


def test_alpha_system_is_rules_plus_json_contract() -> None:
    assert prompts.ALPHA_RULES in prompts.ALPHA_SYSTEM
    assert prompts.ALPHA_JSON_CONTRACT in prompts.ALPHA_SYSTEM
    assert '"is_alpha"' in prompts.ALPHA_SYSTEM and "strict JSON" in prompts.ALPHA_SYSTEM
    # The refresh prompt extends the same rubric.
    assert prompts.ALPHA_SYSTEM in prompts.ALPHA_REFRESH_SYSTEM


def test_rules_version_is_a_stable_hash_of_the_rubric() -> None:
    expected = hashlib.sha256(prompts.ALPHA_RULES.encode("utf-8")).hexdigest()[:12]
    assert prompts.ALPHA_RULES_VERSION == expected
    assert len(prompts.ALPHA_RULES_VERSION) == 12


def test_missing_file_falls_back_without_crashing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(prompts, "_ALPHA_RULES_PATH", tmp_path / "nope.md")
    assert prompts._load_alpha_rules() == prompts._ALPHA_RULES_FALLBACK
