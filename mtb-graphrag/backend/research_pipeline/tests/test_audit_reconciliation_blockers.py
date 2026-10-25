"""Independent regressions for confirmed pre-freeze scientific boundaries."""

from pathlib import Path

import pytest

from backend.research_pipeline.casecontext.parser import adapt_case_context
from backend.research_pipeline.casecontext.pipeline import build_retrieval_case_context, run
from backend.research_pipeline.data_access import adapt_candidate_for_runtime
from backend.research_pipeline.documents.trial_resolution import resolve_trial_record
from backend.research_pipeline.documents.live_resolution import (
    resolve_documents, resolve_live_documents,
)
from backend.research_pipeline.enrichment.relation_support import assess_relation_support
from backend.research_pipeline.enrichment.proposition_assertion import assess_proposition_assertion
from backend.research_pipeline.narrative.input_projection import build_narrator_input
from backend.research_pipeline.narrative.verifier import verify_narrative
from backend.research_pipeline.retrieval.kg_retrieval import (
    _intervention_matches, _match_candidate, load_candidates,
)
from backend.research_pipeline.tests.test_orchestrated_pre_freeze_matrix import (
    _paper_candidate, _parser_output, _run_orchestrated, _source_unit, _trial_candidate,
)
from backend.research_pipeline.tests.test_pre_freeze_proposition_assertion import (
    candidate, forced_positive_reader,
)


@pytest.mark.parametrize("quote", [
    "EGFR L858R allegedly showed sensitivity to erlotinib.",
    "The finding that EGFR L858R showed sensitivity to erlotinib was later withdrawn.",
    "We found that a previous study showed EGFR L858R sensitivity to erlotinib.",
    "In a thought experiment, EGFR L858R showed sensitivity to erlotinib.",
])
def test_epistemic_scope_cannot_be_full_support(quote: str) -> None:
    result = assess_relation_support(
        candidate(), forced_positive_reader(), source_unit_text=quote,
    )
    assert result["result"] != "FULL_SUPPORT", result


@pytest.mark.parametrize("pair_text", [
    "EGFR L858R", "EGFR p.L858R", "L858R mutation in EGFR", "EGFR mutation L858R",
])
def test_literal_gene_variant_pair_is_retained(pair_text: str) -> None:
    raw = f"lung cancer with {pair_text}; current erlotinib"
    context = adapt_case_context("pair-positive", _parser_output(raw), raw)
    result = run(raw, context)
    query = build_retrieval_case_context(context, result["mentions"])
    assert any(b.get("gene") == "EGFR" and b.get("alteration") == "L858R"
               for b in query["biomarkers"])


@pytest.mark.parametrize("raw", [
    "lung cancer with EGFR L858R and KRAS G12C; current erlotinib",
    "lung cancer with EGFR and KRAS G12C; current erlotinib",
])
def test_parser_cannot_invent_gene_variant_pair(raw: str) -> None:
    context = adapt_case_context("cross-pair", _parser_output(raw, biomarkers=(("EGFR", "G12C"),)), raw)
    result = run(raw, context)
    query = build_retrieval_case_context(context, result["mentions"])
    assert not any(b.get("gene") == "EGFR" and b.get("alteration") == "G12C"
                   for b in query["biomarkers"])
    assert any(m["rejection_reason"] == "GENE_VARIANT_PAIR_NOT_GROUNDED"
               for m in result["mentions"])


def test_raw_negation_overrides_parser_present() -> None:
    raw = "lung cancer with no EGFR L858R; current erlotinib"
    context = adapt_case_context("negated-pair", _parser_output(raw), raw)
    result = run(raw, context)
    query = build_retrieval_case_context(context, result["mentions"])
    assert not any(b.get("gene") == "EGFR" and b.get("alteration") == "L858R"
                   for b in query["biomarkers"])


