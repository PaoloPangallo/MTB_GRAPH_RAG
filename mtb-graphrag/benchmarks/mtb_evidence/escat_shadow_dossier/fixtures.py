from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from benchmarks.mtb_evidence.escat_curation_mvp.models import EscatAssessmentRecord, EscatRuleSet


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "escat_curation_mvp" / "test_fixture_ruleset.json"
FIXTURE_DATE = datetime(2026, 8, 2, tzinfo=timezone.utc)


def fixture_ruleset() -> EscatRuleSet:
    return EscatRuleSet.from_dict(json.loads(FIXTURE_PATH.read_text(encoding="utf-8")))


def fixture_curated_record(claim_id: str = "CASE-FIXTURE-CURATED") -> EscatAssessmentRecord:
    return EscatAssessmentRecord(
        assessment_id="EA-FIXTURE-CURATED",
        claim_id=claim_id,
        assessment_status="CURATED",
        framework_version="TEST-1",
        tier="TEST-TIER-1",
        subtier="A",
        biomarker="BRAF V600E",
        disease="TEST DISEASE",
        intervention="TEST DRUG",
        direction="sensitivity",
        tumour_context_relation="same_tumour",
        study_design="prospective",
        outcome_basis=["response"],
        supporting_sources=[{"source_id": "SU-fixture-support"}],
        supporting_passages=[{"text": "fixture passage", "locator": "p.1"}],
        rule_ids=["TEST-R1"],
        rationale="TEST_FIXTURE_ONLY; NOT_A_CLINICAL_ESCAT_ASSESSMENT",
        curator="fixture-curator",
        curated_at=FIXTURE_DATE,
        created_at=FIXTURE_DATE,
    )


def fixture_not_applicable_record() -> EscatAssessmentRecord:
    return EscatAssessmentRecord(
        assessment_id="EA-FIXTURE-NOT-APPLICABLE",
        claim_id="CLM-8941c177da91f66ff93a",
        assessment_status="NOT_APPLICABLE",
        reason_codes=["EXPLICIT_ASSESSMENT_STATE_FIXTURE"],
        rationale="Explicit technical presentation example only.",
        created_at=FIXTURE_DATE,
    )


def fixture_superseded_record() -> EscatAssessmentRecord:
    return EscatAssessmentRecord(
        assessment_id="EA-FIXTURE-SUPERSEDED",
        claim_id="CASE-FIXTURE-SUPERSEDED",
        assessment_status="SUPERSEDED",
        reason_codes=["EXPLICIT_FIXTURE_HISTORY"],
        created_at=FIXTURE_DATE,
    )


def fixture_conflicting_records() -> list[EscatAssessmentRecord]:
    return [
        EscatAssessmentRecord(
            assessment_id="EA-FIXTURE-CONFLICT-A",
            claim_id="CASE-FIXTURE-CONFLICT",
            assessment_status="INCOMPLETE",
            created_at=FIXTURE_DATE,
        ),
        EscatAssessmentRecord(
            assessment_id="EA-FIXTURE-CONFLICT-B",
            claim_id="CASE-FIXTURE-CONFLICT",
            assessment_status="REJECTED",
            rationale="Technical conflict example only.",
            created_at=FIXTURE_DATE,
        ),
    ]
