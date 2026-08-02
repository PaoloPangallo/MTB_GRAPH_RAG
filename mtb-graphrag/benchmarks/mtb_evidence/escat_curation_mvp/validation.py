from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import ASSESSMENT_STATUSES, EscatAssessmentRecord, EscatRule, EscatRuleSet


ALLOWED_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"INCOMPLETE", "READY_FOR_REVIEW", "REJECTED", "CONFLICTING_EVIDENCE", "NOT_APPLICABLE"}),
    "INCOMPLETE": frozenset({"READY_FOR_REVIEW", "REJECTED", "CONFLICTING_EVIDENCE", "NOT_APPLICABLE"}),
    "READY_FOR_REVIEW": frozenset({"CURATED", "REJECTED", "CONFLICTING_EVIDENCE", "NOT_APPLICABLE"}),
    "CURATED": frozenset({"SUPERSEDED"}),
    "REJECTED": frozenset({"SUPERSEDED"}),
    "CONFLICTING_EVIDENCE": frozenset({"SUPERSEDED", "REJECTED"}),
    "NOT_APPLICABLE": frozenset({"SUPERSEDED", "REJECTED"}),
    "SUPERSEDED": frozenset(),
}


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {"valid": self.valid, "errors": list(self.errors), "warnings": list(self.warnings)}


def transition_status(current: str, target: str) -> None:
    if target not in ASSESSMENT_STATUSES:
        raise ValueError(f"unsupported assessment status: {target}")
    if target == "SUPERSEDED":
        raise ValueError("SUPERSEDED_REQUIRES_SUPERSEDE_COMMAND")
    if target not in ALLOWED_STATUS_TRANSITIONS.get(current, frozenset()):
        raise ValueError(f"invalid status transition: {current}->{target}")


def _value(record: EscatAssessmentRecord, field_name: str) -> Any:
    if field_name == "supporting_source":
        return record.supporting_sources
    if field_name == "supporting_passage":
        return record.supporting_passages
    return getattr(record, field_name, None)


def _condition_matches(record: EscatAssessmentRecord, condition: dict[str, Any]) -> bool:
    field_name = condition.get("field")
    value = _value(record, field_name) if field_name else None
    if "equals" in condition and value != condition["equals"]:
        return False
    if "not_equals" in condition and value == condition["not_equals"]:
        return False
    if "in" in condition and value not in condition["in"]:
        return False
    if condition.get("truthy") is True and not value:
        return False
    if "contains" in condition:
        if isinstance(value, (list, tuple, set)):
            if condition["contains"] not in value:
                return False
        elif condition["contains"] not in str(value):
            return False
    return True


def _source_token(source: dict[str, Any]) -> str | None:
    for key in ("source_id", "doi", "pmid", "source_path", "citation"):
        if source.get(key):
            return str(source[key])
    return None


def _rule_source_tokens(rule: EscatRule) -> set[str]:
    source = rule.source
    return {str(value) for key in ("doi", "pmid", "source_path", "citation", "locator") if (value := getattr(source, key))}


