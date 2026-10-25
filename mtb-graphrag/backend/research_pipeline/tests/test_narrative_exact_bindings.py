"""Regression tests for literal, candidate-scoped narrative authorization."""
import pytest

from backend.research_pipeline.narrative.verifier import verify_narrative, _check_branch_semantics

QUOTE = "The source describes a narrowly defined observation."
OTHER = "Another source describes a distinct clinical observation."


def projection(branch="PAPER"):
    def candidate(cid, quote, paper):
        return {"candidate_id": cid, "branch": branch, "canonical_status": "DIRECT",
                "support_direction": "SUPPORTED", "expresses_support": True,
                "validated_quotes": [{"quote": quote, "paper_id": paper}],
                "selected_paper_ids": [paper], "warnings": []}
    return {"candidates": [candidate("P1", QUOTE, "pmid:1234"),
                           candidate("P2", OTHER, "pmid:5678")]}


def result(text, summary="", branch="PAPER"):
    return verify_narrative({}, projection(branch), {
        "candidate_narratives": [{"candidate_id": "P1", "text": text},
                                 {"candidate_id": "P2", "text": "Descrizione."}],
        "narrative_summary": summary})


@pytest.mark.parametrize("quote", [QUOTE + " Added unsupported content.", QUOTE.lower(),
                                    QUOTE.replace(".", "!"), OTHER, QUOTE[:-1]])
def test_modified_or_borrowed_quotes_are_rejected(quote):
    assert "NARRATIVE_UNAUTHORIZED_QUOTE" in result(f'Fonte: "{quote}".')['reason_codes']


def test_complete_candidate_quote_is_authorized():
    assert "NARRATIVE_UNAUTHORIZED_QUOTE" not in result(f'Fonte: "{QUOTE}".')['reason_codes']


@pytest.mark.parametrize("identifier", ["PMID:12345", "PMID:5678", "PMID:123456789012", "NCT123456789"])
def test_identifiers_require_exact_candidate_binding(identifier):
    assert "NARRATIVE_UNAUTHORIZED_ENTITY" in result(f"Fonte {identifier}.")['reason_codes']


def test_global_identifiers_allow_union_but_not_prefixes():
    assert "NARRATIVE_UNAUTHORIZED_ENTITY" not in result("Descrizione.", "Fonte PMID:5678.")['reason_codes']
    assert "NARRATIVE_UNAUTHORIZED_ENTITY" in result("Descrizione.", "Fonte PMID:12345.")['reason_codes']


def test_global_complete_quote_allows_authorized_union():
    assert "NARRATIVE_UNAUTHORIZED_QUOTE" not in result("Descrizione.", f'Fonte: "{OTHER}".')['reason_codes']


def test_candidate_cannot_borrow_other_trial_identifier():
    payload = projection("TRIAL")
    payload['candidates'][0]['trial_context'] = {"nct_id": "NCT12345678"}
    payload['candidates'][1]['trial_context'] = {"nct_id": "NCT87654321"}
    report = verify_narrative({}, payload, {"candidate_narratives": [
        {"candidate_id": "P1", "text": "Fonte NCT87654321."},
        {"candidate_id": "P2", "text": "Descrizione."}]})
    assert "NARRATIVE_UNAUTHORIZED_ENTITY" in report['reason_codes']


def test_count_audit_recomputes_projection_instead_of_trusting_summary_cache():
    payload = projection()
    payload['summary_facts'] = {"paper_count": 999, "trial_count": 0, "kg_only_count": 0}
    report = verify_narrative({}, payload, {"candidate_narratives": [
        {"candidate_id": "P1", "text": "Descrizione."},
        {"candidate_id": "P2", "text": "Descrizione."}],
        "narrative_summary": "Il dossier comprende 999 relazioni da pubblicazioni, 0 associazioni a trial e 0 relazioni del knowledge graph."})
    assert report['global_fact_mismatches'] == [{"block": "narrative_summary",
        "fact": "paper_count", "expected": 2, "observed": 999}]


def test_correct_counts_are_accepted_by_independent_audit():
    assert "NARRATIVE_GLOBAL_FACT_MISMATCH" not in result("Descrizione.",
        "Il dossier comprende 2 relazioni da pubblicazioni, 0 associazioni a trial e 0 relazioni del knowledge graph.")['reason_codes']


@pytest.mark.parametrize("branch", ["PAPER", "KG_ONLY"])
def test_false_global_counts_are_rejected_for_every_branch(branch):
    codes = result("Descrizione.", "Il dossier comprende 999 relazioni da pubblicazioni, 0 associazioni a trial e 2 relazioni del knowledge graph.", branch)['reason_codes']
    assert "NARRATIVE_GLOBAL_FACT_MISMATCH" in codes


TRIAL = {"candidate_id": "T", "branch": "TRIAL", "trial_context": {
    "nct_id": "NCT12345678", "evidence_interpretation": "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE"}}


def test_negative_disclaimer_and_unknown_sentence_is_scope_unproven_only():
    kinds = {v['kind'] for v in _check_branch_semantics(TRIAL,
        "L'associazione a trial non costituisce prova di efficacia. Una frase fuori grammatica.")}
    assert "TRIAL_ASSOCIATION_SCOPE_UNPROVEN" in kinds
    assert "TRIAL_EFFICACY_ESCALATION" not in kinds


def test_negative_disclaimer_does_not_hide_positive_suffix():
    kinds = {v['kind'] for v in _check_branch_semantics(TRIAL,
        "The trial does not show efficacy. The trial is effective.")}
    assert "TRIAL_EFFICACY_ESCALATION" in kinds
