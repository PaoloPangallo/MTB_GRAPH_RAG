"""Bounded, provenance-separated Reader context and optional retry expansion."""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from typing import Any, Callable

from ..experimental import SourceUnitSelectionInput, select

EXPANDABLE_ABSTENTIONS = frozenset(
    {"NO_RELEVANT_EVIDENCE", "INSUFFICIENT_RELATION", "MISSING_REQUIRED_ANCHOR"}
)
_ANAPHORA_CUES = re.compile(
    r"\b(?:such\s+(?:tumou?rs?|patients?|mutations?|variants?|cells?|cases?|findings?|responses?)|"
    r"these\s+(?:patients?|tumou?rs?|mutations?|variants?|cases?|findings?)|"
    r"this\s+(?:treatment|therapy|drug|alteration|mutation|variant|finding|response|regimen))\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ContextPolicy:
    enabled: bool = False
    adjacent_context_enabled: bool = False
    initial_top_k: int = 5
    expanded_top_k: int = 10
    max_context_units: int = 2
    max_context_chars: int = 2400
    version: str = "bounded-reader-context/2.0"

    def __post_init__(self) -> None:
        if (
            type(self.initial_top_k) is not int
            or type(self.expanded_top_k) is not int
            or not 1 <= self.initial_top_k <= self.expanded_top_k <= 20
        ):
            raise ValueError(
                "Reader context requires 1 <= initial K <= expanded K <= 20"
            )
        if (type(self.max_context_units) is not int or not 0 <= self.max_context_units <= 2
                or type(self.max_context_chars) is not int or not 0 <= self.max_context_chars <= 4000):
            raise ValueError("Reader context is bounded to at most 2 units and 4000 characters")

    @classmethod
    def from_environment(cls) -> ContextPolicy:
        return cls(
            enabled=os.getenv("RESEARCH_PIPELINE_EXPAND_READER_CONTEXT", "")
            .strip()
            .lower()
            in {"1", "true", "yes", "on"},
            initial_top_k=int(os.getenv("RESEARCH_PIPELINE_SOURCEUNIT_TOP_K", "5")),
            expanded_top_k=int(
                os.getenv("RESEARCH_PIPELINE_EXPANDED_SOURCEUNIT_TOP_K", "10")
            ),
            adjacent_context_enabled=os.getenv(
                "RESEARCH_PIPELINE_READER_ADJACENT_CONTEXT", "1"
            ).strip().lower() not in {"0", "false", "no", "off"},
            max_context_units=int(os.getenv("RESEARCH_PIPELINE_READER_CONTEXT_MAX_UNITS", "2")),
            max_context_chars=int(os.getenv("RESEARCH_PIPELINE_READER_CONTEXT_MAX_CHARS", "2400")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReaderContextResult:
    call: dict[str, Any]
    paper: dict[str, Any]
    units: list[dict[str, Any]]


def _same_context_scope(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.get("document_id") != right.get("document_id"):
        return False
    if any(left.get(key) != right.get(key) for key in ("section", "subsection")):
        return False
    unit_type = left.get("unit_type")
    if unit_type != right.get("unit_type"):
        return False
    if unit_type in {"FULLTEXT_SENTENCE", "ABSTRACT_SENTENCE"}:
        return left.get("paragraph_index") == right.get("paragraph_index")
    return unit_type in {"FULLTEXT_PARAGRAPH", "ABSTRACT"}


def _position(unit: dict[str, Any]) -> tuple[int, int]:
    paragraph = unit.get("paragraph_index")
    sentence = unit.get("sentence_index")
    return (paragraph if isinstance(paragraph, int) else -1,
            sentence if isinstance(sentence, int) else -1)


def _adjacent_context_units(
    evidence_units: list[dict[str, Any]],
    document_units: list[dict[str, Any]],
    paper: dict[str, Any],
    policy: ContextPolicy,
) -> list[dict[str, Any]]:
    """Return at most the immediate same-scope neighbours as context-only copies."""
    if not policy.adjacent_context_enabled or not policy.max_context_units or not policy.max_context_chars:
        return []
    if not any(_ANAPHORA_CUES.search(str(unit.get("text") or "")) for unit in evidence_units):
        return []
    document_id = paper.get("document_id")
    if not isinstance(document_id, str):
        return []
    by_id = {
        str(unit.get("source_unit_id")): unit for unit in document_units
        if unit.get("document_id") == document_id
        and isinstance(unit.get("source_unit_id"), str)
        and isinstance(unit.get("text"), str) and unit.get("text").strip()
    }
    evidence_ids_set = {str(unit.get("source_unit_id")) for unit in evidence_units}
    candidates: dict[str, tuple[int, int, dict[str, Any], str]] = {}
    for evidence in evidence_units:
        if not _ANAPHORA_CUES.search(str(evidence.get("text") or "")):
            continue
        if evidence.get("document_id") != document_id:
            continue
        for possible in by_id.values():
            uid = str(possible["source_unit_id"])
            if uid in evidence_ids_set or not _same_context_scope(evidence, possible):
                continue
            before = _position(possible) < _position(evidence)
            after = _position(possible) > _position(evidence)
            if not (before or after):
                continue
            # Only immediate neighbors are eligible; gaps never bridge a missing unit.
            sentence_level = evidence.get("unit_type") in {"FULLTEXT_SENTENCE", "ABSTRACT_SENTENCE"}
            distance = (
                abs(_position(possible)[1] - _position(evidence)[1])
                if sentence_level else abs(_position(possible)[0] - _position(evidence)[0])
            )
            if distance != 1:
                continue
            direction = "PREVIOUS" if before else "NEXT"
            rank = 0 if before else 1
            previous = candidates.get(uid)
            candidate = (rank, distance, possible, direction)
            if previous is None or candidate[:2] < previous[:2]:
                candidates[uid] = candidate
    ordered = sorted(candidates.values(), key=lambda item: (_position(item[2]), item[0]))
    result: list[dict[str, Any]] = []
    chars = 0
    evidence_ids = [unit.get("source_unit_id") for unit in evidence_units]
    for _rank, _distance, unit, direction in ordered:
        text = str(unit.get("text") or "")
        if len(result) >= policy.max_context_units or chars + len(text) > policy.max_context_chars:
            continue
        result.append({
            **unit,
            "reader_role": "CONTEXT",
            "context_relation": f"ADJACENT_{direction}",
            "context_for_source_unit_ids": [
                source_id for source_id in evidence_ids
                if source_id and any(
                    evidence.get("source_unit_id") == source_id
                    and _ANAPHORA_CUES.search(str(evidence.get("text") or ""))
                    and _same_context_scope(evidence, unit)
                    and abs(
                        (_position(unit)[1] - _position(evidence)[1])
                        if evidence.get("unit_type") in {"FULLTEXT_SENTENCE", "ABSTRACT_SENTENCE"}
                        else (_position(unit)[0] - _position(evidence)[0])
                    ) == 1
                    for evidence in evidence_units
                )
            ],
        })
        chars += len(text)
    return result


def _reader_units(
    evidence_units: list[dict[str, Any]], document_units: list[dict[str, Any]],
    paper: dict[str, Any], policy: ContextPolicy,
) -> list[dict[str, Any]]:
    evidence = [{**unit, "reader_role": "EVIDENCE"} for unit in evidence_units]
    context = _adjacent_context_units(evidence_units, document_units, paper, policy)
    combined = evidence + context
    from ..retrieval.document_plan import focused_enabled
    limit = os.getenv('RESEARCH_PIPELINE_MAX_READER_SOURCE_CHARACTERS', '').strip()
    if focused_enabled() and limit:
        from ..retrieval.reader_budget import pack_reader_units
        selected, _ = pack_reader_units(tuple(u['source_unit_id'] for u in combined),
            {u['source_unit_id']: u for u in combined}, int(limit))
        combined = [u for u in combined if u['source_unit_id'] in selected]
        if not any(u.get('reader_role') == 'EVIDENCE' for u in combined):
            from ..live_providers import LiveStageFailed
            raise LiveStageFailed('stage_9_paper_context_enricher', 'CALL_BUDGET_EXCEEDED',
                                  'READER_TEXT_BUDGET_EXCEEDED: no complete evidence unit fits')
    return combined


def _context_metadata(evidence_units, document_units, paper, policy, delivered) -> dict[str, Any]:
    contexts = [u for u in delivered if u.get('reader_role') == 'CONTEXT']
    delivered_ids = {u['source_unit_id'] for u in delivered}
    return {'evidence_source_unit_ids': [u['source_unit_id'] for u in delivered if u.get('reader_role') != 'CONTEXT'],
            'context_source_unit_ids': [u['source_unit_id'] for u in contexts],
            'context_characters': sum(len(u.get('text') or '') for u in contexts),
            'reader_source_characters': sum(len(u.get('text') or '') for u in delivered),
            'context_relations': [{'source_unit_id': u['source_unit_id'],
                                  'context_relation': u.get('context_relation'),
                                  'context_for_source_unit_ids': u.get('context_for_source_unit_ids', [])} for u in contexts],
            'deferred_context_source_unit_ids': [u['source_unit_id'] for u in
                _adjacent_context_units(evidence_units, document_units, paper, policy)
                if u['source_unit_id'] not in delivered_ids],
            'anaphora_triggered': any(_ANAPHORA_CUES.search(str(u.get('text') or '')) for u in evidence_units)}


def _attempt(call: dict[str, Any], units: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "source_unit_ids": [unit["source_unit_id"] for unit in units
                            if unit.get("reader_role") != "CONTEXT"],
        "context_source_unit_ids": [unit["source_unit_id"] for unit in units
                                    if unit.get("reader_role") == "CONTEXT"],
        "transport_result": call.get("transport_result"),
        "decision": (call.get("enrichment") or {}).get("decision"),
        "abstain_reason": (call.get("enrichment") or {}).get("abstain_reason"),
        **{
            key: call.get(key)
            for key in (
                "model",
                "prompt_version",
                "model_call_count",
                "reader_request_hash",
                "input_tokens",
                "output_tokens",
                "latency_ms",
            )
        },
    }


def _combine(first: dict[str, Any], last: dict[str, Any]) -> dict[str, Any]:
    result = dict(last)
    result["token_usage_complete"] = all(item.get("token_usage_complete", not item.get("retry_count")) for item in (first, last))
    result["model_call_count"] = first.get("model_call_count", 1) + last.get(
        "model_call_count", 1
    )
    for key in ("input_tokens", "output_tokens", "latency_ms", "retry_count"):
        values = (first.get(key), last.get(key))
        result[key] = (
            sum(values)
            if all(isinstance(value, (int, float)) for value in values)
            else None
        )
    return result


def read_with_context_policy(
    reader: Callable[..., dict[str, Any]],
    budget: Any,
    case_id: str,
    case_context: dict[str, Any],
    candidate: dict[str, Any],
    requested_drug: str,
    paper: dict[str, Any],
    initial_units: list[dict[str, Any]],
    document_units: list[dict[str, Any]],
    policy: ContextPolicy,
    *,
    selector_fn: Callable[..., Any] | None = None,
) -> ReaderContextResult:
    def invoke(units: list[dict[str, Any]]) -> dict[str, Any]:
        return reader(
            budget,
            case_id,
            candidate["candidate_id"],
            paper["document_id"],
            case_context,
            candidate,
            requested_drug,
            units,
        )

    first_units = _reader_units(initial_units, document_units, paper, policy)
    first = invoke(first_units)
    context_audit = {
        "policy_version": policy.version,
        "evidence_source_unit_ids": [unit["source_unit_id"] for unit in initial_units],
        "context_source_unit_ids": [unit["source_unit_id"] for unit in first_units
                                    if unit.get("reader_role") == "CONTEXT"],
        "context_relations": [
            {"source_unit_id": unit["source_unit_id"],
             "context_relation": unit.get("context_relation"),
             "context_for_source_unit_ids": unit.get("context_for_source_unit_ids", [])}
            for unit in first_units if unit.get("reader_role") == "CONTEXT"
        ],
        "context_characters": sum(len(unit.get("text") or "") for unit in first_units
                                   if unit.get("reader_role") == "CONTEXT"),
        "anaphora_triggered": any(
            _ANAPHORA_CUES.search(str(unit.get("text") or "")) for unit in initial_units
        ),
        "reader_source_characters": sum(len(u.get('text') or '') for u in first_units),
        "deferred_context_source_unit_ids": [u['source_unit_id'] for u in
            _adjacent_context_units(initial_units, document_units, paper, policy)
            if u['source_unit_id'] not in {x['source_unit_id'] for x in first_units}],
    }
    context_audit.update(_context_metadata(initial_units, document_units, paper, policy, first_units))
    first["reader_context"] = context_audit
    reader_paper = {**paper, "reader_context": context_audit}
    observation = first.get("enrichment") or {}
    can_expand = (
        policy.enabled
        and first.get("transport_result") == "V3_TRANSPORT_VALID"
        and observation.get("decision") == "ABSTAIN"
        and observation.get("abstain_reason") in EXPANDABLE_ABSTENTIONS
    )
    if not can_expand:
        return ReaderContextResult(first, reader_paper, first_units)
    audit: dict[str, Any] = {
        "policy": policy.to_dict(),
        "attempts": [_attempt(first, first_units)],
        "expanded": False,
    }
    first = {**first, "context_expansion": audit}
    if getattr(budget, "used", 0) >= getattr(budget, "maximum", 0):
        audit["reason"] = "CONTEXT_EXPANSION_BUDGET_EXHAUSTED"
        return ReaderContextResult(first, reader_paper, first_units)
    eligible_units = [
        unit
        for unit in document_units
        if unit.get("document_id") == paper["document_id"] and unit.get("text")
    ]
    selection_input = SourceUnitSelectionInput.from_candidate(
        candidate, paper["document_id"], eligible_units
    )
    selection = (selector_fn or select)(selection_input, top_k=policy.expanded_top_k)
    initial_ids = [unit["source_unit_id"] for unit in initial_units]
    expanded_ids = list(
        dict.fromkeys([*initial_ids, *selection.selected_source_unit_ids])
    )[: policy.expanded_top_k]
    available = {unit["source_unit_id"]: unit for unit in eligible_units}
    expanded_units = [
        available[unit_id] for unit_id in expanded_ids if unit_id in available
    ]
    if not set(expanded_ids) - set(initial_ids):
        audit["reason"] = "NO_ADDITIONAL_COMPATIBLE_SOURCE_UNITS"
        return ReaderContextResult(first, reader_paper, first_units)
    audit["expanded"] = True
    budget_before = getattr(budget, "used", 0)
    try:
        expanded_reader_units = _reader_units(
            expanded_units, document_units, {**paper, "resolved_source_unit_ids": expanded_ids}, policy
        )
        actual_expanded_ids = [u['source_unit_id'] for u in expanded_reader_units if u.get('reader_role') != 'CONTEXT']
        if not set(actual_expanded_ids) - set(initial_ids):
            audit['expanded'] = False
            audit['reason'] = 'NO_ADDITIONAL_UNITS_WITHIN_READER_TEXT_BUDGET'
            return ReaderContextResult(first, reader_paper, first_units)
        expanded_ids = actual_expanded_ids
        last = invoke(expanded_reader_units)
    except Exception as error:
        # A failed transport may have no response. Keep the completed first
        # attempt and budget-observed invocation count without inventing usage.
        failed_call = getattr(error, "call_result", None)
        if not isinstance(failed_call, dict):
            failed_call = {
                "model_call_count": max(
                    0, getattr(budget, "used", budget_before) - budget_before
                ),
                "transport_result": "CONTEXT_EXPANSION_FAILED",
            }
        audit["failure_reason"] = getattr(error, "reason_code", "LIVE_STAGE_FAILED")
        audit["attempts"].append(_attempt(failed_call, expanded_reader_units))
        setattr(
            error,
            "call_result",
            {**_combine(first, failed_call), "context_expansion": audit},
        )
        raise
    audit["attempts"].append(_attempt(last, expanded_reader_units))
    expanded_paper = {
        **paper,
        "resolved_source_unit_ids": expanded_ids,
        "context_expansion": audit,
        "reader_context": context_audit,
        "expanded_selector": selection.to_dict(ranking_limit=None),
    }
    context_audit = {**context_audit, **_context_metadata(expanded_units, document_units,
        paper, policy, expanded_reader_units)}
    expanded_paper['reader_context'] = context_audit
    last = {**last, "reader_context": context_audit}
    return ReaderContextResult(
        {**_combine(first, last), "context_expansion": audit},
        expanded_paper,
        expanded_reader_units,
    )
