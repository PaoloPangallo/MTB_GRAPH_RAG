"""Presentation adapter for the native V3 retrieval result.

The retriever remains the source of truth for buckets and gate decisions.  This
module only projects its typed output into a product-facing response: clinical
claims are kept separate from technical records, provenance is made explicit,
and internal reason codes receive stable human-readable messages.
"""
from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from backend.pipeline.evidence.corpus import loader as CORPUS_LOADER
from backend.pipeline.evidence.retrieval.pipeline import RetrievalOutcome

_BUCKETS = {
    "primary_ranked_results": "primary",
    "retained_with_warning": "warning",
    "audit_only_results": "audit",
    "rejected_by_native_constraints": "rejected",
}

_REASON_MESSAGES = {
    "PARENT_PROVENANCE_CONTAINER_NOT_CLAIM": "Record tecnico utilizzato per conservare la provenienza",
    "CLASS_RELATION_UNVERIFIED": "La relazione tra classe e intervento non e verificata",
    "BIOMARKER_MISMATCH": "Il biomarcatore non coincide con quello del caso",
    "NATIVE_BIOMARKER_MISMATCH": "Il biomarcatore non coincide con quello del caso",
    "DISEASE_MISMATCH": "La malattia non coincide con quella del caso",
    "INTERVENTION_MISMATCH": "Il trattamento non coincide con quello richiesto",
    "NATIVE_INTERVENTION_MISMATCH": "Il trattamento non coincide con quello richiesto",
    "CLAIM_DISEASE_SCOPE_BROADER_THAN_QUERY": "L'ambito di malattia e piu ampio della domanda",
    "RESULT_NOT_SEPARABLE_FOR_QUERY_SUBTYPE": "Il risultato non e separabile per il sottotipo richiesto",
    "PRECLINICAL_NOT_CLINICAL_BENEFIT": "L'evidenza e preclinica e non dimostra beneficio clinico",
    "SINGLE_INCOMPATIBLE_GATE_BLOCKS_PRIMARY": "Un gate strutturale incompatibile blocca la promozione",
    "CLAIM_DEPRECATED": "La claim e ritirata dal corpus attivo",
}

_REASON_MESSAGES.update({
    'BIOMARKER_EXACT_LITERAL_MATCH': 'Il biomarcatore coincide esattamente.',
    'BIOMARKER_QUERY_SATISFIES_ONE_DISJUNCT': 'Il caso soddisfa una disgiunzione biomarcatore dichiarata dalla claim.',
    'DISEASE_EXACT_MATCH': 'La malattia coincide esattamente.',
    'DISEASE_VERIFIED_ALIAS_MATCH': 'La malattia coincide tramite alias verificato.',
    'CROSS_DISEASE_MISMATCH': 'La claim appartiene a un contesto di malattia diverso.',
    'INTERVENTION_FORM_EXACT_MATCH': 'La formulazione dell intervento coincide esattamente.',
    'INTERVENTION_FORMULATION_RELATION_UNRESOLVED': 'La relazione tra intervento e formulazione non e risolta.',
    'ACTIVE_MOIETY_MISMATCH': 'La moieta attiva dell intervento non coincide.',
    'NATIVE_DIRECTION_MISMATCH': 'La direzione nativa della claim non coincide.',
    'FORMULATION_MISMATCH_NOT_COMPENSABLE': 'La formulazione incompatibile non e compensabile.',
    'INTEGRATED_GATE_PRECEDES_SCORING': 'Un gate integrato viene valutato prima dello score.',
    'FORMULATION_GATE_PRECEDES_SCORING': 'Il gate di formulazione viene valutato prima dello score.',
})

_GATE_ORDER = (
    ("claim_status_result", "claim_status"),
    ("domain_match_result", "domain"),
    ("biomarker_match_result", "biomarker"),
    ("disease_match_result", "disease"),
    ("intervention_match_result", "intervention_identity"),
    ("formulation_match_result", "formulation"),
    ("direction_match_result", "direction"),
)

_COMPARISON_AXIS_KEYS = {
    "claim_status": "claim_status_result",
    "domain": "domain_match_result",
    "biomarker": "biomarker_match_result",
    "disease": "disease_match_result",
    "intervention_identity": "intervention_match_result",
    "formulation": "formulation_match_result",
    "direction": "direction_match_result",
}

