"""Canonical Paper Reader caller for prompt/transport 4.5."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from jsonschema import Draft7Validator

from . import prompt_v3 as prompt
from . import transport as tr
from .canonical_normalizer import normalize_observed_relation


def _build_observed_relation(args: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    """Build the canonical relation from validated flat wire fields only."""
    subjects = []
    for index in range(1, 5):
        subject_type = args.get(f"subject_{index}_type")
        subject_value = args.get(f"subject_{index}_value")
        linked_gene = args.get(f"subject_{index}_linked_gene")
        # Empty strings are tolerated as omitted nullable fields, but a
        # whitespace-only value is malformed and must not enter the
        # canonical relation.
        for value in (subject_type, subject_value, linked_gene):
            if isinstance(value, str) and value != "" and not value.strip():
                return None, ["SUBJECT_SLOT_INVALID"]
        type_present = isinstance(subject_type, str) and bool(subject_type.strip())
        value_present = isinstance(subject_value, str) and bool(subject_value.strip())
        link_present = isinstance(linked_gene, str) and bool(linked_gene.strip())
        if link_present and not (type_present and value_present):
            return None, ["SUBJECT_SLOT_INVALID"]
        if type_present != value_present:
            return None, ["SUBJECT_SLOT_INVALID"]
        if type_present:
            subjects.append({"type": subject_type, "surface_value": subject_value,
                             "linked_gene": linked_gene})
    pairings = args.get("subject_pairings") or []
    if not isinstance(pairings, list) or any(
        not isinstance(item, dict) or not str(item.get("gene") or "").strip()
        or not str(item.get("alteration") or "").strip() for item in pairings
    ):
        return None, ["SUBJECT_PAIRINGS_INVALID"]
    caveats = args.get("caveats") or []
    conflicts = args.get("conflict_markers") or []
    if not isinstance(caveats, list) or not all(isinstance(item, str) and item.strip() for item in caveats):
        return None, ["CAVEATS_INVALID"]
    if not isinstance(conflicts, list) or not all(isinstance(item, str) and item.strip() for item in conflicts):
        return None, ["CONFLICT_MARKERS_INVALID"]
    trial = {key: args.get(key) for key in
             ("nct_id", "trial_name", "trial_phase", "trial_status", "trial_condition")
             if args.get(key) not in (None, "")}
    diagnostic = {key.removeprefix("companion_"): args.get(key) for key in (
        "companion_diagnostic_name", "companion_diagnostic_identifier",
        "companion_associated_gene", "companion_associated_drug",
        "companion_specimen", "companion_platform",
    ) if args.get(key) not in (None, "")}
    return {
        "disease": args.get("disease"),
        "subjects": subjects,
        "intervention": args.get("intervention"),
        "observed_stance": args.get("observed_stance") or "UNKNOWN",
        "effect_direction": args.get("effect_direction") or "UNKNOWN",
        "relation_scope": args.get("relation_scope") or "UNKNOWN",
        "molecular_composition": args.get("molecular_composition") or "UNKNOWN",
        "intervention_composition": args.get("intervention_composition") or "UNKNOWN",
        "relation_assertion": args.get("relation_assertion") or "RELATION_UNCERTAIN",
        "subject_pairings": pairings,
        "uncertainty": args.get("uncertainty"),
        "caveats": caveats,
        "conflict_markers": conflicts,
        "trial_context": trial,
        "companion_diagnostic": diagnostic,
        "evidence_context": {
            "subject_level": args.get("subject_level") or "UNKNOWN",
            "claim_type": args.get("claim_type") or "UNKNOWN",
        },
    }, []


def _transport(status: int | None, response: dict | None, error: str | None):
    if error or (status is not None and status >= 400):
        return "HTTP_ERROR", None, [error or f"HTTP_{status}"]
    calls = (((response or {}).get("choices") or [{}])[0].get("message") or {}).get("tool_calls") or []
    if len(calls) != 1 or (calls[0].get("function") or {}).get("name") != prompt.TOOL_NAME:
        return "INVALID_TOOL_CALL", None, ["EXPECTED_SINGLE_READER_TOOL_CALL"]
    raw = (calls[0].get("function") or {}).get("arguments")
    try:
        args = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return "INVALID_TOOL_ARGUMENTS", None, ["ARGUMENTS_NOT_JSON"]
    required = set(prompt.TOOL_SCHEMA["required"])
    if not isinstance(args, dict):
        return "INVALID_TOOL_ARGUMENTS", None, ["ARGUMENT_SHAPE_INVALID", "ARGUMENTS_NOT_OBJECT"]
    if not required.issubset(args):
        return "INVALID_TOOL_ARGUMENTS", None, ["ARGUMENT_SHAPE_INVALID", "REQUIRED_FIELDS_MISSING",
            *[f"REQUIRED_FIELD_MISSING:{key}" for key in sorted(required - set(args))]]
    if any(not isinstance(args[k], (str, dict, type(None))) for k in required):
        return "INVALID_TOOL_ARGUMENTS", None, ["ARGUMENT_SHAPE_INVALID", "REQUIRED_FIELD_TYPE_INVALID"]
    schema_errors = sorted(
        Draft7Validator(prompt.TOOL_SCHEMA).iter_errors(args),
        key=lambda item: list(item.path),
    )
    if schema_errors:
        reasons = ["NESTED_SCHEMA_VALIDATION_FAILED"]
        reasons.extend(
            f"{'.'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
            for error in schema_errors[:5]
        )
        return "INVALID_TOOL_ARGUMENTS", None, reasons
    if args["decision"] == "QUOTE":
        if not isinstance(args.get("quote"), str) or not isinstance(args.get("source_unit_id"), str):
            return "INVALID_TOOL_ARGUMENTS", None, ["QUOTE_FIELDS_REQUIRED_FOR_QUOTE"]
        if not args["quote"].strip() or not args["source_unit_id"].strip():
            return "INVALID_TOOL_ARGUMENTS", None, ["QUOTE_FIELDS_REQUIRED_FOR_QUOTE"]
        if args.get("abstain_reason") is not None:
            return "INVALID_TOOL_ARGUMENTS", None, ["ABSTAIN_REASON_PRESENT_DESPITE_QUOTE"]
    if args["decision"] == "ABSTAIN":
        semantic_fields = ("disease", "intervention", "observed_stance", "effect_direction",
                           "relation_scope", "molecular_composition", "intervention_composition", "subject_level", "claim_type", "relation_assertion",
                           "subject_pairings", "uncertainty", "caveats", "conflict_markers",
                           "nct_id", "trial_name", "trial_phase", "trial_status", "trial_condition",
                           "companion_diagnostic_name", "companion_diagnostic_identifier",
                           "companion_associated_gene", "companion_associated_drug",
                           "companion_specimen", "companion_platform")
        slot_fields = tuple(f"subject_{i}_{suffix}" for i in range(1, 5) for suffix in ("type", "value", "linked_gene"))
        if args.get("quote") is not None or args.get("source_unit_id") is not None \
                or any(args.get(field) is not None for field in (*semantic_fields, *slot_fields)):
            return "INVALID_TOOL_ARGUMENTS", None, ["ABSTAIN_FIELDS_PRESENT"]
        if args.get("abstain_reason") not in prompt.ABSTAIN_REASONS:
            return "INVALID_TOOL_ARGUMENTS", None, ["ABSTAIN_REASON_REQUIRED_FOR_ABSTAIN"]
    relation, relation_errors = _build_observed_relation(args) if args["decision"] == "QUOTE" else (None, [])
    if relation_errors:
        return "INVALID_TOOL_ARGUMENTS", None, relation_errors
    if relation is not None:
        args["observed_relation"] = normalize_observed_relation(relation)
    else:
        args["observed_relation"] = None
    if relation is not None:
        # Legacy fields are compatibility telemetry derived from the canonical
        # relation; they are never accepted as an independent source of truth.
        subjects = args["observed_relation"].get("subjects") or []
        args.update({
            "observed_disease": args["observed_relation"].get("disease") or "",
            "observed_gene": next((item["surface_value"] for item in subjects if item.get("type") == "GENE"), ""),
            "observed_alteration": next((item["surface_value"] for item in subjects if item.get("type") == "ALTERATION"), ""),
            "observed_drug": args["observed_relation"].get("intervention") or "",
            "observed_direction": args["observed_relation"].get("effect_direction") or "UNKNOWN",
            "observed_evidence_type": {
                "PREDICTIVE_ASSOCIATION": "PREDICTIVE",
                "PROGNOSTIC_ASSOCIATION": "PROGNOSTIC",
                "DIAGNOSTIC_ASSOCIATION": "DIAGNOSTIC",
                "FUNCTIONAL_EFFECT": "FUNCTIONAL",
            }.get(args["observed_relation"].get("evidence_context", {}).get("claim_type"), "UNKNOWN"),
        })
    for field in ("source_unit_id", "quote", "disease", "intervention", "notes", "abstain_reason",
                  "observed_stance", "effect_direction", "relation_scope", "subject_level", "claim_type"):
        args.setdefault(field, None)
    for index in range(1, 5):
        for suffix in ("type", "value", "linked_gene"):
            args.setdefault(f"subject_{index}_{suffix}", None)
    return "V3_TRANSPORT_VALID", {
        k: value.strip() if isinstance(value, str) else value for k, value in args.items()
    }, []


def build_reader_payload(case_context: dict[str, Any], candidate: dict[str, Any],
                         paper_id: str, source_units: list[dict[str, Any]],
                         run_index: int = 0) -> dict[str, Any]:
    """The exact transport request, also used as the run-local reuse identity."""
    messages = [
        {"role": "system", "content": prompt.SYSTEM_PROMPT},
        {"role": "user", "content": prompt.render_request(case_context, candidate, paper_id, source_units)},
    ]
    return tr.build_payload(prompt.TOOL_DEFINITION, prompt.TOOL_NAME, messages, seed=run_index, max_tokens=1400)


def call_enricher_v3(case_id: str, candidate_id: str, paper_id: str,
                     case_context: dict[str, Any], candidate: dict[str, Any],
                     source_units: list[dict[str, Any]], run_index: int = 0,
                     *, request_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = request_payload if request_payload is not None else build_reader_payload(
        case_context, candidate, paper_id, source_units, run_index)
    started = time.perf_counter()
    (status, response, error, retries), telemetry = tr.post_with_format_retry(
        payload, lambda status, body, error: _transport(status, body, error)[0])
    outcome, args, reasons = _transport(status, response, error)
    enrichment = None if args is None else {
        **args, "author_claim_quote": args["quote"], "candidate_id": candidate_id,
        "case_id": case_id, "paper_id": paper_id, "model": tr.model_name(),
        "prompt_version": prompt.PROMPT_VERSION, "transport_version": prompt.TRANSPORT_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return {
        "case_id": case_id, "candidate_id": candidate_id, "paper_id": paper_id,
        "model": tr.model_name(), "prompt_version": prompt.PROMPT_VERSION,
        "transport_version": prompt.TRANSPORT_VERSION, "transport_result": outcome,
        "transport_reason_codes": reasons, "enrichment": enrichment,
        "input_tokens": telemetry['input_tokens'], "output_tokens": telemetry['output_tokens'],
        "latency_ms": round((time.perf_counter() - started) * 1000, 3), "retry_count": retries,
        "model_call_count": telemetry['model_call_count'],
        "token_usage_complete": telemetry['token_usage_complete'],
        "format_attempts": telemetry['format_attempts'],
        "format_retry_budget_blocked": telemetry['format_retry_budget_blocked'],
    }
