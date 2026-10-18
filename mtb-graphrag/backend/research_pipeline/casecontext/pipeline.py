"""Catena deterministica fra il parser e il retrieval.

Un solo punto di ingresso per: menzioni tipizzate → verifica semantica →
contraddizioni → eligibility gate. Nessun LLM è coinvolto in nessuno di questi
passi.

Serve sia all'orchestratore sia all'harness di valutazione, che devono eseguire
**esattamente la stessa** catena: duplicarla renderebbe il benchmark una misura
di un'altra pipeline.
"""

from __future__ import annotations

from typing import Any

from ..eligibility.gate import EligibilityDecision, evaluate as evaluate_gate
from . import match_verifier
from .contradictions import detect as detect_contradictions
from .control_instructions import detect_control_instruction_spans
from .mentions import build_mentions, to_contract
from .semantic_verifier import verify as verify_semantics

DETERMINISTIC_CHAIN_VERSION = "casecontext-deterministic-chain/1.0"


def projection_audit(
    case_context: dict[str, Any], mentions: list[Any], projected: dict[str, Any],
) -> dict[str, Any]:
    """Account for every extracted mention at the retrieval boundary.

    This is deliberately a report helper, not a retrieval rule.  A fact is
    either visible in the projected contract or carries an explicit rejection
    reason from the deterministic chain; accepted facts disappearing here are
    reported as unexplained loss.
    """
    def get(item: Any, key: str, default: Any = None) -> Any:
        if isinstance(item, dict):
            return item.get(key, default)
        return getattr(item, key, default)

    projected_text = repr(projected).casefold()
    facts: list[dict[str, Any]] = []
    for mention in mentions:
        raw = str(get(mention, "raw_text", "") or "")
        if not raw:
            continue
        accepted = get(mention, "accepted_for_casecontext") is True
        slot = str(get(mention, "slot", "") or "")
        available = raw.casefold() in projected_text if accepted else False
        if accepted and available:
            status, reason = "AVAILABLE_TO_RETRIEVAL", None
        elif accepted:
            status, reason = "UNEXPLAINED_VALIDATED_FACT_LOSS", "NOT_IN_PROJECTED_CONTEXT"
        else:
            status, reason = "REJECTED_WITH_REASON", get(mention, "rejection_reason")
        facts.append({
            "slot": slot,
            "raw_value": raw,
            "quote": (get(mention, "source_span") or {}).get("quote")
            if isinstance(get(mention, "source_span"), dict) else None,
            "parsed": True,
            "validated": accepted,
            "status": status,
            "rejection_reason": reason,
        })
    unexplained = sum(item["status"] == "UNEXPLAINED_VALIDATED_FACT_LOSS" for item in facts)
    return {
        "facts": facts,
        "unexplained_validated_fact_loss": unexplained,
        "validated_fact_count": sum(item["validated"] for item in facts),
        "available_to_retrieval_count": sum(item["status"] == "AVAILABLE_TO_RETRIEVAL" for item in facts),
        "rejected_with_reason_count": sum(item["status"] == "REJECTED_WITH_REASON" for item in facts),
    }


def validate_minimal_case_context(case_context: dict[str, Any] | None) -> dict[str, Any]:
    """Intent-aware admission based only on explicit usable anchors.

    Disease is contextual: it may improve retrieval, but is not universally
    required.  The gate never invents a missing disease or intervention.
    """
    if not isinstance(case_context, dict):
        return {"valid": False, "run_status": "INVALID_CASE_CONTEXT", "missing": ["case_context"]}
    biomarkers = case_context.get("biomarkers") or []
    molecular_anchor = any(
        item.get("gene") or item.get("alteration") or item.get("normalized_value") or item.get("raw_value")
        for item in biomarkers if isinstance(item, dict)
    )
    target = case_context.get("target_intervention")
    interventions = [target, *(case_context.get("previous_interventions") or [])]
    intervention_anchor = any(
        isinstance(item, dict) and (item.get("normalized_value") or item.get("raw_value"))
        for item in interventions
    )
    missing = []
    if not molecular_anchor and not intervention_anchor:
        missing.append("clinical_anchor")
    if case_context.get("query_intent") == "THERAPY_EVALUATION" and not (
        isinstance(target, dict) and (target.get("normalized_value") or target.get("raw_value"))
    ):
        missing.append("target_intervention")
    return {
        "valid": not missing,
        "run_status": "COMPLETED" if not missing else "INSUFFICIENT_CASE_CONTEXT",
        "missing": missing,
        "ambiguities": list(case_context.get("uncertainties") or []),
    }