def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


@lru_cache(maxsize=1)
def _source_records(repository_version: str) -> dict[str, Mapping[str, Any]]:
    if repository_version != "qualified_claim_repository/1.4":
        return {}
    corpus = CORPUS_LOADER.load_from_registry(
        policy_mode="strict_verified",
        verify_hashes=True,
        verify_sources=True,
    )
    return {
        str(record.get("claim_id")): record
        for record in corpus.claims
        if record.get("claim_id")
    }


def _source_record(result: Any, repository_version: str) -> Mapping[str, Any]:
    claim_id = str(getattr(result, "claim_id", "") or "")
    return _source_records(repository_version).get(claim_id, {})


def _source_value(source_record: Mapping[str, Any], field: str) -> Any:
    value = source_record.get(field)
    if value in (None, ""):
        return None
    return value


def _message(code: str) -> str:
    return _REASON_MESSAGES.get(code, "Decisione strutturale registrata dal gate V3")


def _reason_gate(result: Any, code: str) -> str:
    gate = _as_dict(getattr(result, "gate", {}))
    for gate_name, axis_key in _COMPARISON_AXIS_KEYS.items():
        axis = _as_dict(gate.get(axis_key))
        if code in {str(item) for item in (axis.get("reason_codes") or ())}:
            return gate_name
    return str(gate.get("dominant_gate") or "structural_gate")


def _reason_codes(result: Any) -> list[dict[str, str]]:
    return [
        {
            "code": str(code),
            "gate": _reason_gate(result, str(code)),
            "human_message": _message(str(code)),
        }
        for code in (getattr(result, "reason_codes", ()) or ())
    ]


def _status_for_gate(axis: Mapping[str, Any], bucket: str) -> str:
    if axis.get("compatible") is False or axis.get("rejected_by_native_constraints"):
        return "fail"
    if axis.get("status") in {"deprecated_claim", "audit_only"}:
        return "not_applicable"
    if bucket == "warning":
        return "warning"
    return "pass"


