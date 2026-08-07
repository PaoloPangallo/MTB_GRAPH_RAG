"""NarratorInput — projection deterministica dal dossier canonico.

Il Narrator **non riceve il runtime state**. Riceve una proiezione costruita da
questo modulo, che legge soltanto il dossier canonico e seleziona soltanto i
campi ammessi.

Il principio è quello che ha chiuso ISS-003: ciò che non è validato non deve
poter essere confuso con ciò che lo è. Qui il principio è applicato a monte —
una quote rigettata non arriva nemmeno al modello.

Nessun LLM è coinvolto. La funzione è pura: lo stesso dossier canonico produce
lo stesso ``NarratorInput`` e lo stesso ``narrator_input_hash``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ..dossier.builder import PRESENTABLE_AS_AUTHOR_CLAIM

NARRATOR_INPUT_VERSION = "dossier-narrator-input/1.0"

#: Warning che la narrativa **deve** riflettere. Gli altri sono tecnici: utili
#: nel dossier strutturato, non obbligatori nella prosa. La distinzione è
#: dichiarata qui e usata dal verifier (§15).
NARRATIVE_CRITICAL_WARNINGS: frozenset[str] = frozenset({
    "NO_VALIDATED_ENRICHMENT_AVAILABLE",
    "VALIDATED_ENRICHMENT_DOES_NOT_ADDRESS_DIRECTION",
    "SOURCE_POLARITY_DOES_NOT_SUPPORT",
    "SOURCE_POLARITY_CONTRADICTS",
    "SOURCE_POLARITY_NEUTRAL",
})

TECHNICAL_ONLY_WARNINGS: frozenset[str] = frozenset({
    "SOME_ENRICHMENTS_ACCEPTED_WITH_WARNING",
})

#: Direzioni della support mask che esprimono **assenza o negazione** di
#: supporto documentale. Una narrativa che le descrive come supporto è
#: un'inversione, non una parafrasi.
NON_SUPPORTING_DIRECTIONS: frozenset[str] = frozenset({
    "SOURCE_DOES_NOT_SUPPORT", "CONTRADICTED",
    "NO_DOCUMENT_SIGNAL", "UNRELATED_EVIDENCE",
})

#: Status che non esprimono supporto stabilito.
NON_SUPPORTING_STATUSES: frozenset[str] = frozenset({
    "AMBIGUOUS", "CONTRADICTED", "NO_MATCH",
})


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _validated_quotes(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Solo le voci che il validatore deterministico ha accettato.

    Il filtro è su ``presentation_state``, cioè sulla stessa fonte di verità che
    la UI usa dopo ISS-003. Una ``REJECTED_QUOTE`` o una ``PROPOSED_QUOTE_NOT_VALIDATED``
    non entra nella projection: il modello non può citare ciò che non vede.
    """
    quotes = []
    for voice in entry.get("author_context") or []:
        if voice.get("presentation_state") not in PRESENTABLE_AS_AUTHOR_CLAIM:
            continue
        quote = _text(voice.get("author_claim_quote"))
        if not quote:
            continue
        quotes.append({
            "quote": quote,
            "source_unit_id": _text(voice.get("source_unit_id")),
            "paper_id": _text(voice.get("paper_id")),
            "author_context_summary": _text(voice.get("author_context_summary")),
        })
    return quotes


def _abstentions(entry: dict[str, Any]) -> list[str]:
    """Motivi di astensione, senza il testo proposto e poi scartato."""
    return [
        _text(v.get("abstention_reason"))
        for v in entry.get("author_context") or []
        if v.get("presentation_state") == "ABSTAINED" and _text(v.get("abstention_reason"))
    ]


def _candidate(entry: dict[str, Any]) -> dict[str, Any]:
    mask = (entry.get("gate_results") or {}).get("support_mask") or {}
    direction = _text(mask.get("direction"))
    status = _text(entry.get("status"))
    warnings = [w for w in entry.get("warnings") or [] if isinstance(w, str)]
    quotes = _validated_quotes(entry)
    selected = [p for p in (entry.get("document_support") or {}).get("selected_papers") or []
                if isinstance(p, str)]
    return {
        "candidate_id": _text(entry.get("candidate_id")),
        "drug": entry.get("drug"),
        "graph_relation": _text(entry.get("graph_relation")),
        "canonical_status": status,
        "gate_bucket": _text((entry.get("gate_results") or {}).get("bucket")),
        "support_direction": direction,
        "support_mask": {k: v for k, v in mask.items() if isinstance(v, str)},
        "warnings": warnings,
        "critical_warnings": [w for w in warnings if w in NARRATIVE_CRITICAL_WARNINGS],
        "selected_paper_ids": selected,
        "validated_quotes": quotes,
        "has_validated_quote": bool(quotes),
        "abstention_reasons": _abstentions(entry),
        # Derivati espliciti: il modello non deve dedurli, e il verifier li usa
        # come atteso. Sono calcoli deterministici su dati già nel dossier.
        "expresses_support": (status not in NON_SUPPORTING_STATUSES
                              and direction not in NON_SUPPORTING_DIRECTIONS),
        "source_does_not_support": direction == "SOURCE_DOES_NOT_SUPPORT",
    }


