"""Costruzione e lettura del clinical gold.

Il clinical gold descrive **cio' che dovrebbe essere ricostruito** secondo fonti
primarie, registri dei trial e annotazione umana. Non dipende dallo snapshot Neo4j e
non viene mai riscritto sulla base delle predizioni: se una fonte non e' nel grafo,
il clinical gold resta com'e' e a cambiare e' la copertura misurata.

Le proposte di emendamento prodotte dall'audit (`proposed_gold_amendments.jsonl`)
**non** vengono applicate qui. Sono proposte per un revisore umano; applicarle
automaticamente significherebbe lasciare che lo stato del grafo riscriva la verita'
clinica, che e' esattamente l'inversione che questa separazione esiste per impedire.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .contracts import ClinicalGoldCase, ClinicalGoldClaim

# Il pilota e' stato annotato una volta sola: la seconda revisione e' ancora aperta.
DEFAULT_ANNOTATORS = ("annotatore_1",)
DEFAULT_ADJUDICATION = "pending_second_review"


class ClinicalGoldError(ValueError):
    """Il clinical gold non e' leggibile o non ha la forma attesa."""


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


def _claim_from_pilot(payload: Mapping[str, Any], case_id: str) -> ClinicalGoldClaim:
    return ClinicalGoldClaim(
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
        rationale=_text(payload, "gold_rationale") or _text(payload, "rationale"),
        prohibited_overclaim=_text(payload, "prohibited_overclaim"),
    )


def _qualifiers_from_claims(claims: Sequence[ClinicalGoldClaim]) -> tuple[str, ...]:
    """I qualificatori obbligatori dichiarati dalle claim, deduplicati."""
    qualifiers: list[str] = []
    for claim in claims:
        for fragment in claim.mandatory_qualifiers.split(";"):
            cleaned = fragment.strip()
            if cleaned and cleaned not in qualifiers:
                qualifiers.append(cleaned)
    return tuple(qualifiers)


def from_pilot_record(payload: Mapping[str, Any]) -> ClinicalGoldCase:
    """Converte un record del pilota v1 in un `ClinicalGoldCase`.

    La conversione e' una riorganizzazione, non una revisione: nessun valore viene
    modificato, aggiunto o rimosso.
    """
    case_id = _text(payload, "case_id")
    if not case_id:
        raise ClinicalGoldError("record senza case_id")

    claims = tuple(
        _claim_from_pilot(item, case_id) for item in (payload.get("claims") or [])
    )
    sources = tuple(dict(item) for item in (payload.get("sources") or []))

    entities: list[str] = []
    for value in (_text(payload, "gene"), _text(payload, "variant"), _text(payload, "disease")):
        if value and value not in entities:
            entities.append(value)

    return ClinicalGoldCase(
        case_id=case_id,
        question=_text(payload, "question"),
        case_context=_text(payload, "case_context"),
        category=_text(payload, "category"),
        gene=_text(payload, "gene"),
        variant=_text(payload, "variant"),
        disease=_text(payload, "disease"),
        required_context=_text(payload, "required_context"),
        expected_entities=tuple(entities),
        expected_claims=claims,
        expected_sources=tuple(str(source.get("source_id", "")) for source in sources),
        expected_qualifiers=_qualifiers_from_claims(claims),
        expected_documentary_status=tuple(
            claim.documentary_status for claim in claims if claim.documentary_status
        ),
        expected_applicability=_text(payload, "expected_applicability"),
        expected_abstention=_flag(payload, "expected_abstention"),
        expected_human_review=_flag(payload, "expected_human_review"),
        expected_therapies=_tuple(payload, "expected_therapies"),
        expected_pmids=_tuple(payload, "expected_pmids"),
        expected_nct_ids=_tuple(payload, "expected_nct_ids"),
        required_tools=_tuple(payload, "required_tools"),
        optional_tools=_tuple(payload, "optional_tools"),
        unnecessary_tools=_tuple(payload, "unnecessary_tools"),
        gold_sources=sources,
        annotation_status=_text(payload, "annotation_status"),
        annotators=DEFAULT_ANNOTATORS,
        adjudication=DEFAULT_ADJUDICATION,
    )