def _query_forms(query: Mapping[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    payload = dict(query or {})
    if "original" in payload or "normalized" in payload:
        original = _as_dict(payload.get("original"))
        normalized = _as_dict(payload.get("normalized"))
        gate_query = _as_dict(normalized.get("gate_query"))
        return original, normalized, gate_query
    return payload, payload, _as_dict(payload.get("gate_query")) or payload


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == ()


def _comparison_value(
    *,
    original: Any,
    normalized: Any,
    claim: Any,
    native_result: Any,
    not_applicable_reason: str | None = None,
) -> dict[str, Any]:
    reason = not_applicable_reason
    if reason is None and _is_empty(original):
        reason = "NOT_PROVIDED_BY_CASE"
    if reason is None and _is_empty(claim):
        reason = "MISSING_IN_CLAIM"
    if reason is None and native_result is None:
        reason = "NOT_EXPOSED_BY_GATE"
    availability = "AVAILABLE" if reason is None else reason
    return {
        "query_value_original": original,
        "query_value_normalized": normalized,
        "claim_value": claim,
        "comparison_result": native_result,
        "not_applicable_reason": reason,
        "availability": availability,
    }


def _native_axis(result: Any, name: str) -> dict[str, Any]:
    gate = _as_dict(getattr(result, "gate", {}))
    return _as_dict(gate.get(_COMPARISON_AXIS_KEYS[name]))


def _claim_fields(result: Any, source_record: Mapping[str, Any]) -> dict[str, Any]:
    subject = _source_value(source_record, "subject")
    relation = _source_value(source_record, "relation")
    obj = _source_value(source_record, "object")
    return {
        "claim_text": _source_value(source_record, "claim_text"),
        "subject": subject,
        "relation": relation,
        "object": obj,
        "biomarker": _source_value(source_record, "biomarker")
        or str(getattr(result, "biomarker", "") or "")
        or None,
        "disease": _source_value(source_record, "disease_scope")
        or str(getattr(result, "disease_scope", "") or "")
        or None,
        "intervention": _source_value(source_record, "intervention")
        or str(getattr(result, "canonical_intervention", "") or "")
        or None,
        "direction": _source_value(source_record, "direction"),
        "evidence_type": _source_value(source_record, "claim_type")
        or str(getattr(result, "claim_type", "") or "")
        or None,
        "structured_tuple_complete": all(
            value not in (None, "") for value in (subject, relation, obj)
        ),
    }


def _case_comparison(
    result: Any,
    query: Mapping[str, Any] | None,
    source_record: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    original, normalized, gate_query = _query_forms(query)
    fields = _claim_fields(result, source_record)
    biomarker_original = original.get("biomarker") or original.get("alteration")
    biomarker_normalized = (
        normalized.get("normalized_biomarker")
        or gate_query.get("biomarker")
    )
    intervention_axis = _native_axis(result, "intervention_identity")
    formulation_axis = _native_axis(result, "formulation")
    direction_axis = _native_axis(result, "direction")
    return {
        "biomarker": _comparison_value(
            original=biomarker_original,
            normalized=biomarker_normalized,
            claim=fields["biomarker"],
            native_result=_native_axis(result, "biomarker").get("match_type"),
        ),
        "disease": _comparison_value(
            original=original.get("disease"),
            normalized=normalized.get("normalized_disease")
            or gate_query.get("disease"),
            claim=fields["disease"],
            native_result=_native_axis(result, "disease").get("relation_type"),
        ),
        "intervention": _comparison_value(
            original=original.get("interventions", []),
            normalized=normalized.get("normalized_interventions", []),
            claim=fields["intervention"],
            native_result=intervention_axis.get("match_type"),
        ),
        "formulation": _comparison_value(
            original=original.get("intervention_class"),
            normalized=gate_query.get("intervention_class"),
            claim=_as_dict(formulation_axis).get("claim_form"),
            native_result=formulation_axis.get("relation_type"),
            not_applicable_reason=(
                "NOT_APPLICABLE"
                if formulation_axis.get("axis_evaluated") is False
                else None
            ),
        ),
        "direction": _comparison_value(
            original=original.get("direction"),
            normalized=gate_query.get("direction"),
            claim=fields["direction"],
            native_result=direction_axis.get("direction_match_type"),
        ),
        "claim_status": _comparison_value(
            original=None,
            normalized=None,
            claim=_as_dict(_native_axis(result, "claim_status")).get("status"),
            native_result=_as_dict(_native_axis(result, "claim_status")).get(
                "status"
            ),
            not_applicable_reason="NOT_EXPOSED_BY_GATE",
        ),
        "domain": _comparison_value(
            original=original.get("claim_domain"),
            normalized=normalized.get("claim_domain"),
            claim=_as_dict(_native_axis(result, "domain")).get("claim_domain"),
            native_result=_as_dict(_native_axis(result, "domain")).get(
                "domain_match"
            ),
        ),
    }


def _decision(result: Any, source_record: Mapping[str, Any]) -> dict[str, Any]:
    score = _as_dict(getattr(result, "score", {}))
    eligibility = _as_dict(score.get("eligibility"))
    gate = _as_dict(getattr(result, "gate", {}))
    structural_eligible = eligibility.get("structural_score_eligible")
    if structural_eligible is None:
        structural_eligible = gate.get("structural_score_eligible")
    total = score.get("total") if "total" in score else None
    return {
        "bucket": _BUCKETS.get(str(getattr(result, "bucket", "")), None),
        "applicability": _source_value(source_record, "applicability"),
        "structural_score": total,
        "structural_score_eligible": structural_eligible,
    }


def _gate_message(name: str, axis: Mapping[str, Any], codes: list[str]) -> str:
    if codes:
        return _message(codes[0])
    if name == "claim_status" and axis.get("status") == "active_claim":
        return "Lo stato della claim e ammesso."
    if name == "domain" and axis.get("domain_match") is True:
        return "Il dominio della claim e compatibile."
    if name == "intervention_identity" and axis.get("match_type") == "no_intervention_constraint":
        return "Nessun intervento e stato imposto dal caso."
    if name == "formulation" and axis.get("axis_evaluated") is False:
        return "La formulazione non e applicabile senza un vincolo di intervento."
    if name == "direction" and axis.get("direction_match_type") == "not_constrained":
        return "La direzione non e stata imposta dal caso."
    return "Esito del gate disponibile nei dati nativi."


def _gate_trace(
    result: Any,
    query: Mapping[str, Any] | None = None,
    source_record: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    gate = _as_dict(getattr(result, "gate", {}))
    final_bucket = _BUCKETS.get(str(getattr(result, "bucket", "")), "audit")
    source = source_record or {}
    comparisons = _case_comparison(result, query, source)
    claim_values = {
        'biomarker': getattr(result, 'biomarker', None),
        'disease': getattr(result, 'disease_scope', None),
        'intervention_identity': getattr(result, 'canonical_intervention', None),
        'formulation': _as_dict(gate.get('formulation_match_result')).get('claim_form'),
        'direction': _source_value(source, "direction"),
        "claim_status": _as_dict(gate.get("claim_status_result")).get("status"),
        "domain": _as_dict(gate.get("domain_match_result")).get("claim_domain"),
    }
    trace: list[dict[str, Any]] = []
    for key, name in _GATE_ORDER:
        axis = _as_dict(gate.get(key))
        if not axis:
            continue
        codes = [str(code) for code in (axis.get("reason_codes") or ())]
        comparison_name = name
        if name == "intervention_identity":
            comparison_name = "intervention"
        comparison = comparisons.get(comparison_name, {})
        trace.append(
            {
                'case_value': comparison.get("query_value_normalized"),
                'claim_value': comparison.get("claim_value", claim_values.get(name)),
                "gate": name,
                "status": _status_for_gate(axis, final_bucket),
                "reason_code": codes[0] if codes else None,
                "reason_codes": codes,
                "message": _gate_message(name, axis, codes),
                "query_value_original": comparison.get("query_value_original"),
                "query_value_normalized": comparison.get("query_value_normalized"),
                "comparison_result": comparison.get("comparison_result"),
                "not_applicable_reason": comparison.get("not_applicable_reason"),
                "availability": comparison.get("availability"),
            }
        )
    if not trace and gate:
        trace.append(
            {
                "gate": "structural_gate",
                "status": "pass" if final_bucket == "primary" else final_bucket,
                "reason_code": None,
                "reason_codes": [],
                "message": "Traccia strutturale disponibile nel risultato nativo",
            }
        )
    return trace


def _provenance(result: Any) -> dict[str, Any]:
    source = _as_dict(getattr(result, "provenance", {}))
    source_ids = [str(item) for item in (source.get("source_ids") or ())]
    locators = [dict(item) for item in (source.get("locators") or ())]
    source_unit_ids = [str(item) for item in (source.get("source_unit_ids") or ())]
    parent_id = str(source.get("parent_id") or getattr(result, "parent_id", "") or "") or None
    if locators:
        status = "VERIFIED_LOCATOR"
    elif source_ids or source_unit_ids:
        status = "ALTERNATIVE_SOURCE_AVAILABLE"
    elif parent_id:
        status = "PARENT_ONLY"
    else:
        status = "SOURCE_IDENTIFIER_MISSING"
    missing: list[str] = []
    if not source_ids:
        missing.append("source_ids")
    if not locators:
        missing.append("locators")
    return {
        "status": status,
        "pmid": next((item for item in source_ids if item.upper().startswith("PUBMED:")), None),
        "doi": next((item for item in source_ids if item.upper().startswith("DOI:")), None),
        "nct": next((item for item in source_ids if item.upper().startswith("NCT:")), None),
        "url": next((item.get("url") for item in locators if item.get("url")), None),
        "locator": locators[0] if locators else None,
        "source_ids": source_ids,
        "source_unit_ids": source_unit_ids,
        "parent_record_id": parent_id,
        "source_unit_id": source_unit_ids[0] if source_unit_ids else None,
        "is_verifiable": bool(locators or source_ids or source_unit_ids),
        "missing_fields": missing,
        "raw": source,
    }


def _candidate_kind(result: Any) -> str:
    claim_type = str(getattr(result, "claim_type", "") or "")
    gate = _as_dict(getattr(result, "gate", {}))
    status = _as_dict(gate.get("claim_status_result"))
    if claim_type == "graph_evidence_record":
        return "provenance_container"
    if claim_type == "unresolved_association" or str(getattr(result, "claim_id", "")).startswith("UNR-"):
        return "unresolved_association"
    if claim_type == "unsupported_association" or str(getattr(result, "claim_id", "")).startswith("UNS-"):
        return "unsupported_association"
    if bool(status.get("deprecated")) or claim_type == "deprecated_claim":
        return "deprecated_claim"
    return "evidence_claim"


def _claim_record(
    result: Any,
    query: Mapping[str, Any] | None = None,
    repository_version: str = "",
) -> dict[str, Any]:
    gate = _as_dict(getattr(result, "gate", {}))
    formulation = _as_dict(gate.get("formulation_match_result"))
    status = _as_dict(gate.get("claim_status_result"))
    bucket = _BUCKETS.get(str(getattr(result, "bucket", "")), "audit")
    intervention = str(getattr(result, "canonical_intervention", "") or "") or None
    members = [str(item) for item in (getattr(result, "intervention_members", ()) or ())]
    source_record = _source_record(result, repository_version)
    fields = _claim_fields(result, source_record)
    record = {
        "claim_id": str(getattr(result, "claim_id", "")),
        "candidate_kind": _candidate_kind(result),
        "subject": fields["subject"],
        "relation": fields["relation"],
        "object": fields["object"],
        "structured_tuple_complete": fields["structured_tuple_complete"],
        "claim_text": fields["claim_text"],
        "disease": fields["disease"],
        "biomarker": fields["biomarker"],
        "intervention": fields["intervention"] or intervention,
        "formulation": formulation.get("claim_form"),
        "regimen": members if len(members) > 1 else None,
        "direction": fields["direction"],
        "evidence_type": fields["evidence_type"],
        "applicability": _source_value(source_record, "applicability"),
        "separability": formulation.get("relation_status"),
        "status": status.get("status"),
        "bucket": bucket,
        "score": _as_dict(getattr(result, "score", {})),
        "rank": int(getattr(result, "rank", 0) or 0),
        "reason_codes": _reason_codes(result),
        "gate_trace": _gate_trace(result, query, source_record),
        "claim": fields,
        "decision": _decision(result, source_record),
        "case_comparison": _case_comparison(result, query, source_record),
        "qualifiers": [str(item) for item in (getattr(result, "warnings", ()) or ())],
        "parent_graph_evidence_record": {
            "parent_id": str(getattr(result, "parent_id", "") or "") or None,
            "graph_evidence_id": str(getattr(result, "graph_evidence_id", "") or "") or None,
        },
        "source_unit": _provenance(result).get("source_unit_id"),
        "provenance": _provenance(result),
    }
    return record


def _technical_record(
    result: Any,
    query: Mapping[str, Any] | None = None,
    repository_version: str = "",
) -> dict[str, Any]:
    record = _claim_record(result, query, repository_version)
    kind = record["candidate_kind"]
    record["technical_kind"] = kind
    return record


_GATE_LABELS = {
    'claim_status_gate': 'Stato della claim',
    'domain_gate': 'Dominio',
    'biomarker_gate': 'Biomarcatore',
    'disease_gate': 'Malattia',
    'intervention_identity_gate': 'Identità intervento',
    'formulation_gate': 'Formulazione',
    'direction_polarity_gate': 'Direzione e polarità',
}

_GATE_LABELS.update({
    'active_claim_loading': 'Caricamento claim attive',
    'claim_status_gate': 'Stato della claim',
    'bucket_composition': 'Composizione bucket',
    'scoring_where_permitted': 'Scoring dove consentito',
    'within_bucket_ranking': 'Ranking nel bucket',
    'result_rendering': 'Rendering del risultato',
    'regimen_class_aggregate_gate': 'Aggregazione classe regimen',
    'direction_polarity_gate': 'Direzione e polarita',
})

_GATE_AXIS_KEYS = {
    'claim_status_gate': 'claim_status_result',
    'domain_gate': 'domain_match_result',
    'biomarker_gate': 'biomarker_match_result',
    'disease_gate': 'disease_match_result',
    'intervention_identity_gate': 'intervention_match_result',
    'formulation_gate': 'formulation_match_result',
    'direction_polarity_gate': 'direction_match_result',
}

_PROVENANCE_LABELS = {
    'VERIFIED_LOCATOR': 'Locator verificato',
    'ALTERNATIVE_SOURCE_AVAILABLE': 'Fonte alternativa disponibile',
    'PARENT_ONLY': 'Solo parent record',
    'SOURCE_IDENTIFIER_MISSING': 'Identificatore fonte mancante',
    'PROVENANCE_INCOMPLETE': 'Provenance incompleta',
}


def _pipeline_stages(
    payload: Any,
    evidence: Mapping[str, list[dict[str, Any]]],
    technical: Mapping[str, list[dict[str, Any]]],
    summary: Mapping[str, int],
    abstention: bool,
) -> list[dict[str, Any]]:
    native_query = dict(getattr(payload, 'query', {}) or {})
    original = dict(native_query.get('original') or {})
    normalized = dict(native_query.get('normalized') or {})
    phase_latency = dict(getattr(payload, 'latency_ms', {}) or {})
    technical_counts = {name: len(items) for name, items in technical.items()}
    bucket_counts = {name: len(items) for name, items in evidence.items()}
    differences = [
        {
            'field': field,
            'input_value': original.get(field),
            'normalized_value': normalized.get(field),
        }
        for field in sorted(set(original) | set(normalized))
        if original.get(field) != normalized.get(field)
    ]
    return [
        {
            'id': 'clinical_input',
            'label': 'Input clinico',
            'status': 'completed',
            'input_count': 1,
            'output_count': 1,
            'latency_ms': None,
            'details': {'payload': original},
        },
        {
            'id': 'case_normalization',
            'label': 'CaseContext normalizzato',
            'status': 'completed',
            'input_count': 1,
            'output_count': 1,
            'latency_ms': phase_latency.get('normalization'),
            'details': {'normalized': normalized, 'differences': differences},
        },
        {
            'id': 'repository_candidates',
            'label': 'Repository e candidati',
            'status': 'completed',
            'input_count': 1,
            'output_count': int(getattr(payload, 'candidate_count', 0) or 0),
            'latency_ms': None,
            'details': {
                'repository_version': summary.get('repository_version'),
                'claim_records': summary.get('claim_records', 0),
                'technical_records': summary.get('technical_records', 0),
                'technical_categories': technical_counts,
            },
        },
        {
            'id': 'structural_gates',
            'label': 'Gate strutturali',
            'status': 'completed',
            'input_count': int(getattr(payload, 'candidate_count', 0) or 0),
            'output_count': int(getattr(payload, 'candidate_count', 0) or 0),
            'latency_ms': phase_latency.get('gating'),
            'details': {
                'gate_execution_order': list(
                    dict(getattr(payload, 'gate_decisions', {}) or {}).get(
                        'gate_execution_order', []
                    )
                ),
            },
        },
        {
            'id': 'classification_ranking',
            'label': 'Classificazione e ranking nei bucket',
            'status': 'completed',
            'input_count': int(getattr(payload, 'candidate_count', 0) or 0),
            'output_count': int(summary.get('claim_records', 0)),
            'latency_ms': phase_latency.get('ranking'),
            'details': {'buckets': bucket_counts},
        },
        {
            'id': 'provenance_projection',
            'label': 'Verifica della provenance',
            'status': 'completed',
            'input_count': int(summary.get('claim_records', 0)),
            'output_count': int(summary.get('claim_records', 0)),
            'latency_ms': None,
            'details': {'status_counts': {}},
        },
        {
            'id': 'structured_dossier',
            'label': 'Dossier strutturato',
            'status': 'completed',
            'input_count': int(summary.get('claim_records', 0)),
            'output_count': int(summary.get('primary', 0) + summary.get('warning', 0)),
            'latency_ms': None,
            'details': {
                'included_buckets': ['primary', 'warning'],
                'excluded_buckets': ['audit', 'rejected'],
                'abstention': abstention,
            },
        },
        {
            'id': 'optional_narration',
            'label': 'Narrazione opzionale',
            'status': 'not_executed',
            'input_count': 1,
            'output_count': 0,
            'latency_ms': None,
            'details': {
                'executed': False,
                'message': 'Narrazione LLM non eseguita. Il risultato corrente è esclusivamente strutturale e deterministico.',
            },
        },
    ]


def _gate_summary(
    results: list[Any], gate_order: list[str]
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for gate_name in gate_order:
        axis_key = _GATE_AXIS_KEYS.get(gate_name)
        if axis_key is None:
            summaries.append(
                {
                    'gate': gate_name,
                    'label': _GATE_LABELS.get(gate_name, gate_name),
                    'pass_count': None,
                    'fail_count': None,
                    'not_applicable_count': None,
                    'warning_count': None,
                    'counts_available': False,
                    'reason_codes': [],
                    'explanations': [],
                    'note': 'Gate presente nell ordine nativo; conteggi per record non esposti.',
                }
            )
            continue
        counts = {'pass': 0, 'fail': 0, 'not_applicable': 0, 'warning': 0}
        codes: set[str] = set()
        messages: set[str] = set()
        for result in results:
            gate = _as_dict(getattr(result, 'gate', {}))
            axis = _as_dict(gate.get(axis_key))
            status = _status_for_gate(
                axis,
                _BUCKETS.get(str(getattr(result, 'bucket', '')), 'audit'),
            )
            counts[status] = counts.get(status, 0) + 1
            for code in axis.get('reason_codes') or ():
                codes.add(str(code))
                messages.add(_message(str(code)))
        summaries.append(
            {
                'gate': gate_name,
                'label': _GATE_LABELS[gate_name],
                'pass_count': counts['pass'],
                'fail_count': counts['fail'],
                'not_applicable_count': counts['not_applicable'],
                'warning_count': counts['warning'],
                'counts_available': True,
                'reason_codes': sorted(codes),
                'explanations': sorted(messages),
                'note': None,
            }
        )
    return summaries


def _bucket_summary(
    evidence: Mapping[str, list[dict[str, Any]]]
) -> dict[str, dict[str, Any]]:
    definitions = {
        'primary': 'Claim direttamente compatibili e ammesse al dossier principale.',
        'warning': 'Claim mantenute con una limitazione strutturale esplicita.',
        'audit': 'Claim conservate per verifica, non promosse nel dossier.',
        'rejected': 'Claim escluse dai vincoli strutturali nativi.',
    }
    return {
        bucket: {'count': len(evidence.get(bucket, [])), 'definition': definition}
        for bucket, definition in definitions.items()
    }


def _provenance_summary(
    evidence: Mapping[str, list[dict[str, Any]]]
) -> dict[str, dict[str, Any]]:
    summary = {
        status: {
            'count': 0,
            'label': label,
            'fields_present': [],
            'fields_missing': [],
        }
        for status, label in _PROVENANCE_LABELS.items()
    }
    for records in evidence.values():
        for record in records:
            provenance = _as_dict(record.get('provenance'))
            status = str(provenance.get('status') or 'PROVENANCE_INCOMPLETE')
            if status not in summary:
                status = 'PROVENANCE_INCOMPLETE'
            summary[status]['count'] += 1
            summary[status]['fields_present'] = sorted(
                set(summary[status]['fields_present'])
                | {
                    field
                    for field in ('parent_record_id', 'source_unit_id', 'source_ids', 'locator')
                    if provenance.get(field)
                }
            )
            summary[status]['fields_missing'] = sorted(
                set(summary[status]['fields_missing'])
                | set(str(item) for item in provenance.get('missing_fields') or ())
            )
    return summary


def _dossier_summary(
    evidence: Mapping[str, list[dict[str, Any]]], abstention: bool
) -> dict[str, Any]:
    return {
        'included_claim_count': len(evidence.get('primary', []))
        + len(evidence.get('warning', [])),
        'primary_count': len(evidence.get('primary', [])),
        'warning_count': len(evidence.get('warning', [])),
        'audit_count': len(evidence.get('audit', [])),
        'rejected_count': len(evidence.get('rejected', [])),
        'abstention': abstention,
        'abstention_reason': (
            'Nessuna evidenza direttamente compatibile con il caso. Il sistema si astiene dal produrre conclusioni principali.'
            if abstention
            else None
        ),
        'narration_executed': False,
    }


def _with_pipeline_projection(function: Any) -> Any:
    def wrapped(outcome: RetrievalOutcome) -> dict[str, Any]:
        response = function(outcome)
        payload = outcome.payload
        evidence = response['evidence']
        technical = response['technical_records']
        summary = dict(response['summary'])
        summary['repository_version'] = outcome.repository_version
        abstention = bool(response['abstention'])
        gate_decisions = dict(getattr(payload, 'gate_decisions', {}) or {})
        provenance_summary = _provenance_summary(evidence)
        response['pipeline'] = {
            'stages': _pipeline_stages(
                payload, evidence, technical, summary, abstention
            ),
            'gate_summary': _gate_summary(
                list(getattr(payload, 'all_results', ()) or ()),
                [str(item) for item in gate_decisions.get('gate_execution_order', [])],
            ),
            'bucket_summary': _bucket_summary(evidence),
            'provenance_summary': provenance_summary,
            'dossier_summary': _dossier_summary(evidence, abstention),
        }
        response['pipeline']['stages'][5]['details']['status_counts'] = {
            status: item['count'] for status, item in provenance_summary.items()
        }
        return response

    return wrapped


@_with_pipeline_projection
def present_retrieval_outcome(outcome: RetrievalOutcome) -> dict[str, Any]:
    """Create the stable product response without changing native semantics."""
    payload = outcome.payload
    results = list(getattr(payload, "all_results", ()) or ())
    evidence: dict[str, list[dict[str, Any]]] = {
        "primary": [], "warning": [], "audit": [], "rejected": []
    }
    technical: dict[str, list[dict[str, Any]]] = {
        "provenance_containers": [],
        "unresolved_associations": [],
        "unsupported_associations": [],
        "deprecated_claims": [],
        "other": [],
    }
    native_query = _as_dict(getattr(payload, 'query', {}))
    for result in results:
        record = _claim_record(result, native_query, outcome.repository_version)
        kind = record["candidate_kind"]
        if kind == "evidence_claim":
            evidence[record["bucket"]].append(record)
        elif kind == "provenance_container":
            technical["provenance_containers"].append(
                _technical_record(result, native_query, outcome.repository_version)
            )
        elif kind == "unresolved_association":
            technical["unresolved_associations"].append(
                _technical_record(result, native_query, outcome.repository_version)
            )
        elif kind == "unsupported_association":
            technical["unsupported_associations"].append(
                _technical_record(result, native_query, outcome.repository_version)
            )
        elif kind == "deprecated_claim":
            technical["deprecated_claims"].append(
                _technical_record(result, native_query, outcome.repository_version)
            )
        else:
            technical["other"].append(
                _technical_record(result, native_query, outcome.repository_version)
            )
    claim_records = sum(len(items) for items in evidence.values())
    technical_count = sum(len(items) for items in technical.values())
    native_query = dict(getattr(payload, "query", {}) or {})
    case_context = dict(native_query.get("normalized") or native_query)
    gate_query = dict(case_context.get("gate_query") or {})
    for key, value in gate_query.items():
        case_context.setdefault(key, value)
    if native_query.get("original") is not None:
        case_context["original"] = dict(native_query.get("original") or {})
    return {
        "case_context": case_context,
        "summary": {
            "total_records": int(getattr(payload, "candidate_count", len(results)) or len(results)),
            "claim_records": claim_records,
            "technical_records": technical_count,
            "primary": len(evidence["primary"]),
            "warning": len(evidence["warning"]),
            "audit_claims": len(evidence["audit"]),
            "rejected_claims": len(evidence["rejected"]),
        },
        "evidence": evidence,
        "technical_records": technical,
        "abstention": not evidence["primary"] and not evidence["warning"],
        "metadata": {
            "backend_name": outcome.backend_name,
            "repository_version": outcome.repository_version,
            "policy_mode": outcome.policy_mode,
            "corpus_hash": str(getattr(payload, "corpus_hash", "")),
            "gate_version": str(getattr(payload, "gate_version", "")),
            "schema_version": str(getattr(payload, "schema_version", "")),
            "latency_ms": int(outcome.latency_ms),
            "latency_breakdown_ms": dict(getattr(payload, "latency_ms", {}) or {}),
            "run_id": str(getattr(payload, "run_id", "")),
            "pipeline_version": outcome.pipeline_version,
            "warnings": list(outcome.warnings),
            "gate_decisions": dict(getattr(payload, "gate_decisions", {}) or {}),
        },
    }


__all__ = ["present_retrieval_outcome"]
