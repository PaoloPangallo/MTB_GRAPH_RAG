from __future__ import annotations

from datetime import datetime, timezone

from benchmarks.mtb_evidence.escat_curation_mvp.models import (
    EscatAssessmentRecord,
    EscatFrameworkReference,
    EscatRuleSet,
)
from benchmarks.mtb_evidence.escat_curation_mvp.validation import validate_assessment


def unavailable_ruleset() -> EscatRuleSet:
    return EscatRuleSet(
        framework="ESCAT",
        version=None,
        reference=EscatFrameworkReference(framework="ESCAT"),
        rules=[],
    )


def test_tier_is_rejected_when_official_ruleset_is_unavailable() -> None:
    record = EscatAssessmentRecord(
        assessment_id="EA-1",
        claim_id="CLM-1",
        framework="ESCAT",
        assessment_status="CURATED",
        tier="I-A",
        biomarker="EGFR L858R",
        disease="NSCLC",
        intervention="osimertinib",
        rule_ids=["R-legacy"],
        supporting_sources=[{"source_id": "PMID:1"}],
        curator="human",
        curated_at=datetime(2026, 8, 2, tzinfo=timezone.utc),
        rationale="attempted legacy import",
    )

    result = validate_assessment(record, unavailable_ruleset())

    assert result.valid is False
    assert "OFFICIAL_RULESET_NOT_AVAILABLE" in result.errors
    assert "LEGACY_OR_UNVERIFIED_TIER_NOT_ALLOWED" in result.errors


def test_incomplete_draft_is_valid_without_tier() -> None:
    record = EscatAssessmentRecord(
        assessment_id="EA-2",
        claim_id="CLM-2",
        framework="ESCAT",
        assessment_status="INCOMPLETE",
        reason_codes=["OFFICIAL_RULESET_NOT_AVAILABLE"],
    )

    result = validate_assessment(record, unavailable_ruleset())

    assert result.valid is True
    assert result.errors == []


def test_subtier_requires_complete_rule_requirements() -> None:
    record = EscatAssessmentRecord(
        assessment_id="EA-3",
        claim_id="CLM-3",
        framework="ESCAT",
        assessment_status="READY_FOR_REVIEW",
        tier=None,
        subtier="A",
        missing_requirements=[],
    )

    result = validate_assessment(record, unavailable_ruleset())

    assert result.valid is False
    assert "SUBTIER_REQUIRES_TIER" in result.errors
