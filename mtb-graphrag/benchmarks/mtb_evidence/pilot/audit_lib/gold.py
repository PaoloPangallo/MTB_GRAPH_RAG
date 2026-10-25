"""Lettura del gold pilota in strutture congelate.

Il gold e' di sola lettura per costruzione: le dataclass sono `frozen`, e nessuna
funzione di questo package riscrive il file di input. Le divergenze rilevate
dall'audit diventano proposte in `proposed_gold_amendments.jsonl`, mai modifiche.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence


class GoldParseError(ValueError):
    """Il file gold non e' leggibile o non ha la forma attesa."""


@dataclass(frozen=True)
class GoldClaim:
    claim_id: str
    case_id: str
    subject: str
    relation: str
    object: str
    disease: str
    direction: str
    mandatory_qualifiers: str
    pmid: str
    nct_id: str
    documentary_status: str
    applicability: str
    gold_rationale: str
    prohibited_overclaim: str
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True)
class GoldSource:
    source_record_id: str
    case_id: str
    source_type: str
    source_id: str
    title: str
    url_or_path: str
    role: str
    relevant_population_or_rule: str
    review_status: str
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True)
class GoldCase:
    case_id: str
    pilot_id: str
    category: str
    annotation_status: str
    case_context: str
    question: str
    gene: str
    variant: str
    disease: str
    required_context: str
    expected_therapies: tuple[str, ...]
    expected_pmids: tuple[str, ...]
    expected_nct_ids: tuple[str, ...]
    required_tools: tuple[str, ...]
    optional_tools: tuple[str, ...]
    unnecessary_tools: tuple[str, ...]
    conditional_plan: str
    expected_applicability: str
    expected_abstention: bool
    expected_human_review: bool
    report_requirements: str
    claims: tuple[GoldClaim, ...]
    sources: tuple[GoldSource, ...]
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key, "")
    return "" if value is None else str(value)


def _tuple(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = payload.get(key) or []
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


def _flag(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key, False)
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"true", "1", "yes", "si"}


def _parse_claim(payload: Mapping[str, Any], case_id: str) -> GoldClaim:
    return GoldClaim(
        claim_id=_text(payload, "claim_id"),
        case_id=_text(payload, "case_id") or case_id,
        subject=_text(payload, "subject"),
        relation=_text(payload, "relation"),
        object=_text(payload, "object"),
        disease=_text(payload, "disease"),
        direction=_text(payload, "direction"),
        mandatory_qualifiers=_text(payload, "mandatory_qualifiers"),
        pmid=_text(payload, "pmid"),
        nct_id=_text(payload, "nct_id"),
        documentary_status=_text(payload, "documentary_status"),
        applicability=_text(payload, "applicability"),
        gold_rationale=_text(payload, "gold_rationale"),
        prohibited_overclaim=_text(payload, "prohibited_overclaim"),
        raw=dict(payload),
    )


def _parse_source(payload: Mapping[str, Any], case_id: str) -> GoldSource:
    return GoldSource(
        source_record_id=_text(payload, "source_record_id"),
        case_id=_text(payload, "case_id") or case_id,
        source_type=_text(payload, "source_type"),
        source_id=_text(payload, "source_id"),
        title=_text(payload, "title"),
        url_or_path=_text(payload, "url_or_path"),
        role=_text(payload, "role"),
        relevant_population_or_rule=_text(payload, "relevant_population_or_rule"),
        review_status=_text(payload, "review_status"),
        raw=dict(payload),
    )


def parse_case(payload: Mapping[str, Any]) -> GoldCase:
    case_id = _text(payload, "case_id")
    if not case_id:
        raise GoldParseError("record senza case_id")
    return GoldCase(
        case_id=case_id,
        pilot_id=_text(payload, "pilot_id"),
        category=_text(payload, "category"),
        annotation_status=_text(payload, "annotation_status"),
        case_context=_text(payload, "case_context"),
        question=_text(payload, "question"),
        gene=_text(payload, "gene"),
        variant=_text(payload, "variant"),
        disease=_text(payload, "disease"),
        required_context=_text(payload, "required_context"),
        expected_therapies=_tuple(payload, "expected_therapies"),
        expected_pmids=_tuple(payload, "expected_pmids"),
        expected_nct_ids=_tuple(payload, "expected_nct_ids"),
        required_tools=_tuple(payload, "required_tools"),
        optional_tools=_tuple(payload, "optional_tools"),
        unnecessary_tools=_tuple(payload, "unnecessary_tools"),
        conditional_plan=_text(payload, "conditional_plan"),
        expected_applicability=_text(payload, "expected_applicability"),
        expected_abstention=_flag(payload, "expected_abstention"),
        expected_human_review=_flag(payload, "expected_human_review"),
        report_requirements=_text(payload, "report_requirements"),
        claims=tuple(
            _parse_claim(item, case_id) for item in (payload.get("claims") or [])
        ),
        sources=tuple(
            _parse_source(item, case_id) for item in (payload.get("sources") or [])
        ),
        raw=dict(payload),
    )


def parse_gold_lines(lines: Sequence[str]) -> tuple[GoldCase, ...]:
    """Parsa righe JSONL, ignorando quelle vuote e riportando il numero di riga."""
    cases: list[GoldCase] = []
    for number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as error:
            raise GoldParseError(f"riga {number}: JSON non valido ({error.msg})") from error
        if not isinstance(payload, dict):
            raise GoldParseError(f"riga {number}: atteso un oggetto JSON")
        cases.append(parse_case(payload))
    if not cases:
        raise GoldParseError("nessun caso trovato nel file gold")
    seen: set[str] = set()
    for case in cases:
        if case.case_id in seen:
            raise GoldParseError(f"case_id duplicato: {case.case_id}")
        seen.add(case.case_id)
    return tuple(cases)


def load_gold(path: Path) -> tuple[GoldCase, ...]:
    target = Path(path)
    if not target.is_file():
        raise GoldParseError(f"file gold non trovato: {target}")
    return parse_gold_lines(target.read_text(encoding="utf-8").splitlines())
