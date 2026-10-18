"""Italian factual scope stays closed; negations never license positive claims."""
import pytest
from backend.research_pipeline.narrative import lexicon


@pytest.mark.parametrize("text", ["La relazione non è supportata.",
                                 "La relazione non è stata confermata.",
                                 "L'analisi non ha confermato il supporto.",
                                 "The relation is not confirmed."])
def test_direct_negation_is_not_a_positive_support_claim(text):
    assert lexicon.support_claim_hits(text) == []


@pytest.mark.parametrize("text", ["Not not confirmed.", "Non non confermata.",
                                 "La relazione non è non confermata.",
                                 "L'analisi non ha non confermato il supporto."])
def test_double_negation_cannot_hide_a_support_claim(text):
    assert lexicon.support_claim_hits(text)


def test_double_negation_with_auxiliary_cannot_hide_a_support_claim():
    assert lexicon.support_claim_hits("Non non ha confermato il supporto.")


@pytest.mark.parametrize("count", [3, 7])
def test_grounded_global_quote_count_is_not_trial_efficacy(count):
    from backend.research_pipeline.narrative.verifier import _unlicensed_global_text
    projection = {"summary_facts": {"validated_quote_count": count}}
    assert _unlicensed_global_text(f"Sono presenti {count} citazioni validate.", projection) == ""
    assert _unlicensed_global_text(f"Sono presenti {count + 1} citazioni validate.", projection)
    assert _unlicensed_global_text(f"Sono presenti {count} citazioni validate e il trial è efficace.", projection)


def test_global_majority_claim_requires_a_proven_lower_bound():
    from backend.research_pipeline.narrative.verifier import _unlicensed_global_text
    text = "Il sistema ha identificato che la maggior parte delle relazioni non ha supporto documentale o non è verificabile;"
    projection = {"summary_facts": {"candidate_count": 10, "no_support_count": 2,
                                   "unverifiable_count": 2, "kg_only_count": 2}}
    assert _unlicensed_global_text(text, projection) == ""
    projection["summary_facts"]["kg_only_count"] = 0
    assert _unlicensed_global_text(text, projection)


def test_global_partial_and_quote_counts_both_require_exact_canonical_values():
    from backend.research_pipeline.narrative.verifier import _unlicensed_global_text
    projection = {"summary_facts": {"partial_support_count": 3, "validated_quote_count": 7}}
    assert _unlicensed_global_text("Sono presenti 3 relazioni con supporto parziale e 7 citazioni validate.", projection) == ""
    assert _unlicensed_global_text("Sono presenti 4 relazioni con supporto parziale e 7 citazioni validate.", projection)


@pytest.mark.parametrize("text", ["La relazione non è supportata. La relazione è supportata.",
                                 "La relazione non è confermata. La relazione è confermata.",
                                 "Non è falso che la relazione è supportata.",
                                 "La relazione non solo è supportata."])
def test_negation_does_not_erase_a_separate_positive_claim(text):
    assert lexicon.support_claim_hits(text)

from backend.research_pipeline.narrative.verifier import _check_branch_semantics, _check_status


KG = {"candidate_id": "K", "branch": "KG_ONLY", "canonical_status": "KG_ONLY",
      "candidate_support": None, "support_direction": "", "expresses_support": False}
TRIAL = {"candidate_id": "T", "branch": "TRIAL", "trial_context": {
    "nct_id": "NCT12345678", "eligibility_status": "NOT_EVALUATED",
    "evidence_interpretation": "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE"}}


def test_negated_document_support_is_not_positive_support():
    assert not _check_status(KG, "La relazione non è supportata da documenti.")
    assert not _check_status(KG, "La relazione non è supportata da evidenza documentale.")
    assert not _check_status(KG, "La relazione non è supportata da documentazione.")


def test_negation_does_not_mask_later_positive_assertion():
    assert _check_status(KG, "La relazione non è supportata da documenti. È supportata clinicamente.")


def test_italian_trial_facts_are_accepted():
    assert not _check_branch_semantics(TRIAL,
        "Il trial NCT12345678 è associato al caso. "
        "L'associazione a trial non costituisce prova di efficacia. "
        "L'eleggibilità del paziente non è stata valutata.")
    assert not _check_branch_semantics(TRIAL, "La candidate è associata al trial NCT12345678.")
    assert not _check_branch_semantics(TRIAL,
        "L'associazione a trial non costituisce prova di efficacia e "
        "l'eleggibilità del paziente non è stata valutata.")


def test_trial_condition_language_requires_literal_registered_conditions():
    from copy import deepcopy
    trial = deepcopy(TRIAL)
    trial["canonical_status"] = "CONTEXT_ONLY"
    trial["trial_context"]["conditions"] = ["Cancer Alpha", "Condition Beta"]
    prefix = "La candidate è associata al trial NCT12345678"
    assert not _check_branch_semantics(trial, prefix + " per Cancer Alpha.")
    assert not _check_branch_semantics(trial, prefix + ", che riguarda pazienti con Cancer Alpha e Condition Beta.")
    assert not _check_branch_semantics(trial, "Lo stato canonico è di solo contesto e l'associazione a trial non costituisce prova di efficacia.")
    assert _check_branch_semantics(trial, prefix + " per Cancer Gamma.")
    assert _check_branch_semantics(trial, prefix + " per Cancer Alpha e il paziente è eleggibile.")


@pytest.mark.parametrize("text", [
    "Il trial NCT99999999 è associato al caso.",
    "Il trial NCT12345678 è efficace.",
    "Il paziente è eleggibile per il trial NCT12345678.",
    "Il trial NCT12345678 è associato al caso e dimostra efficacia.",
    "L'associazione a trial non costituisce prova di efficacia e il trial è efficace.",
])
def test_trial_escalations_and_unknown_identity_still_rejected(text):
    assert _check_branch_semantics(TRIAL, text)


def test_global_counts_must_match_canonical_facts():
    facts = {"trial_count": 72, "kg_only_count": 222}
    assert not _check_branch_semantics(TRIAL,
        "Il dossier comprende 72 associazioni a trial e 222 relazioni del Knowledge Graph.", facts)
    assert _check_branch_semantics(TRIAL,
        "Il dossier comprende 73 associazioni a trial e 222 relazioni del Knowledge Graph.", facts)


def test_global_trial_and_graph_limitations_are_scoped():
    facts = {"paper_count": 0, "trial_count": 72, "kg_only_count": 222}
    text = ("Le evidenze riportate derivano da associazioni a trial clinici, "
            "le quali non costituiscono prova di efficacia. "
            "Non è disponibile la provenienza documentale per le relazioni "
            "derivate esclusivamente dal Knowledge Graph.")
    assert not _check_branch_semantics(TRIAL, text, facts)
    assert _check_branch_semantics(TRIAL, text, {**facts, "paper_count": 1})
    assert not _check_branch_semantics(TRIAL,
        "Le limitazioni includono l'assenza di provenienza documentale per alcune "
        "relazioni e il fatto che l'associazione a trial non costituisce prova di efficacia.", facts)


def test_kg_negative_clause_never_masks_separate_documentary_claim():
    assert not _check_branch_semantics(KG, "La relazione non è supportata da evidenza documentale.")
    assert _check_branch_semantics(KG,
        "La relazione non è supportata da evidenza documentale. Validated evidence exists.")


def test_double_negation_cannot_be_removed_as_an_absence_clause():
    assert _check_status(KG, "Non non è supportata da documenti.")
    assert _check_branch_semantics(KG, "Non non è supportata da evidenza documentale.")