def _validate_rule(record: EscatAssessmentRecord, rule: EscatRule, ruleset: EscatRuleSet, errors: list[str]) -> None:
    if record.framework_version != ruleset.version or rule.framework_version != ruleset.version:
        errors.append("FRAMEWORK_VERSION_MISMATCH")
    if rule.source.framework != ruleset.framework or rule.source.version != ruleset.version:
        errors.append("RULE_SOURCE_FRAMEWORK_VERSION_MISMATCH")
    if record.tier != rule.tier:
        errors.append("TIER_RULE_MISMATCH")
    if record.subtier and record.subtier != rule.subtier:
        errors.append("SUBTIER_RULE_MISMATCH")
    if rule.subtier and not record.subtier:
        errors.append("MISSING_SUBTIER")
    for field_name in rule.required_fields:
        if not _value(record, field_name):
            errors.append(f"MISSING_REQUIRED_FIELD:{field_name}")
    for condition in rule.required_conditions:
        if not _condition_matches(record, condition):
            errors.append("REQUIRED_CONDITION_UNSATISFIED")
    if any(_condition_matches(record, condition) for condition in rule.exclusion_conditions):
        errors.append("EXCLUSION_CONDITION_MATCHED")
    if rule.alternative_conditions and not any(_condition_matches(record, condition) for condition in rule.alternative_conditions):
        errors.append("ALTERNATIVE_CONDITION_UNSATISFIED")
    if record.subtier and record.subtier in rule.subtier_requirements:
        for field_name in rule.subtier_requirements[record.subtier]:
            if not _value(record, field_name):
                errors.append("SUBTIER_REQUIREMENTS_INCOMPLETE")
    rule_sources = _rule_source_tokens(rule)
    if not rule_sources:
        errors.append("RULE_SOURCE_MISSING")
    if not record.supporting_sources:
        errors.append("MISSING_SUPPORTING_SOURCE")
    elif any(_source_token(source) in rule_sources for source in record.supporting_sources):
        errors.append("RULE_SOURCE_MUST_BE_DISTINCT")
    if record.supporting_sources and all((_source_token(source) or "").upper().startswith("PMID:") for source in record.supporting_sources) and not record.supporting_passages:
        errors.append("PMID_ALONE_INSUFFICIENT")


def validate_assessment(record: EscatAssessmentRecord, ruleset: EscatRuleSet) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    if record.framework != "ESCAT":
        errors.append("UNSUPPORTED_FRAMEWORK")
    if record.subtier and not record.tier:
        errors.append("SUBTIER_REQUIRES_TIER")
    if record.assessment_status == "CURATED" and not record.tier:
        errors.append("CURATED_REQUIRES_TIER")
    if record.assessment_status == "NOT_APPLICABLE" and record.tier:
        errors.append("NOT_APPLICABLE_CANNOT_HAVE_TIER")
    if record.tier:
        if not ruleset.available and not ruleset.is_test_fixture:
            errors.append("OFFICIAL_RULESET_NOT_AVAILABLE")
        if not ruleset.structurally_available:
            errors.append("RULESET_NOT_STRUCTURALLY_AVAILABLE")
        if ruleset.reference.framework != ruleset.framework or ruleset.reference.version != ruleset.version:
            errors.append("RULESET_REFERENCE_FRAMEWORK_VERSION_MISMATCH")
        if record.assessment_origin in {"LEGACY_DERIVED", "UNKNOWN"} or any("legacy" in item.casefold() for item in record.rule_ids):
            errors.append("LEGACY_OR_UNVERIFIED_TIER_NOT_ALLOWED")
        if record.assessment_status != "CURATED":
            errors.append("TIER_REQUIRES_CURATED_STATUS")
        for field_name in ("biomarker", "disease", "intervention"):
            if not getattr(record, field_name):
                errors.append(f"MISSING_REQUIRED_FIELD:{field_name}")
        if not record.framework_version:
            errors.append("MISSING_FRAMEWORK_VERSION")
        if not record.rule_ids:
            errors.append("MISSING_RULE_ID")
        selected = {rule.rule_id: rule for rule in ruleset.rules}
        for rule_id in record.rule_ids:
            rule = selected.get(rule_id)
            if rule is None:
                errors.append("RULE_ID_NOT_FOUND")
            else:
                _validate_rule(record, rule, ruleset, errors)
        if ruleset.is_test_fixture:
            warnings.append("TEST_FIXTURE_ONLY")
        if not record.rationale:
            errors.append("MISSING_RATIONALE")
        if not record.curator:
            errors.append("MISSING_CURATOR")
        if not record.curated_at:
            errors.append("MISSING_CURATED_AT")
    elif record.assessment_status in {"DRAFT", "INCOMPLETE", "READY_FOR_REVIEW"}:
        warnings.append("TIER_NOT_ASSIGNED")
    return ValidationResult(valid=not errors, errors=errors, warnings=warnings)
