from __future__ import annotations

from dataclasses import dataclass, field

from .models import EscatAssessmentRecord, EscatRuleSet


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def validate_assessment(
    record: EscatAssessmentRecord, ruleset: EscatRuleSet
) -> ValidationResult:
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
        if not ruleset.available:
            errors.append("OFFICIAL_RULESET_NOT_AVAILABLE")
        if record.assessment_origin in {"LEGACY_DERIVED", "UNKNOWN"} or any(
            "legacy" in item.casefold() for item in record.rule_ids
        ):
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
        if not record.supporting_sources:
            errors.append("MISSING_SUPPORTING_SOURCE")
        if not record.rationale:
            errors.append("MISSING_RATIONALE")
        if not record.curator:
            errors.append("MISSING_CURATOR")
        if not record.curated_at:
            errors.append("MISSING_CURATED_AT")
    elif record.assessment_status in {"DRAFT", "INCOMPLETE", "READY_FOR_REVIEW"}:
        warnings.append("TIER_NOT_ASSIGNED")

    if record.subtier and record.missing_requirements:
        errors.append("SUBTIER_REQUIREMENTS_INCOMPLETE")

    return ValidationResult(valid=not errors, errors=errors, warnings=warnings)