@pytest.mark.parametrize("sentence", [
    "This trial demonstrates that the patient will respond to erlotinib.",
    "The patient is a good match for this trial.",
    "Erlotinib is appropriate for this patient based on this trial.",
])
def test_trial_association_narrative_must_reject_clinical_escalation(sentence: str) -> None:
    dossier = {"case_id": "narrative-scope", "clinical_trials": [{
        "candidate_id": "T", "nct_id": "NCT12345678", "interventions": ["erlotinib"],
        "trial_resolution_status": "AVAILABLE", "eligibility_status": "NOT_EVALUATED",
        "evidence_interpretation": "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE",
        "support_level": "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE",
    }]}
    projection = build_narrator_input(dossier)
    output = {"candidate_narratives": [{"candidate_id": "T", "text": sentence}]}
    result = verify_narrative(dossier, projection, output)
    assert result["status"] == "FAIL", result


def test_trial_only_available_sourceunit_reaches_reader() -> None:
    raw = "lung cancer with EGFR L858R; current erlotinib; trial NCT12345678"
    candidate_row = _trial_candidate(gene="EGFR")
    case_id = "reconciliation-trial-only"
    try:
        result = _run_orchestrated(
            Path("."), case_id, raw, _parser_output(raw, trials=("NCT12345678",)),
            {candidate_row["candidate_id"]: candidate_row},
            [_source_unit("This trial investigates EGFR and erlotinib in lung cancer.",
                          document_id="nct:NCT12345678", unit_id="SU-TRIAL-RECON")],
        )
        trial = result.relation_aware_report["clinical_trials"][0]
        assert trial["reader_attempts"], trial
        assert trial["claim"]["status"] == "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE"
    finally:
        Path(f"{case_id}.sqlite3").unlink(missing_ok=True)


def test_different_drugs_do_not_match_on_salt_token() -> None:
    assert not _intervention_matches("erlotinib hydrochloride", "gefitinib hydrochloride")


def test_unknown_trial_availability_cannot_be_success() -> None:
    record = {"document_id": "nct:NCT12345678", "availability": "UNKNOWN",
              "local_cache_path": "stale.json"}
    result = resolve_trial_record("NCT12345678", record, resolved_payload=True)
    assert result["trial_resolution_status"] != "AVAILABLE"


def test_unknown_trial_cache_record_cannot_resolve_despite_stale_truthy_payload() -> None:
    record = {"document_id": "nct:NCT12345678", "availability": "UNKNOWN",
              "local_cache_path": "stale.json", "nct_id": "NCT12345678"}
    association = {"candidate_id": "T", "available_bundles": [{
        "bundle_id": "trial:T", "document_id": "nct:NCT12345678",
        "provenance_identifier": {"nct": "NCT12345678"},
    }]}

    class StaleCache:
        root = Path(".")
        resolver_version = "controlled-stale-cache"
        manifest_path = Path("does-not-exist")

        def has_text_payload(self, _record):
            return True

        def resolve_live_identifier(self, _identifier):
            return {**record, "cache_hit": True}

    cache = StaleCache()
    for resolution in (
        resolve_documents([association], {record["document_id"]: record}, cache),
        resolve_live_documents([association], cache, {}),
    ):
        assert not resolution.documents[0].resolved
        assert resolve_trial_record(
            "NCT12345678", record, resolved_payload=resolution.documents[0].resolved,
        )["trial_resolution_status"] != "AVAILABLE"


def test_verified_trial_metadata_payload_remains_available() -> None:
    record = {"document_id": "nct:NCT12345678", "availability": "METADATA_ONLY"}
    assert resolve_trial_record(
        "NCT12345678", record, resolved_payload=True,
    )["trial_resolution_status"] == "AVAILABLE"


def test_formulation_suffix_does_not_invent_an_unsourced_equivalence() -> None:
    # A formulation relationship needs an audited active-moiety mapping.
    # Removing generic salt tokens is no longer canonical entity identity.
    assert not _intervention_matches("erlotinib", "erlotinib hydrochloride")
    assert not _intervention_matches("erlotinib sodium", "gefitinib sodium")


