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
from copy import deepcopy
from typing import Any

from ..dossier.builder import PRESENTABLE_AS_AUTHOR_CLAIM

NARRATOR_INPUT_VERSION = "dossier-narrator-input/1.1"
NARRATIVE_TRACE_VERSION = "dossier-narrative-trace/1.0"

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


def _candidate_support_checks(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Propagate every paper-scoped check without recalculating it."""
    checks: list[dict[str, Any]] = []
    direct = entry.get("candidate_support")
    if isinstance(direct, dict):
        fields = direct.get("fields") if isinstance(direct.get("fields"), dict) else {}
        paper_id = _text(direct.get("paper_id") or fields.get("paper_id"))
        document_id = _text(direct.get("document_id") or fields.get("document_id")) or paper_id
        checks.append({
            "candidate_id": _text(entry.get("candidate_id")),
            "paper_id": paper_id,
            "document_id": document_id,
            "source_unit_id": _text(direct.get("source_unit_id") or fields.get("source_unit_id")),
            "quote": "",
            "candidate_support": direct,
        })
    for validation in entry.get("validation_results") or []:
        if not isinstance(validation, dict):
            continue
        support = validation.get("candidate_support")
        if isinstance(support, dict):
            fields = support.get("fields") if isinstance(support.get("fields"), dict) else {}
            paper_id = _text(validation.get("paper_id") or support.get("paper_id") or fields.get("paper_id"))
            document_id = _text(validation.get("document_id") or support.get("document_id") or fields.get("document_id")) or paper_id
            source_unit_id = _text(validation.get("source_unit_id") or support.get("source_unit_id") or fields.get("source_unit_id"))
            quote = next(
                (
                    _text(enrichment.get("author_claim_quote"))
                    for enrichment in entry.get("author_context") or []
                    if _text(enrichment.get("paper_id")) == paper_id
                    and _text(enrichment.get("source_unit_id")) == source_unit_id
                ),
                "",
            )
            checks.append({
                "candidate_id": _text(entry.get("candidate_id")),
                "paper_id": paper_id,
                "document_id": document_id,
                "source_unit_id": source_unit_id,
                "quote": quote,
                "candidate_support": support,
            })
    return checks


def _candidate_support(entry: dict[str, Any], checks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Expose a singular check only when it is unambiguous."""
    if len(checks) == 1:
        return checks[0]["candidate_support"]
    return None


def _candidate(entry: dict[str, Any]) -> dict[str, Any]:
    mask = (entry.get("gate_results") or {}).get("support_mask") or {}
    direction = _text(mask.get("direction"))
    status = _text(entry.get("status"))
    warnings = [w for w in entry.get("warnings") or [] if isinstance(w, str)]
    quotes = _validated_quotes(entry)
    selected = [p for p in (entry.get("document_support") or {}).get("selected_papers") or []
                if isinstance(p, str)]
    support_checks = _candidate_support_checks(entry)
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
        "candidate_support": _candidate_support(entry, support_checks),
        "candidate_support_checks": support_checks,
        # Derivati espliciti: il modello non deve dedurli, e il verifier li usa
        # come atteso. Sono calcoli deterministici su dati già nel dossier.
        "expresses_support": (
            status == "DIRECT"
            and _text((entry.get("gate_results") or {}).get("bucket")) == "PRIMARY_BUCKET"
            and direction == "SUPPORTED"
        ),
        "source_does_not_support": direction == "SOURCE_DOES_NOT_SUPPORT",
    }