def build_retrieval_case_context(
    case_context: dict[str, Any], mentions: list[Any],
) -> dict[str, Any]:
    """Project only accepted clinical mentions into the retriever contract.

    The retriever still receives its existing dictionary shape, but rejected
    parser values are never copied back into the query projection.
    """
    projected = dict(case_context or {})

    def value(mention: Any, key: str, default: Any = None) -> Any:
        if isinstance(mention, dict):
            return mention.get(key, default)
        return getattr(mention, key, default)

    def accepted(slot: str, *entity_types: str) -> list[Any]:
        return [
            mention for mention in mentions
            if value(mention, "slot") == slot
            and value(mention, "accepted_for_casecontext") is True
            and (not entity_types or value(mention, "entity_type") in entity_types)
        ]

    def structured_value(mention: Any) -> dict[str, Any]:
        raw = value(mention, "raw_text", "")
        normalized = value(mention, "normalized_value") or raw
        result = {"raw_value": raw, "normalized_value": normalized}
        span = value(mention, "source_span")
        if span:
            result["source_spans"] = [span]
        return result

    disease = accepted("disease", "DISEASE")
    projected["diseases"] = [
        {
            **structured_value(m),
            "clinical_role": value(m, "semantic_role", "PRIMARY"),
            "assertion_status": value(m, "assertion_status", "UNKNOWN"),
        }
        for m in disease
    ]
    current_disease = next(
        (item for item in projected["diseases"]
         if str(item["clinical_role"]).upper() not in {"HISTORY", "DIFFERENTIAL", "UNCERTAIN"}
         and str(item["assertion_status"]).upper() in {"ASSERTED", "PRESENT", "CURRENT"}),
        None,
    )
    projected["disease"] = current_disease

    def assertion_status(mention: Any) -> str:
        status = str(value(mention, "assertion_status", "UNKNOWN") or "UNKNOWN").upper()
        return {
            "ASSERTED": "PRESENT", "HYPOTHETICAL": "UNCERTAIN",
        }.get(status, status)

    accepted_genes = {
        str(value(m, "raw_text", "")).casefold(): m
        for m in accepted("biomarker", "GENE", "BIOMARKER")
    }
    accepted_alterations = {
        str(value(m, "raw_text", "")).casefold(): m
        for m in accepted("alteration", "ALTERATION")
    }
    negated_mentions = {
        (str(value(m, "entity_type", "")).upper(), str(value(m, "raw_text", "")).casefold())
        for m in mentions
        if str(value(m, "assertion_status", "")).upper() == "NEGATED"
        and value(m, "slot") in {"biomarker", "alteration"}
    }
    biomarkers: list[dict[str, Any]] = []
    negated_biomarkers: list[dict[str, Any]] = []
    source_biomarkers = case_context.get("biomarkers") or []
    if source_biomarkers:
        for source in source_biomarkers:
            gene = source.get("gene")
            alteration = source.get("alteration")
            if (("GENE", str(gene or "").casefold()) in negated_mentions
                    or ("ALTERATION", str(alteration or "").casefold()) in negated_mentions):
                negated_biomarkers.append({"gene": gene, "alteration": alteration})
                continue
            gene_mention = accepted_genes.get(str(gene or "").casefold())
            alteration_mention = accepted_alterations.get(str(alteration or "").casefold())
            if gene and alteration and source.get("pair_grounded") is not True:
                alteration_mention = None
            if not gene_mention and not alteration_mention:
                continue
            item: dict[str, Any] = {
                "gene": gene if gene_mention else None,
                "alteration": alteration if alteration_mention else None,
                "alteration_type": source.get("alteration_type"),
                "assertion_status": assertion_status(alteration_mention or gene_mention),
                "clinical_role": source.get("clinical_role") or "PRIMARY",
                "raw_value": " ".join(str(value) for value in (gene if gene_mention else None, alteration if alteration_mention else None) if value),
                "normalized_value": " ".join(str(value) for value in (gene if gene_mention else None, alteration if alteration_mention else None) if value),
                "source_spans": source.get("source_spans") or [],
            }
            if gene_mention and alteration_mention:
                item["pair_source_span"] = source.get("pair_source_span")
            if gene_mention:
                item["gene_quote"] = value(gene_mention, "raw_text", "")
            if alteration_mention:
                item["alteration_quote"] = value(alteration_mention, "raw_text", "")
            biomarkers.append(item)
    else:
        # Legacy contexts without paired observations remain readable.
        for mention in accepted("biomarker", "GENE", "BIOMARKER"):
            item = structured_value(mention)
            item.update({"gene": value(mention, "raw_text", ""), "alteration": None,
                         "assertion_status": assertion_status(mention)})
            biomarkers.append(item)
        for mention in accepted("alteration", "ALTERATION"):
            item = structured_value(mention)
            item.update({"gene": None, "alteration": value(mention, "raw_text", ""),
                         "assertion_status": assertion_status(mention)})
            biomarkers.append(item)
    projected["biomarkers"] = biomarkers
    projected["negated_biomarkers"] = negated_biomarkers

    intervention_mentions = accepted("target_intervention", "INTERVENTION") + accepted(
        "previous_intervention", "INTERVENTION") + accepted("intervention", "INTERVENTION")
    projected["interventions"] = [
        {
            **structured_value(m),
            "name": value(m, "raw_text", ""),
            "role": {
                "TARGET_INTERVENTION": "TARGET",
                "PREVIOUS_INTERVENTION": "PREVIOUS",
            }.get(value(m, "semantic_role", "UNKNOWN"), value(m, "semantic_role", "UNKNOWN")),
            "assertion_status": assertion_status(m),
        }
        for m in intervention_mentions
    ]
    previous = accepted("previous_intervention", "INTERVENTION")
    projected["previous_interventions"] = [structured_value(m) for m in previous]
    target = accepted("target_intervention", "INTERVENTION")
    projected["target_intervention"] = structured_value(target[0]) if target else None
    projected["target_interventions"] = [
        structured_value(m) for m in intervention_mentions
        if value(m, "semantic_role", "") in {"TARGET_INTERVENTION", "CURRENT_INTERVENTION"}
    ]

    for source_key, mention_slot in (
        ("trial_mentions", "trial_mention"),
        ("companion_diagnostic_mentions", "companion_diagnostic_mention"),
    ):
        source_items = list(case_context.get(source_key) or [])
        verified_mentions = [m for m in mentions if value(m, "slot") == mention_slot]
        projected[source_key] = [
            dict(item) for item, mention in zip(source_items, verified_mentions)
            if isinstance(item, dict)
            and value(mention, "accepted_for_casecontext") is True
            and assertion_status(mention) == "PRESENT"
        ]
    return projected


