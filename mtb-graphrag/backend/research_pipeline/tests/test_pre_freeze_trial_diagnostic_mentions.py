"""Parsed trial/diagnostic mentions must cross the same text and assertion gate."""

from __future__ import annotations

from backend.research_pipeline.casecontext.mentions import build_mentions
from backend.research_pipeline.casecontext.pipeline import build_retrieval_case_context
from backend.research_pipeline.casecontext.semantic_verifier import verify


def project(text: str, trials: list[dict], diagnostics: list[dict]) -> tuple[dict, list]:
    context = {
        "trial_mentions": trials,
        "companion_diagnostic_mentions": diagnostics,
    }
    mentions, _ = verify(build_mentions(context, text))
    return build_retrieval_case_context(context, mentions), mentions


def test_hallucinated_trial_and_diagnostic_cannot_reach_retrieval() -> None:
    projected, mentions = project(
        "EGFR mutation observed.",
        [{"nct_id": "NCT12345678", "nct_id_quote": "NCT12345678"}],
        [{"name": "Invented CDx", "name_quote": "Invented CDx"}],
    )
    assert projected["trial_mentions"] == []
    assert projected["companion_diagnostic_mentions"] == []
    assert len([m for m in mentions if m.entity_type in {"TRIAL", "COMPANION_DIAGNOSTIC"}]) == 2
    assert all(m.rejection_reason for m in mentions if m.entity_type in {"TRIAL", "COMPANION_DIAGNOSTIC"})


def test_negated_trial_and_diagnostic_cannot_reach_retrieval() -> None:
    projected, mentions = project(
        "No trial NCT12345678 is available. No Guardant360 CDx was used.",
        [{"nct_id": "NCT12345678", "nct_id_quote": "NCT12345678"}],
        [{"name": "Guardant360 CDx", "name_quote": "Guardant360 CDx"}],
    )
    assert projected["trial_mentions"] == []
    assert projected["companion_diagnostic_mentions"] == []
    assert all(m.assertion_status == "NEGATED" for m in mentions)


def test_grounded_positive_mentions_keep_fields_and_accounting() -> None:
    projected, mentions = project(
        "Trial NCT12345678 uses Guardant360 CDx for EGFR.",
        [{"nct_id": "NCT12345678", "nct_id_quote": "NCT12345678"}],
        [{"name": "Guardant360 CDx", "name_quote": "Guardant360 CDx",
          "associated_gene": "EGFR", "associated_gene_quote": "EGFR"}],
    )
    assert projected["trial_mentions"][0]["nct_id"] == "NCT12345678"
    assert projected["companion_diagnostic_mentions"][0]["associated_gene"] == "EGFR"
    relevant = [m for m in mentions if m.entity_type in {"TRIAL", "COMPANION_DIAGNOSTIC"}]
    assert len(relevant) == 2
    assert all(m.accepted_for_casecontext for m in relevant)


def test_fabricated_associated_gene_rejects_whole_diagnostic() -> None:
    projected, mentions = project(
        "Guardant360 CDx was used.", [],
        [{"name": "Guardant360 CDx", "name_quote": "Guardant360 CDx",
          "associated_gene": "KRAS", "associated_gene_quote": "KRAS"}],
    )
    assert projected["companion_diagnostic_mentions"] == []
    assert mentions[0].rejection_reason