@pytest.mark.parametrize("quote", [
    "A conference abstract asserted that EGFR L858R showed sensitivity to erlotinib.",
    "Clinicians have claimed that EGFR L858R predicts erlotinib response.",
    "The published claim that EGFR L858R responds to erlotinib was subsequently rescinded.",
    "An earlier report's conclusion that EGFR L858R predicts erlotinib response was invalidated.",
    "EGFR L858R is said to confer sensitivity to erlotinib.",
    '"EGFR L858R predicts erlotinib response," the review quoted.',
    "Could it be that EGFR L858R predicts response to erlotinib?",
    "It is not false that EGFR L858R predicts response to erlotinib.",
    "Had EGFR L858R predicted erlotinib response, this cohort would have benefited.",
    "Although others proposed EGFR L858R sensitivity to erlotinib, our data failed to reproduce it.",
    "In the introductory background, EGFR L858R sensitivity to erlotinib has been described.",
    "We were unable to verify that EGFR L858R predicts response to erlotinib.",
    "One group observed EGFR L858R sensitivity to erlotinib; another group disputed it.",
    "EGFR L858R perhaps increases sensitivity to erlotinib.",
    "It would be premature to conclude that EGFR L858R predicts erlotinib response.",
    "A simulation predicted EGFR L858R sensitivity to erlotinib.",
    "The rumor that EGFR L858R predicts erlotinib response spread widely.",
])
def test_independently_authored_non_direct_scope_is_not_full(quote: str) -> None:
    result = assess_relation_support(candidate(), forced_positive_reader(), source_unit_text=quote)
    assert result["result"] != "FULL_SUPPORT", (quote, result)


@pytest.mark.parametrize("quote", [
    "EGFR L858R showed sensitivity to erlotinib, or so we imagined.",
    "EGFR L858R showed sensitivity to erlotinib, so the story goes.",
    "EGFR L858R showed sensitivity to erlotinib, at least in the fictional scenario.",
    "EGFR L858R showed sensitivity to erlotinib; the result was subsequently invalidated.",
    "EGFR L858R showed sensitivity to erlotinib, a claim later discredited.",
    "EGFR L858R showed sensitivity to erlotinib in a dream.",
    "EGFR L858R showed sensitivity to erlotinib, or so the critics alleged.",
    "EGFR L858R showed sensitivity to erlotinib, a result later debunked.",
])
def test_trailing_scope_qualifier_cannot_license_full_support(quote: str) -> None:
    result = assess_relation_support(candidate(), forced_positive_reader(), source_unit_text=quote)
    assert result["result"] != "FULL_SUPPORT", (quote, result)


@pytest.mark.parametrize("quote", [
    "EGFR L858R showed sensitivity to erlotinib in an imagined world.",
    "EGFR L858R showed sensitivity to erlotinib, a conclusion later overturned.",
    "EGFR L858R showed sensitivity to erlotinib, or so the manuscript claimed.",
    "EGFR L858R showed sensitivity to erlotinib, a story since repudiated.",
])
def test_unclassified_trailing_scope_remains_open(quote: str) -> None:
    result = assess_relation_support(candidate(), forced_positive_reader(), source_unit_text=quote)
    assert result["result"] != "FULL_SUPPORT", (quote, result)


@pytest.mark.parametrize("sentence", [
    "This trial proves erlotinib works for the patient.",
    "Enrollment is warranted for this patient.",
    "The case fits this study perfectly.",
    "The trial makes erlotinib the preferred therapy.",
    "A favorable response is expected.",
    "This patient qualifies for the study.",
    "Erlotinib is the right treatment for this case.",
    "The trial confirms therapeutic benefit for this patient.",
    "Patient selection criteria are satisfied.",
    "The trial predicts benefit from erlotinib.",
    "We should prescribe erlotinib to this patient.",
    "Erlotinib offers a clinical advantage here.",
    "The participant matches the trial population.",
    "Trial inclusion indicates sensitivity to erlotinib.",
    "The patient can safely be enrolled now.",
])
def test_independently_authored_trial_escalation_is_rejected(sentence: str) -> None:
    dossier = {"case_id": "narrative-red-team", "clinical_trials": [{
        "candidate_id": "T", "nct_id": "NCT12345678", "interventions": ["erlotinib"],
        "trial_resolution_status": "AVAILABLE", "eligibility_status": "NOT_EVALUATED",
        "evidence_interpretation": "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE",
        "support_level": "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE",
    }]}
    projection = build_narrator_input(dossier)
    output = {"candidate_narratives": [{"candidate_id": "T", "text": sentence}]}
    result = verify_narrative(dossier, projection, output)
    assert result["status"] == "FAIL", (sentence, result)


