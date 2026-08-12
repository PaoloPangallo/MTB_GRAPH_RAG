from __future__ import annotations

import json
import sys
import re
from pathlib import Path
from typing import Any


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _get(data: dict[str, Any], field: str) -> Any:
    value: Any = data
    for part in field.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def evaluate_expression(expression: dict[str, Any], observation: dict[str, Any]) -> bool:
    op = expression["op"]
    if op in {"AND", "OR", "ALL", "ANY"}:
        values = [evaluate_expression(item, observation) for item in expression["args"]]
        return all(values) if op in {"AND", "ALL"} else any(values)
    if op == "NOT":
        return not evaluate_expression(expression["arg"], observation)
    left = _get(observation, expression["field"])
    right = expression.get("value")
    if op == "EQ":
        return left == right
    if op == "NE":
        return left != right
    if op == "IN":
        return left in right
    if op == "NOT_IN":
        return left not in right
    if op == "EXISTS":
        return left is not None
    if op == "NOT_EXISTS":
        return left is None
    if op == "CALLED":
        return expression["stage_id"] in (left or [])
    if op == "NOT_CALLED":
        return expression["stage_id"] not in (left or [])
    if op == "ARTIFACT_EXISTS":
        return bool(left)
    raise ValueError(f"unsupported H01 operator: {op}")


_STAGE_PATH = re.compile(r"^stage\(([^)]+)\)\.(.+)$")
_KNOWN_STAGE_SUFFIXES = {
    "output.records[*].field",
    "output.verified_fields",
    "output.control_instruction_spans[*].reason_code",
    "output.verified_fields.target_intervention",
    "reason_codes[*]",
    "output.validations[*].outcome",
    "output.dossier.candidate_therapies[*].author_context[*]",
    "output.documents[*].document_id",
    "output.source_units[*].source_unit_id",
    "output.source_units[*].document_id",
    "output.selections[*].selected_papers[*].selected_source_unit_ids[*]",
    "output.narrative",
    "output.verification.status",
    "output.presentation_mode",
    "output.fallback_reason[*]",
}
_KNOWN_STAGE_VALUE_TYPES = {
    "output.records[*].field": "array<string>",
    "output.verified_fields": "object",
    "output.control_instruction_spans[*].reason_code": "array<string>",
    "output.verified_fields.target_intervention": "string|null",
    "reason_codes[*]": "array<string>",
    "output.validations[*].outcome": "array<string>",
    "output.dossier.candidate_therapies[*].author_context[*]": "array<object>",
    "output.documents[*].document_id": "array<string>",
    "output.source_units[*].source_unit_id": "array<string>",
    "output.source_units[*].document_id": "array<string>",
    "output.selections[*].selected_papers[*].selected_source_unit_ids[*]": "array<string>",
    "output.narrative": "string|null",
    "output.verification.status": "string|null",
    "output.presentation_mode": "string|null",
    "output.fallback_reason[*]": "array<string>",
}


def _read_path(raw: dict[str, Any], path: str) -> list[Any]:
    """Read the deliberately small stage()/output path grammar."""
    match = _STAGE_PATH.match(path)
    if not match:
        if path.startswith("challenge."):
            value: Any = raw.get("__challenge__", {})
            parts = path.split(".")[1:]
        else:
            raise ValueError(f"unsupported raw path: {path}")
    else:
        stages = raw.get("stages", {})
        if isinstance(stages, list):
            stages = {item.get("stage_id"): {
                "output": item.get("output_preview", {}),
                "reason_codes": item.get("reason_codes", []),
            } for item in stages if isinstance(item, dict)}
        value = stages.get(match.group(1))
        parts = match.group(2).split(".")
    values = [value]
    for part in parts:
        next_values: list[Any] = []
        wildcard = part.endswith("[*]")
        key = part[:-3] if wildcard else part
        for item in values:
            if not isinstance(item, dict):
                continue
            child = item.get(key)
            if wildcard:
                if isinstance(child, list):
                    next_values.extend(child)
            else:
                next_values.append(child)
        values = next_values
    return values


def _binding_values(raw: dict[str, Any], binding: dict[str, Any]) -> Any:
    values = _read_path(raw, binding["path"])
    norm = binding["normalization"]
    if norm == "IDENTITY":
        return values[0] if values else None
    if norm == "OBJECT_KEYS_EXACT":
        return sorted((values[0] or {}).keys()) if values and isinstance(values[0], dict) else []
    if norm == "SCALAR_TO_SET":
        if not values or values[0] is None:
            return []
        return list(values[0]) if isinstance(values[0], list) else [values[0]]
    if norm == "COLLECT_RECORDS":
        return [value for value in values if isinstance(value, dict)]
    flattened: list[Any] = []
    for value in values:
        if isinstance(value, list):
            flattened.extend(value)
        elif value is not None:
            flattened.append(value)
    return flattened