def _relation_candidate(entry: dict[str, Any], branch: str) -> dict[str, Any]:
    """Project one canonical relation entry without inventing support."""
    entry = deepcopy(entry)
    support_level = _text(entry.get("support_level"))
    status = support_level or ("CONTEXT_ONLY" if branch != "PAPER" else "AMBIGUOUS")
    warnings = []
    if branch == "TRIAL":
        warnings.append("TRIAL_ASSOCIATION_IS_NOT_EFFICACY_EVIDENCE")
    if branch == "KG_ONLY":
        warnings.append("DOCUMENT_PROVENANCE_NOT_AVAILABLE")
    paper_id = _text(entry.get("document_id"))
    quote = _text(entry.get("quote")) if entry.get("quote_valid") else ""
    candidate = {
        "candidate_id": _text(entry.get("candidate_id")),
        "branch": branch,
        "drug": None,
        "graph_relation": _text(entry.get("relation")),
        "canonical_status": status,
        "gate_bucket": "",
        "support_direction": _text(entry.get("direction")),
        "support_mask": deepcopy({k: v for k, v in (entry.get("support_fields") or {}).items()
                                   if isinstance(v, str)}),
        "warnings": warnings,
        "critical_warnings": warnings,
        "selected_paper_ids": [paper_id] if paper_id else [],
        "validated_quotes": ([{"quote": quote, "source_unit_id": _text(entry.get("quote_source_unit_id")),
                                "paper_id": paper_id, "author_context_summary": ""}] if quote else []),
        "has_validated_quote": bool(quote),
        "abstention_reasons": [],
        "candidate_support": ({"result": support_level, "fields": deepcopy(entry.get("support_fields") or {})}
                              if support_level else None),
        "candidate_support_checks": [],
        "expresses_support": branch == "PAPER" and support_level == "FULL_SUPPORT",
        "source_does_not_support": False,
    }
    source_refs = []
    source_refs.extend(candidate["selected_paper_ids"])
    source_refs.extend(
        q[key]
        for q in candidate["validated_quotes"]
        for key in ("paper_id", "source_unit_id")
        if q.get(key)
    )
    if branch == "TRIAL":
        candidate["trial_context"] = deepcopy({k: entry.get(k) for k in (
            "nct_id", "title", "conditions", "interventions", "phase", "status",
            "trial_resolution_status", "eligibility_status", "evidence_interpretation",
            "graph_provenance")})
        if candidate["trial_context"].get("nct_id"):
            source_refs.append(candidate["trial_context"]["nct_id"])
    elif branch == "KG_ONLY":
        candidate["kg_context"] = deepcopy({k: entry.get(k) for k in (
            "subject", "relation", "object", "disease_context", "direction",
            "evidence_type", "source_database", "graph_provenance",
            "verification_status", "document_provenance")})
        provenance = candidate["kg_context"].get("graph_provenance") or {}
        for key in ("edge_ids", "node_ids"):
            source_refs.extend(provenance.get(key) or [])
    candidate["source_refs"] = list(dict.fromkeys(str(ref) for ref in source_refs if ref))
    return candidate


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


def _trace_hash(payload: dict[str, Any]) -> str:
    body = {k: v for k, v in payload.items() if k != "trace_hash"}
    encoded = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _paper_trace(entry: dict[str, Any]) -> dict[str, Any]:
    quote_valid = entry.get("quote_valid") is True
    return {
        "candidate_id": _text(entry.get("candidate_id")),
        "branch": "PAPER",
        "relation": _text(entry.get("relation")),
        "document": {
            "document_id": _text(entry.get("document_id")),
            "requested_document_id": _text(entry.get("requested_document_id")),
            "pmcid": _text(entry.get("pmcid")),
            "document_source": _text(entry.get("document_source")),
            "document_type": _text(entry.get("document_type")),
            "document_resolution_status": _text(entry.get("document_resolution_status")),
            "source_unit_id": _text(entry.get("quote_source_unit_id")),
            "validated_quote": _text(entry.get("quote")) if quote_valid else "",
            "quote_valid": quote_valid,
            "quote_validation": deepcopy(entry.get("quote_validation") or {}),
        },
        "support": {
            "support_level": _text(entry.get("support_level")),
            "support_status": _text(entry.get("support_status")),
            "support_reason": _text(entry.get("support_reason")),
            "support_fields": deepcopy(entry.get("support_fields") or {}),
            "reader_decision": _text(entry.get("reader_decision")),
            "reader_status": _text(entry.get("reader_status")),
            "reason": _text(entry.get("reason")),
        },
        "graph_provenance": deepcopy(entry.get("graph_provenance") or {}),
    }


def _trial_trace(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": _text(entry.get("candidate_id")),
        "branch": "TRIAL",
        "relation": _text(entry.get("relation")),
        "trial": deepcopy({key: entry.get(key) for key in (
            "nct_id", "title", "conditions", "interventions", "phase", "status",
            "trial_resolution_status", "eligibility_status", "evidence_interpretation",
            "provenance_status", "source",
        )}),
        "graph_provenance": deepcopy(entry.get("graph_provenance") or {}),
    }


