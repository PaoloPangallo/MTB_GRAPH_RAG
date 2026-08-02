from __future__ import annotations

from datetime import datetime, timezone

from benchmarks.mtb_evidence.escat_curation_mvp.models import (
    EscatAssessmentEvent,
    EscatAssessmentRecord,
    EscatCurationDraft,
    EscatFrameworkReference,
    EscatRule,
    EscatRuleSet,
)


def test_assessment_round_trip_preserves_separate_sources_and_passages() -> None:
    record = EscatAssessmentRecord(
        assessment_id="EA-1",
        claim_id="CLM-1",
        framework="ESCAT",
        assessment_status="INCOMPLETE",
        biomarker="EGFR L858R",
        disease="NSCLC",
        intervention="osimertinib",
        supporting_sources=[{"source_id": "PMID:1", "level": "document"}],
        supporting_passages=[{"text": "real local passage", "locator": "ABSTRACT"}],
        reason_codes=["OFFICIAL_RULESET_NOT_AVAILABLE"],
        missing_requirements=["framework_version", "rule_ids"],
        created_at=datetime(2026, 8, 2, tzinfo=timezone.utc),
    )

    restored = EscatAssessmentRecord.from_dict(record.to_dict())

    assert restored.to_dict() == record.to_dict()
    assert restored.supporting_sources != restored.supporting_passages
    assert restored.tier is None
    assert restored.subtier is None


def test_ruleset_without_local_source_is_explicitly_unavailable() -> None:
    reference = EscatFrameworkReference(framework="ESCAT")
    rule = EscatRule(rule_id="R-1", framework_version="unknown", tier="I-A")
    ruleset = EscatRuleSet(framework="ESCAT", version=None, reference=reference, rules=[])

    assert reference.available is False
    assert rule.to_dict()["tier"] == "I-A"
    assert ruleset.status == "OFFICIAL_RULESET_NOT_AVAILABLE"
    assert ruleset.available is False


def test_event_and_draft_are_distinct_from_assessment_record() -> None:
    record = EscatAssessmentRecord(
        assessment_id="EA-2",
        claim_id="CLM-2",
        framework="ESCAT",
        assessment_status="DRAFT",
    )
    draft = EscatCurationDraft(
        assessment=record,
        prefilled_fields={"biomarker": {"value": "ALK G1202R", "level": "claim"}},
        missing_requirements=["official_ruleset"],
    )
    event = EscatAssessmentEvent(
        event_id="EV-1",
        assessment_id="EA-2",
        timestamp=datetime(2026, 8, 2, tzinfo=timezone.utc),
        actor="test",
        action="DRAFT_CREATED",
        reason="fixture",
    )

    assert draft.to_dict()["assessment"]["assessment_id"] == "EA-2"
    assert event.to_dict()["action"] == "DRAFT_CREATED"