def _mention_accounting(mentions: list[Any]) -> dict[str, dict[str, Any]]:
    """Reconcile every typed mention before the retrieval projection."""
    categories = {
        "DISEASE": "disease", "GENE": "biomarker", "ALTERATION": "biomarker",
        "BIOMARKER": "biomarker", "INTERVENTION": "intervention",
        "TRIAL": "trial", "COMPANION_DIAGNOSTIC": "companion_diagnostic",
    }
    output = {category: {"parsed": 0, "accepted": 0, "rejected": 0,
                         "used": [], "excluded": [],
                         "retrieval_used": [], "retrieval_excluded": []}
              for category in dict.fromkeys(categories.values())}
    for mention in mentions:
        item = mention if isinstance(mention, dict) else mention.to_dict()
        category = categories.get(str(item.get("entity_type") or ""))
        if not category:
            continue
        row = output[category]
        row["parsed"] += 1
        trace = {"slot": item.get("slot"), "raw_text": item.get("raw_text"),
                 "assertion_status": item.get("assertion_status")}
        if item.get("accepted_for_casecontext") is True:
            row["accepted"] += 1
            row["used"].append(trace)
            if category in {"trial", "companion_diagnostic"} and item.get("assertion_status") != "ASSERTED":
                row["retrieval_excluded"].append({**trace, "reason": "ASSERTION_NOT_POSITIVE"})
            else:
                row["retrieval_used"].append(trace)
        else:
            row["rejected"] += 1
            excluded = {**trace, "reason": item.get("rejection_reason") or "NOT_ACCEPTED"}
            row["excluded"].append(excluded)
            row["retrieval_excluded"].append(excluded)
    return output