@pytest.mark.parametrize("sentence", [
    "This trial exists.",
    "The trial includes erlotinib.",
    "Eligibility has not been evaluated.",
    "Efficacy is not established by this trial.",
])
def test_trial_association_only_language_is_allowed(sentence: str) -> None:
    dossier = {"clinical_trials": [{
        "candidate_id": "T", "nct_id": "NCT12345678", "interventions": ["erlotinib"],
        "eligibility_status": "NOT_EVALUATED",
        "evidence_interpretation": "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE",
        "support_level": "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE",
    }]}
    projection = build_narrator_input(dossier)
    output = {"candidate_narratives": [{"candidate_id": "T", "text": sentence}]}
    assert verify_narrative(dossier, projection, output)["status"] == "PASS"


def test_first_party_direct_result_survives_epistemic_filter() -> None:
    quote = "Our results showed that EGFR L858R was associated with response to erlotinib."
    result = assess_relation_support(candidate(), forced_positive_reader(), source_unit_text=quote)
    assert result["result"] == "FULL_SUPPORT", result


@pytest.mark.parametrize("quote,relation,scope", [
    ("EGFR L858R showed sensitivity to erlotinib.", "RELATION_ASSERTED", "DIRECT_ASSERTION"),
    ("Previous studies reported that EGFR L858R showed sensitivity to erlotinib.",
     "RELATION_ASSERTED", "ATTRIBUTED_ASSERTION"),
    ("EGFR L858R might show sensitivity to erlotinib.",
     "RELATION_ASSERTED", "HYPOTHETICAL_ASSERTION"),
    ("The finding that EGFR L858R showed sensitivity to erlotinib was withdrawn.",
     "RELATION_ASSERTED", "RETRACTED_ASSERTION"),
    ("The finding that EGFR L858R showed sensitivity to erlotinib was rejected.",
     "RELATION_ASSERTED", "REJECTED_ASSERTION"),
    ("Whether EGFR L858R responds to erlotinib is unclear.",
     "RELATION_ASSERTED", "UNCERTAIN_ASSERTION"),
    ("EGFR L858R and erlotinib were studied.",
     "ENTITY_CO_OCCURRENCE", "COOCCURRENCE"),
])
def test_assertion_contract_exposes_distinct_epistemic_scope(
    quote: str, relation: str, scope: str,
) -> None:
    result = assess_proposition_assertion(quote, candidate(), relation)
    assert result.epistemic_scope == scope


@pytest.mark.parametrize("quote,full", [
    ("Although earlier authors suggested EGFR L858R sensitivity to erlotinib, "
     "our results confirmed EGFR L858R response to erlotinib.", True),
    ("Although earlier authors suggested EGFR L858R sensitivity to erlotinib, "
     "our results failed to confirm EGFR L858R response to erlotinib.", False),
])
def test_contrast_respects_current_source_clause(quote: str, full: bool) -> None:
    result = assess_relation_support(candidate(), forced_positive_reader(), source_unit_text=quote)
    assert (result["result"] == "FULL_SUPPORT") is full, result