def _ref_value(ref: Any, derived: dict[str, Any], challenge: dict[str, Any]) -> Any:
    if isinstance(ref, dict) and "value" in ref:
        return ref["value"]
    if isinstance(ref, str):
        if ref.startswith("derived."):
            return derived.get(ref.split(".", 1)[1])
        if ref.startswith("challenge."):
            return challenge.get(ref.split(".", 1)[1])
    return ref


def evaluate_binding_expression(expression: dict[str, Any], derived: dict[str, Any], challenge: dict[str, Any]) -> bool:
    op = expression["op"]
    if op in {"AND", "OR", "ALL", "ANY"}:
        values = [evaluate_binding_expression(item, derived, challenge) for item in expression["args"]]
        return all(values) if op in {"AND", "ALL"} else any(values)
    if op == "NOT":
        return not evaluate_binding_expression(expression["arg"], derived, challenge)
    if op == "UNION":
        return sorted({item for ref in expression["args"] for item in (_ref_value(ref, derived, challenge) or [])})
    if op == "SET_INTERSECTION_NONEMPTY":
        left_ref = expression["left"]
        right_ref = expression["right"]
        left_value = (evaluate_binding_expression(left_ref, derived, challenge)
                      if isinstance(left_ref, dict) and left_ref.get("op") == "UNION"
                      else _ref_value(left_ref, derived, challenge))
        right_value = (evaluate_binding_expression(right_ref, derived, challenge)
                       if isinstance(right_ref, dict) and right_ref.get("op") == "UNION"
                       else _ref_value(right_ref, derived, challenge))
        left = set(left_value or [])
        right = set(right_value or [])
        return bool(left & right)
    if op == "ANY_RECORD_MATCH":
        records = _ref_value(expression["records"], derived, challenge) or []
        for record in records:
            if not isinstance(record, dict):
                continue
            matched = True
            for condition in expression["conditions"]:
                actual = record.get(condition["field"])
                if condition["op"] == "EQ":
                    matched = matched and actual == condition.get("value")
                elif condition["op"] == "IN":
                    matched = matched and actual in condition.get("value", [])
                elif condition["op"] == "IN_REF":
                    expected = _ref_value(condition["ref"], derived, challenge) or []
                    matched = matched and actual in expected
                else:
                    raise ValueError(f"unsupported record condition operator: {condition['op']}")
                if not matched:
                    break
            if matched:
                return True
        return False
    if op == "EQ":
        return _ref_value(expression["left"], derived, challenge) == _ref_value(expression["right"], derived, challenge)
    raise ValueError(f"unsupported raw binding operator: {op}")


def derive_observations(raw: dict[str, Any], challenge: dict[str, Any], contract: dict[str, Any]) -> dict[str, bool]:
    derived = {name: _binding_values(raw, spec) for name, spec in contract["bindings"].items()}
    derived["__challenge__"] = challenge
    observations: dict[str, bool] = {}
    for name, spec in contract["observations"].items():
        observations[name] = evaluate_binding_expression(spec["expression"], derived, challenge)
    return observations


def evaluate_eligibility(observed: str | None, expected: list[str] | None) -> str:
    if expected is None:
        return "SKIP"
    return "PASS" if observed in expected else "FAIL"