def run(
    clinical_text: str,
    case_context: dict[str, Any] | None,
    transport_ok: bool = True,
) -> dict[str, Any]:
    """Esegue la catena deterministica completa.

    ``case_context`` è l'output grezzo del parser (contratto 1.0). Restituisce
    il CaseContext 2.0, i record di verifica e la decisione del gate.
    """
    text = clinical_text or ""
    control_spans = detect_control_instruction_spans(text)

    if not isinstance(case_context, dict):
        decision = evaluate_gate(text, None, [], control_spans, [], transport_ok=False)
        return {
            "contract_version": DETERMINISTIC_CHAIN_VERSION,
            "case_context_v2": None,
            "mentions": [],
            "mention_accounting": _mention_accounting([]),
            "textual_records": [],
            "semantic_records": [],
            "contradictions": [],
            "control_instruction_spans": control_spans,
            "eligibility": decision.to_dict(),
        }

    # A — verifica testuale, invariata: resta il gate di letteralità.
    textual = match_verifier.verify_case_context(case_context, text)
    textual_ok, textual_warnings = match_verifier.essential_fields_pass(textual)

    # Menzioni tipizzate + verifica semantica (tipo, ruolo, asserzione).
    mentions = build_mentions(case_context, text, control_spans)
    mentions, semantic_records = verify_semantics(mentions)

    # Contraddizioni deterministiche.
    contradictions = detect_contradictions(text, mentions, case_context, control_spans)

    decision = evaluate_gate(
        text, case_context, mentions, control_spans, contradictions,
        transport_ok=transport_ok,
    )
    if not textual_ok and decision.eligible:
        # La verifica testuale conserva il potere di veto: un mismatch letterale
        # non può essere superato da una verifica semantica favorevole.
        decision = evaluate_gate(text, case_context, [], control_spans, contradictions,
                                 transport_ok=transport_ok)
        decision.reason_codes = ["TEXTUAL_MATCH_VERIFIER_MISMATCH"] + decision.reason_codes

    return {
        "contract_version": DETERMINISTIC_CHAIN_VERSION,
        "case_context_v2": to_contract(
            case_context, mentions, control_spans,
            [c.to_dict() for c in contradictions]),
        "mentions": [m.to_dict() for m in mentions],
        "mention_accounting": _mention_accounting(mentions),
        "textual_records": [r.to_dict() for r in textual],
        "textual_essential_pass": textual_ok,
        "textual_warnings": list(textual_warnings),
        "semantic_records": semantic_records,
        "contradictions": [c.to_dict() for c in contradictions],
        "control_instruction_spans": control_spans,
        "eligibility": decision.to_dict(),
    }