@pytest.mark.parametrize("case_id,quote", [
    ("scope-alleged", "EGFR L858R allegedly showed sensitivity to erlotinib."),
    ("scope-withdrawn", "The finding that EGFR L858R showed sensitivity to erlotinib was later withdrawn."),
    ("scope-attributed", "We found that a previous study showed EGFR L858R sensitivity to erlotinib."),
    ("scope-thought", "In a thought experiment, EGFR L858R showed sensitivity to erlotinib."),
])
def test_orchestrator_cannot_promote_document_scope(case_id: str, quote: str) -> None:
    raw = "lung cancer with EGFR L858R; current erlotinib"
    paper = _paper_candidate()
    try:
        result = _run_orchestrated(
            Path("."), case_id, raw, _parser_output(raw),
            {paper["candidate_id"]: paper}, [_source_unit(quote)], reader_force_positive=True,
        )
        claim = result.relation_aware_report["paper_evidence"][0]["claim"]
        assert claim["status"] != "FULL_SUPPORT", claim
    finally:
        Path(f"{case_id}.sqlite3").unlink(missing_ok=True)


def test_orchestrator_cannot_promote_invented_pair() -> None:
    case_id = "cross-pair-orchestrated"
    raw = "lung cancer with EGFR L858R and KRAS G12C; current erlotinib"
    paper = _paper_candidate(biomarkers=[
        {"label": "EGFR", "type": "Gene"},
        {"label": "G12C", "type": "Variant", "gene": "EGFR", "alteration": "G12C"},
    ])
    try:
        result = _run_orchestrated(
            Path("."), case_id, raw, _parser_output(raw, biomarkers=(("EGFR", "G12C"),)),
            {paper["candidate_id"]: paper},
            [_source_unit("EGFR G12C was associated with sensitivity to erlotinib in lung cancer.")],
        )
        claims = [item["claim"] for item in (result.relation_aware_report or {}).get("paper_evidence", [])]
        assert all(claim["status"] != "FULL_SUPPORT" for claim in claims), claims
    finally:
        Path(f"{case_id}.sqlite3").unlink(missing_ok=True)


def test_orchestrator_raw_negation_cannot_reach_full_support() -> None:
    case_id = "negated-pair-orchestrated"
    raw = "lung cancer with no EGFR L858R; current erlotinib"
    paper = _paper_candidate()
    try:
        result = _run_orchestrated(
            Path("."), case_id, raw, _parser_output(raw), {paper["candidate_id"]: paper},
            [_source_unit("EGFR L858R was associated with sensitivity to erlotinib in lung cancer.")],
        )
        claims = [item["claim"] for item in (result.relation_aware_report or {}).get("paper_evidence", [])]
        assert all(claim["status"] != "FULL_SUPPORT" for claim in claims), claims
    finally:
        Path(f"{case_id}.sqlite3").unlink(missing_ok=True)


def test_orchestrator_wrong_drug_same_salt_is_not_retrieved() -> None:
    case_id = "wrong-salt-drug-orchestrated"
    raw = "lung cancer with EGFR L858R; current erlotinib hydrochloride"
    paper = _paper_candidate(interventions=[{"label": "gefitinib hydrochloride", "type": "Drug"}])
    try:
        result = _run_orchestrated(
            Path("."), case_id, raw,
            _parser_output(raw, interventions=(("erlotinib hydrochloride", "TARGET"),)),
            {paper["candidate_id"]: paper},
            [_source_unit("EGFR L858R responded to gefitinib hydrochloride in lung cancer.")],
        )
        assert not (result.relation_aware_report or {}).get("paper_evidence"), result
    finally:
        Path(f"{case_id}.sqlite3").unlink(missing_ok=True)


def test_conservative_diagnostic_manufacturer_suffix_alias() -> None:
    candidate_row = adapt_candidate_for_runtime(
        load_candidates()["GCA4-039ca7831aca33a1e28296dc"]
    )
    context = {
        "biomarkers": [{"gene": "EGFR", "assertion_status": "PRESENT"}],
        "disease": {"raw_value": "lung cancer"},
        "target_intervention": {"raw_value": "erlotinib"},
        "query_intent": "THERAPY_EVALUATION",
        "companion_diagnostic_mentions": [{
            "name": "FoundationOne CDx", "associated_gene": "EGFR",
            "associated_drug": "erlotinib", "assertion_status": "PRESENT",
        }],
    }
    assert _match_candidate(context, candidate_row)[0]