def build_from_pilot(pilot_path: Path) -> tuple[ClinicalGoldCase, ...]:
    """Costruisce il clinical gold dal JSONL del pilota."""
    target = Path(pilot_path)
    if not target.is_file():
        raise ClinicalGoldError(f"gold pilota non trovato: {target}")
    cases = []
    for number, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as error:
            raise ClinicalGoldError(f"riga {number}: JSON non valido ({error.msg})") from error
        cases.append(from_pilot_record(payload))
    if not cases:
        raise ClinicalGoldError("nessun caso nel gold pilota")
    return tuple(cases)


def load_clinical_gold(path: Path) -> tuple[ClinicalGoldCase, ...]:
    """Rilegge un clinical gold gia' materializzato."""
    target = Path(path)
    if not target.is_file():
        raise ClinicalGoldError(f"clinical gold non trovato: {target}")
    cases = []
    for line in target.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        payload = json.loads(stripped)
        claims = tuple(
            ClinicalGoldClaim(**claim) for claim in payload.get("expected_claims", [])
        )
        cases.append(
            ClinicalGoldCase(
                case_id=payload["case_id"],
                question=payload.get("question", ""),
                case_context=payload.get("case_context", ""),
                category=payload.get("category", ""),
                gene=payload.get("gene", ""),
                variant=payload.get("variant", ""),
                disease=payload.get("disease", ""),
                required_context=payload.get("required_context", ""),
                expected_entities=tuple(payload.get("expected_entities", [])),
                expected_claims=claims,
                expected_sources=tuple(payload.get("expected_sources", [])),
                expected_qualifiers=tuple(payload.get("expected_qualifiers", [])),
                expected_documentary_status=tuple(
                    payload.get("expected_documentary_status", [])
                ),
                expected_applicability=payload.get("expected_applicability", ""),
                expected_abstention=bool(payload.get("expected_abstention", False)),
                expected_human_review=bool(payload.get("expected_human_review", False)),
                expected_therapies=tuple(payload.get("expected_therapies", [])),
                expected_pmids=tuple(payload.get("expected_pmids", [])),
                expected_nct_ids=tuple(payload.get("expected_nct_ids", [])),
                required_tools=tuple(payload.get("required_tools", [])),
                optional_tools=tuple(payload.get("optional_tools", [])),
                unnecessary_tools=tuple(payload.get("unnecessary_tools", [])),
                gold_sources=tuple(payload.get("gold_sources", [])),
                annotation_status=payload.get("annotation_status", ""),
                annotators=tuple(payload.get("annotators", [])),
                adjudication=payload.get("adjudication", ""),
            )
        )
    return tuple(cases)


def verify_no_loss(
    pilot_cases: Sequence[Mapping[str, Any]], clinical: Sequence[ClinicalGoldCase]
) -> list[str]:
    """Verifica che la conversione non abbia perso nulla del pilota.

    Restituisce l'elenco delle discrepanze. Deve restare vuoto: se una claim, una
    fonte o un identificatore sparisce nella conversione, il clinical gold non
    rappresenta piu' l'annotazione umana.
    """
    problems: list[str] = []
    by_id = {case.case_id: case for case in clinical}
    for payload in pilot_cases:
        case_id = str(payload.get("case_id", ""))
        case = by_id.get(case_id)
        if case is None:
            problems.append(f"{case_id}: assente dal clinical gold")
            continue
        expected_claims = {str(c.get("claim_id")) for c in payload.get("claims") or []}
        actual_claims = {claim.claim_id for claim in case.expected_claims}
        if expected_claims != actual_claims:
            problems.append(
                f"{case_id}: claim divergenti, mancanti={sorted(expected_claims - actual_claims)}"
            )
        expected_sources = {str(s.get("source_id")) for s in payload.get("sources") or []}
        actual_sources = set(case.expected_sources)
        if expected_sources != actual_sources:
            problems.append(
                f"{case_id}: fonti divergenti, "
                f"mancanti={sorted(expected_sources - actual_sources)}"
            )
        for field_name in ("expected_therapies", "expected_pmids", "expected_nct_ids"):
            expected = set(payload.get(field_name) or [])
            actual = set(getattr(case, field_name))
            if expected != actual:
                problems.append(
                    f"{case_id}: {field_name} divergente, mancanti={sorted(expected - actual)}"
                )
    return problems