def _kg_only_trace(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": _text(entry.get("candidate_id")),
        "branch": "KG_ONLY",
        "graph": deepcopy({key: entry.get(key) for key in (
            "subject", "relation", "object", "disease_context", "direction", "evidence_type",
            "source_database", "verification_status", "document_provenance", "document_id",
        )}),
        "graph_provenance": deepcopy(entry.get("graph_provenance") or {}),
    }


def build_narrative_trace(canonical_dossier: dict[str, Any]) -> dict[str, Any]:
    """Create a source-level, deterministic trace for narrative consumers."""
    dossier = canonical_dossier or {}
    candidates: list[dict[str, Any]] = []
    candidates.extend(_paper_trace(entry) for entry in dossier.get("paper_evidence") or []
                      if isinstance(entry, dict))
    candidates.extend(_trial_trace(entry) for entry in dossier.get("clinical_trials") or []
                      if isinstance(entry, dict))
    candidates.extend(_kg_only_trace(entry) for entry in dossier.get("kg_only_relations") or []
                      if isinstance(entry, dict))
    payload = {
        "contract_version": NARRATIVE_TRACE_VERSION,
        "case_id": _text(dossier.get("case_id")),
        "candidates": candidates,
    }
    payload["trace_hash"] = _trace_hash(payload)
    return payload


def _presentation_entries(entries: Any, branch: str) -> list[dict[str, Any]]:
    """Return isolated, presentation-safe copies of canonical branch entries."""
    projected: list[dict[str, Any]] = []
    for raw in entries or []:
        if not isinstance(raw, dict):
            continue
        entry = deepcopy(raw)
        if branch == "PAPER":
            if entry.get("quote_valid") is False:
                entry.pop("quote", None)
                entry.pop("author_claim_quote", None)
            entry.pop("rejected_quotes", None)
            entry.pop("author_context", None)
        projected.append(entry)
    return projected


def build_narrator_input(canonical_dossier: dict[str, Any]) -> dict[str, Any]:
    """Proiezione del dossier canonico ammessa al Narrator.

    Esclusi per costruzione: candidate escluse, ``excluded_papers``, quote
    rigettate o solo proposte, output grezzo del modello, internals del
    validatore, documenti integrali, SourceUnit non selezionate, gold label.
    """
    dossier = canonical_dossier or {}
    if any(key in dossier for key in ("paper_evidence", "clinical_trials", "kg_only_relations")):
        candidates = (
            [_relation_candidate(e, "PAPER") for e in dossier.get("paper_evidence") or []]
            + [_relation_candidate(e, "TRIAL") for e in dossier.get("clinical_trials") or []]
            + [_relation_candidate(e, "KG_ONLY") for e in dossier.get("kg_only_relations") or []]
        )
    else:
        candidates = [_candidate(e) for e in dossier.get("candidate_therapies") or []]
    payload = {
        "contract_version": NARRATOR_INPUT_VERSION,
        "case": _case(dossier),
        "candidates": candidates,
        "paper_evidence": _presentation_entries(dossier.get("paper_evidence"), "PAPER"),
        "clinical_trials": _presentation_entries(dossier.get("clinical_trials"), "TRIAL"),
        "kg_only_relations": _presentation_entries(dossier.get("kg_only_relations"), "KG_ONLY"),
        "limitations": [x for x in dossier.get("limitations") or [] if isinstance(x, str)],
        "provenance_summary": {
            "dossier_version": _text((dossier.get("provenance") or dossier.get("provenance_summary") or {}).get("dossier_version")),
            "dossier_kind": _text((dossier.get("provenance") or dossier.get("provenance_summary") or {}).get("dossier_kind")),
            "llm_never_decides": list((dossier.get("provenance") or dossier.get("provenance_summary") or {}).get("gemma_never_decides") or []),
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
        # NCT is already authorized in the TRIAL projection. Identifier checks
        # are stricter than token checks, so it must be added explicitly.
        trial = c.get("trial_context") or {}
        nct_id = _text(trial.get("nct_id"))
        if nct_id:
            papers.add(nct_id)
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
