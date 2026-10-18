"""Static probes for narrative escalation; no narrator provider is invoked."""

from backend.research_pipeline.narrative.verifier import (
    _check_branch_semantics, _check_omissions, _check_recommendation,
)
from backend.research_pipeline.narrative.input_projection import build_narrator_input


def test_prescriptive_paraphrase_is_rejected() -> None:
    narrative = {"candidate_narratives": [{"candidate_id": "C", "text":
        "Erlotinib should be considered for treatment."}]}
    assert _check_recommendation(narrative)


def test_trial_efficacy_and_eligibility_paraphrases_are_rejected() -> None:
    candidate = {"candidate_id": "T", "branch": "TRIAL",
                 "trial_context": {"eligibility_status": "NOT_EVALUATED"}}
    assert _check_branch_semantics(candidate, "The trial demonstrated clinical benefit.")
    assert _check_branch_semantics(candidate, "The patient is eligible for enrollment.")


def test_kg_only_cannot_be_described_as_document_verified() -> None:
    candidate = {"candidate_id": "K", "branch": "KG_ONLY"}
    assert _check_branch_semantics(candidate, "The paper confirms this relation.")


def test_mixed_support_requires_explicit_conflict_in_narrative() -> None:
    candidate = {"candidate_id": "P", "branch": "PAPER",
                 "canonical_status": "PARTIAL_SUPPORT", "critical_warnings": [],
                 "contradiction_present": True}
    assert _check_omissions(candidate, "The relation has partial support.")
    assert not _check_omissions(candidate, "Evidence is conflicting; the relation has partial support.")


def test_conflict_flag_survives_canonical_narrator_projection() -> None:
    projected = build_narrator_input({"paper_evidence": [{
        "candidate_id": "P", "support_level": "PARTIAL_SUPPORT",
        "contradiction_present": True,
    }]})
    assert projected["candidates"][0]["contradiction_present"] is True
