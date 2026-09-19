"""COGNIFY ai-service — diagnosis prompt builder (Step 7).

The LLM receives ONLY the EvidencePack (observed evidence). This module
takes an ``EvidencePack`` (or its ``to_dict()`` mapping) and renders a
deterministic ``{system, user}`` prompt pair:

- The user message embeds the pack JSON verbatim (sorted keys, indent 2)
  plus the explicit candidate list and pack concept.
- The system message constrains the LLM to return ONLY strict JSON with
  the five diagnosis fields, grounded in the pack. It forbids invented
  IDs, database access, mastery math, hints, and adaptive decisions.

Determinism: same pack always yields the same prompt (JSON dumped with
``sort_keys=True``). No clock, no randomness, no I/O, no environment
reads, no DB access.
"""
from __future__ import annotations

import json
from typing import Any

from packages.evidence.models import EvidencePack

from .models import MAX_EXPLANATION_CHARS

DIAGNOSIS_JSON_SHAPE: str = (
    '{"concept_id": "<CONCEPT, e.g. C3>", '
    '"misconception_id": "<one of the candidates, e.g. C3-M01>", '
    '"confidence": <number 0-1>, '
    '"explanation": "<concise, 10-500 chars>", '
    '"evidence_refs": ["<grounded refs, 1-8 items>"]}'
)

SYSTEM_PROMPT_TEMPLATE: str = (
    "You are Cognify's root-cause diagnosis engine. "
    "You receive ONLY one EvidencePack JSON object (observed evidence for a "
    "single student submission). You have NO database access, NO filesystem, "
    "NO tools, and NO other student data.\n"
    "Task: pick the single most likely misconception that explains the observed failure.\n"
    "Rules:\n"
    "1. misconception_id MUST be exactly one of the pack's "
    "misconception_candidates. Never invent, alter, or abbreviate an ID.\n"
    "2. concept_id MUST equal the pack's concept_id exactly.\n"
    "3. confidence MUST be a number in [0, 1].\n"
    "4. explanation MUST be concise "
    f"(10-{MAX_EXPLANATION_CHARS} chars) and describe WHY the evidence points "
    "to this misconception.\n"
    "5. evidence_refs MUST list 1-8 short references to observable evidence, "
    "using ONLY these forms: 'code', 'execution_status', 'stdout', 'stderr', "
    "'expected_output', 'actual_output', 'concept_history', 'recent_events', "
    "'failed_test:<test_id>', 'candidate:<MISCONCEPTION_ID>', "
    "'history:<MISCONCEPTION_ID>', 'recurring:<MISCONCEPTION_ID>'. "
    "Every <test_id> / <MISCONCEPTION_ID> you reference MUST appear in the pack.\n"
    "6. Return ONLY a single JSON object with EXACTLY these keys: "
    "concept_id, misconception_id, confidence, explanation, evidence_refs. "
    "No markdown, no commentary, no extra keys.\n"
    "7. Do NOT update any database, do NOT calculate mastery, do NOT generate "
    "hints, and do NOT make adaptive/roadmap decisions. Diagnosis only."
)


def _pack_to_dict(pack: EvidencePack | dict[str, Any]) -> dict[str, Any]:
    if isinstance(pack, EvidencePack):
        return pack.to_dict()
    if isinstance(pack, dict):
        # Re-validate through the pack model so malformed dicts fail fast
        # with the pack's own strict errors (single source of truth).
        return EvidencePack.from_dict(pack).to_dict()
    raise TypeError(
        f"pack must be EvidencePack or dict, got {type(pack).__name__}."
    )


def build_diagnosis_prompt(
    pack: EvidencePack | dict[str, Any],
) -> dict[str, str]:
    """Build the deterministic ``{system, user}`` prompt for a pack.

    Args:
        pack: EvidencePack (or its dict form). Only this evidence is
            embedded; no database rows, secrets, or extra history are added.

    Returns:
        ``{"system": ..., "user": ...}`` — both plain strings.
    """
    pack_dict = _pack_to_dict(pack)
    concept_id = pack_dict["concept_id"]
    candidates = [c["misconception_id"] for c in pack_dict["misconception_candidates"]]
    failed = pack_dict.get("failed_test_id")
    pack_json = json.dumps(pack_dict, sort_keys=True, indent=2, ensure_ascii=False)
    user = (
        "Diagnose the root-cause misconception for this EvidencePack.\n"
        f"Pack concept: {concept_id}\n"
        f"Candidate misconception IDs (choose exactly one): {', '.join(candidates)}\n"
        f"Decisive failed test: {failed}\n"
        "Respond with ONLY this JSON shape (exactly these keys):\n"
        f"{DIAGNOSIS_JSON_SHAPE}\n"
        "EvidencePack JSON:\n"
        f"{pack_json}"
    )
    return {"system": SYSTEM_PROMPT_TEMPLATE, "user": user}


def build_diagnosis_messages(
    pack: EvidencePack | dict[str, Any],
) -> list[dict[str, str]]:
    """Chat-style ``[{role, content}]`` view of :func:`build_diagnosis_prompt`."""
    prompt = build_diagnosis_prompt(pack)
    return [
        {"role": "system", "content": prompt["system"]},
        {"role": "user", "content": prompt["user"]},
    ]


__all__ = [
    "DIAGNOSIS_JSON_SHAPE",
    "SYSTEM_PROMPT_TEMPLATE",
    "build_diagnosis_messages",
    "build_diagnosis_prompt",
]