def _case(dossier: dict[str, Any]) -> dict[str, Any]:
    context = dossier.get("case_context") or {}

    def value(field: str) -> str:
        node = context.get(field)
        if isinstance(node, dict):
            return _text(node.get("normalized_value")) or _text(node.get("raw_value"))
        return _text(node)

    biomarkers = []
    for b in context.get("biomarkers") or []:
        if isinstance(b, dict):
            label = _text(b.get("normalized_value")) or _text(b.get("raw_value"))
            if label:
                biomarkers.append(label)
    return {
        "case_id": _text(dossier.get("case_id")),
        "query_intent": _text(context.get("query_intent")),
        "disease": value("disease"),
        "biomarkers": biomarkers,
        "target_intervention": value("target_intervention"),
        "clinical_question": _text(context.get("clinical_question")),
    }


def narrator_input_hash(payload: dict[str, Any]) -> str:
    """Hash stabile: chiavi ordinate, separatori fissi, UTF-8."""
    body = {k: v for k, v in payload.items() if k != "narrator_input_hash"}
    encoded = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_narrator_input(canonical_dossier: dict[str, Any]) -> dict[str, Any]:
    """Proiezione del dossier canonico ammessa al Narrator.

    Esclusi per costruzione: candidate escluse, ``excluded_papers``, quote
    rigettate o solo proposte, output grezzo del modello, internals del
    validatore, documenti integrali, SourceUnit non selezionate, gold label.
    """
    dossier = canonical_dossier or {}
    candidates = [_candidate(e) for e in dossier.get("candidate_therapies") or []]
    payload = {
        "contract_version": NARRATOR_INPUT_VERSION,
        "case": _case(dossier),
        "candidates": candidates,
        "limitations": [x for x in dossier.get("limitations") or [] if isinstance(x, str)],
        "provenance_summary": {
            "dossier_version": _text((dossier.get("provenance") or {}).get("dossier_version")),
            "dossier_kind": _text((dossier.get("provenance") or {}).get("dossier_kind")),
            "llm_never_decides": list((dossier.get("provenance") or {}).get("gemma_never_decides") or []),
        },
        "counts": {
            "candidates": len(candidates),
            "with_validated_quote": sum(1 for c in candidates if c["has_validated_quote"]),
            "expressing_support": sum(1 for c in candidates if c["expresses_support"]),
        },
    }
    payload["narrator_input_hash"] = narrator_input_hash(payload)
    return payload


def allowed_entities(narrator_input: dict[str, Any]) -> dict[str, set[str]]:
    """Insieme delle entità che la narrativa può nominare.

    Costruito **solo** dal NarratorInput: è il riferimento della entity closure
    del verifier (§10).
    """
    case = narrator_input.get("case") or {}
    drugs, candidate_ids, papers, quotes = set(), set(), set(), set()
    for c in narrator_input.get("candidates") or []:
        if c.get("candidate_id"):
            candidate_ids.add(c["candidate_id"])
        if c.get("drug"):
            drugs.add(str(c["drug"]))
        papers.update(c.get("selected_paper_ids") or [])
        for q in c.get("validated_quotes") or []:
            quotes.add(q["quote"])
            if q.get("paper_id"):
                papers.add(q["paper_id"])
            if q.get("source_unit_id"):
                papers.add(q["source_unit_id"])
    if case.get("target_intervention"):
        drugs.add(case["target_intervention"])
    return {
        "drugs": drugs,
        "candidate_ids": candidate_ids,
        "identifiers": papers,
        "quotes": quotes,
        "diseases": {case["disease"]} if case.get("disease") else set(),
        "biomarkers": set(case.get("biomarkers") or []),
    }
