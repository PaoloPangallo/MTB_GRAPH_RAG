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
    return {
        "disease": args.get("disease"),
        "subjects": subjects,
        "intervention": args.get("intervention"),
        "observed_stance": args.get("observed_stance") or "UNKNOWN",
        "effect_direction": args.get("effect_direction") or "UNKNOWN",
        "relation_scope": args.get("relation_scope") or "UNKNOWN",
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
    if not isinstance(args, dict) or not required.issubset(args) or any(
            not isinstance(args[k], (str, dict, type(None))) for k in required):
        return "INVALID_TOOL_ARGUMENTS", None, ["ARGUMENT_SHAPE_INVALID"]
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
                           "relation_scope", "subject_level", "claim_type")
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


def call_enricher_v3(case_id: str, candidate_id: str, paper_id: str,
                     case_context: dict[str, Any], candidate: dict[str, Any],
                     source_units: list[dict[str, Any]], run_index: int = 0) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": prompt.SYSTEM_PROMPT},
        {"role": "user", "content": prompt.render_request(case_context, candidate, paper_id, source_units)},
    ]
    payload = tr.build_payload(prompt.TOOL_DEFINITION, prompt.TOOL_NAME, messages, seed=run_index, max_tokens=1400)
    started = time.perf_counter()
    status, response, error, retries = tr.post_with_infra_retry(payload)
    outcome, args, reasons = _transport(status, response, error)
    enrichment = None if args is None else {
        **args, "author_claim_quote": args["quote"], "candidate_id": candidate_id,
        "case_id": case_id, "paper_id": paper_id, "model": tr.model_name(),
        "prompt_version": prompt.PROMPT_VERSION, "transport_version": prompt.TRANSPORT_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    usage = (response or {}).get("usage") or {}
    return {
        "case_id": case_id, "candidate_id": candidate_id, "paper_id": paper_id,
        "model": tr.model_name(), "prompt_version": prompt.PROMPT_VERSION,
        "transport_version": prompt.TRANSPORT_VERSION, "transport_result": outcome,
        "transport_reason_codes": reasons, "enrichment": enrichment,
        "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
        "latency_ms": round((time.perf_counter() - started) * 1000, 3), "retry_count": retries,
    }