def validate_contract(root: Path) -> dict[str, Any]:
    normalization = _load(root / "heldout_normalization_contract.json")
    raw_binding = _load(root / "raw_observation_binding_contract.json")
    hard = _load(root / "hard_observable_contract.json")
    null_policy = _load(root / "null_policy.json")
    vectors = _load(root / "test_vectors.json")
    gold_path = root.parents[2] / "evaluation" / "final_protocol" / "heldout" / "architectural_challenge_gold.json"
    gold = _load(gold_path)["gold"]
    repo = root.parents[2]
    sys.path.insert(0, str(repo))
    from backend.research_pipeline.contracts import STAGE_SEQUENCE  # type: ignore
    expected_states = {row["expected_run_state"] for row in gold}
    predicates = normalization["gold_expectation_predicates"]["run_state"]
    hard_ids = {row["hard_property"] for row in gold if row.get("hard_property")}
    observed_vocab = set(normalization["observed_runtime"]["eligibility_vocabulary"])
    expected_eligibility = {token for row in gold for token in (row.get("expected_eligibility") or [])}
    stop_vocab = set(normalization["observed_runtime"]["stop_stage"]["vocabulary"])
    runtime_stage_vocab = list(STAGE_SEQUENCE)
    expected_stops = {row["expected_stop_stage"] for row in gold if row.get("expected_stop_stage")}
    forbidden_vocab = set(normalization["observed_runtime"]["forbidden_calls"]["vocabulary"])
    expected_forbidden = {token for row in gold for token in (row.get("expected_forbidden_calls") or [])}
    polarity_vocab = set(normalization["observed_runtime"]["polarity"]["tokens"])
    expected_polarity = {row["expected_polarity_behavior"] for row in gold if row.get("expected_polarity_behavior")}
    case_ids = {row["case_id"] for row in gold}
    vector_ids = {row["case_id"] for row in vectors["case_vectors"]}
    unmapped = sorted(
        (expected_states - set(predicates))
        | (expected_eligibility - observed_vocab)
        | (expected_stops - stop_vocab)
        | (expected_forbidden - forbidden_vocab)
        | (expected_polarity - polarity_vocab)
    )
    undefined = sorted(hard_ids - set(hard["observables"]))
    prose_only = list(hard.get("prose_only_observables", []))
    gold_fields = {
        "expected_eligibility", "expected_retrieval_allowed", "expected_stop_stage",
        "expected_forbidden_calls", "expected_polarity_behavior",
        "expected_canonical_artifact_allowed", "expected_run_state",
    }
    missing_null = sorted(field for field in gold_fields if field not in null_policy["fields"])
    ambiguous = []
    if case_ids != vector_ids:
        ambiguous.append("case_vector_identity")
    if normalization["observed_runtime"]["run_state_normalization"]["unknown_status"] != "INCOMPLETE":
        ambiguous.append("unknown_run_state")
    if runtime_stage_vocab != normalization["observed_runtime"].get("stage_vocabulary"):
        ambiguous.append("runtime_stage_vocabulary_mismatch")
    if normalization["observed_runtime"]["canonical_artifact"].get("stage_id") != "stage_13_dossier":
        ambiguous.append("canonical_artifact_stage")
    if "document_limit_reached" in json.dumps(normalization["gold_expectation_predicates"]["run_state"]):
        ambiguous.append("synthetic_document_limit_observation")
    derivations = normalization.get("raw_derivations", {})
    required_derivations = {"authority_transfer", "unauthorized_field", "unvalidated_quote", "injected_provenance", "presentation_drift"}
    missing_derivations = sorted(required_derivations - set(derivations))
    unexplained = sorted(
        observable for observable, spec in hard["observables"].items()
        if "raw_derivation" not in spec or not spec.get("source_fields")
    )
    binding_stage_ids = {
        match.group(1) for spec in raw_binding["bindings"].values()
        if (match := _STAGE_PATH.match(spec["path"]))
    }
    invalid_raw_paths = sorted(binding_stage_ids - set(runtime_stage_vocab))
    invalid_raw_paths.extend(
        sorted({spec["path"] for spec in raw_binding["bindings"].values()
                if (match := _STAGE_PATH.match(spec["path"])) and match.group(2) not in _KNOWN_STAGE_SUFFIXES}))
    invalid_raw_paths.extend(
        sorted({spec["path"] for spec in raw_binding["bindings"].values()
                if (match := _STAGE_PATH.match(spec["path"]))
                and _KNOWN_STAGE_VALUE_TYPES.get(match.group(2)) != spec.get("value_type")}))
    invalid_raw_paths = sorted(set(invalid_raw_paths))
    required_observations = {
        field.split(".", 1)[1] for spec in hard["observables"].values()
        for field in spec["source_fields"] if field.startswith("observations.")
    }
    missing_binding_observations = sorted(required_observations - set(raw_binding["observations"]))
    raw_path_total = sum(1 for spec in raw_binding["bindings"].values() if "path" in spec)
    raw_path_validated = raw_path_total - len(invalid_raw_paths)
    challenge_path_total = sum(len(spec.get("challenge_paths", [])) for spec in raw_binding["observations"].values())
    return {
        "cases_resolved": len(case_ids) if not (unmapped or undefined or missing_null or ambiguous or missing_derivations or unexplained or invalid_raw_paths or missing_binding_observations) else 0,
        "unmapped_tokens": unmapped,
        "undefined_predicates": undefined,
        "prose_only_observables": prose_only,
        "missing_null_policies": missing_null,
        "ambiguous_rules": ambiguous,
        "runtime_stage_count": len(runtime_stage_vocab),
        "phantom_stages": sorted(stop_vocab - set(runtime_stage_vocab)),
        "undefined_raw_derivations": missing_derivations,
        "unexplained_observable_leaves": unexplained,
        "invalid_raw_paths": invalid_raw_paths,
        "missing_binding_observations": missing_binding_observations,
        "raw_path_total": raw_path_total,
        "raw_path_validated": raw_path_validated,
        "challenge_path_total": challenge_path_total,
        "gold_case_count": len(gold),
        "semantic_vector_count": len(vectors["semantic_vectors"]),
        "raw_observable_vector_count": len(vectors.get("raw_observable_vectors", [])),
    }


if __name__ == "__main__":
    result = validate_contract(Path(__file__).parent)
    print(json.dumps(result, sort_keys=True))
