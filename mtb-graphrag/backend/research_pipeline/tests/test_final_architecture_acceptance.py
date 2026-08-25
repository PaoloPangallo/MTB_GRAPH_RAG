import json
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.pipeline.agentic.ledger import EventLedger
from backend.research_pipeline import orchestrator
from backend.research_pipeline.dossier.builder import build_relation_aware_report
from backend.research_pipeline.enrichment.relation_support import assess_relation_support
from backend.research_pipeline.enrichment import prompt_v3
from backend.research_pipeline.enrichment.validator_v3 import validate_enrichment_v3
from backend.research_pipeline.casecontext import prompt as case_prompt
from backend.research_pipeline.pipeline import CallBudget
from backend.research_pipeline.retrieval import kg_retrieval
from backend.research_pipeline.retrieval.relation_family import (
    CLINICAL_TRIAL,
    INVALID_PROVENANCE,
    KG_ONLY,
    PAPER_EVIDENCE,
    classify_relation_family,
)


def _context(*, disease="colorectal cancer", gene="KRAS", alteration="G12D", drug=None):
    value = {
        "case_id": "CASE-ACCEPTANCE",
        "disease": {"raw_value": disease, "normalized_value": disease},
        "biomarkers": [{"gene": gene, "alteration": alteration, "raw_value": f"{gene} {alteration}"}],
        "target_intervention": ({"raw_value": drug, "normalized_value": drug} if drug else None),
        "query_intent": "THERAPY_EVALUATION" if drug else "THERAPY_DISCOVERY",
        "uncertainties": [],
    }
    return value


def _association(candidate):
    return {
        "candidate_id": candidate["candidate_id"],
        "candidate": candidate,
        "relation_family": classify_relation_family(candidate),
        "match_reason_codes": ["ACCEPTANCE_FIXTURE"],
        "available_bundles": [],
    }


def _parser(case_context):
    return lambda budget, case_id, text: {
        "transport_result": "FORCED_TOOL_VALID",
        "model": "offline-parser",
        "prompt_version": "casecontext-parser-prompt/3.0",
        "case_context_raw": case_context,
    }


def _run(*, candidates, case_context=None, select_papers_fn=None):
    context = case_context or _context(drug="panitumumab")
    result = {
        "query_intent": context["query_intent"],
        "associations": [_association(candidate) for candidate in candidates],
        "excluded_candidates": [],
        "no_match": not candidates,
        "retrieval_summary": {"matched_total": len(candidates), "selected_total": len(candidates)},
    }
    with TemporaryDirectory() as tmp:
        return orchestrator.run_case(
            case_id=context["case_id"],
            clinical_text="colorectal cancer KRAS G12D panitumumab",
            call_parser_fn=_parser(context),
            call_enricher_fn=lambda *args, **kwargs: {
                "transport_result": "V2_TRANSPORT_VALID", "enrichment": None,
            },
            source_units_by_id={},
            budget=CallBudget(4),
            ledger=EventLedger(Path(tmp) / "acceptance.sqlite3"),
            research_frozen_artifacts=True,
            retrieve_fn=lambda _: result,
            select_papers_fn=select_papers_fn,
            match_verifier_fn=lambda *_: {
                "records": [], "essential_fields_pass": True, "warnings": [], "bypassed": True,
            },
            eligibility_gate_fn=lambda *_: None,
            call_narrator_fn=None,
        )


def test_mixed_pmid_and_nct_is_invalid_provenance_not_an_exception():
    candidate = {"document_identifiers": [{"pmid": "1", "nct": "NCT1"}]}
    assert classify_relation_family(candidate) == INVALID_PROVENANCE


def test_trial_drug_is_retrieved_from_real_corpus_using_intervention_anchor(monkeypatch):
    trial = kg_retrieval.load_candidates()["GCA-bd12d81e3b8b2f67728ca364"]
    unrelated = kg_retrieval.load_candidates()["GCA-6cb3e69e2badaaf63cdb75bd"]
    monkeypatch.setattr(kg_retrieval, "load_candidates", lambda: {
        trial["candidate_id"]: trial, unrelated["candidate_id"]: unrelated,
    })
    result = kg_retrieval.retrieve(_context(disease="gastrointestinal cancer", gene="ERBB2", alteration=None, drug="EMB-01"))
    assert [entry["candidate_id"] for entry in result["associations"]] == [trial["candidate_id"]]
    assert result["associations"][0]["relation_family"] == CLINICAL_TRIAL


def test_mixed_runtime_never_sends_trial_or_kg_only_to_paper_selector():
    candidates = kg_retrieval.load_candidates()
    paper = candidates["GCA-008ae3aad1a64c118318ef79"]
    trial = candidates["GCA-bd12d81e3b8b2f67728ca364"]
    kg_only = candidates["GCA-6cb3e69e2badaaf63cdb75bd"]
    selected = []

    def paper_only_selector(association, units, **kwargs):
        selected.append(association["candidate_id"])
        assert association["relation_family"] == PAPER_EVIDENCE
        return {"candidate_id": association["candidate_id"], "selected_papers": [], "excluded_papers": []}

    run = _run(candidates=[paper, trial, kg_only], select_papers_fn=paper_only_selector)
    report = run.relation_aware_report
    assert selected == [paper["candidate_id"]]
    assert len(report["paper_evidence"]) == 1
    assert len(report["clinical_trials"]) == 1
    assert len(report["kg_only_relations"]) == 1
    assert report["clinical_trials"][0]["evidence_interpretation"] == "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE"
    assert report["kg_only_relations"][0]["document_provenance"] == "NOT_AVAILABLE"


def test_zero_retrieval_returns_clean_empty_canonical_dossier():
    run = _run(candidates=[])
    assert run.status == "STOPPED"
    assert run.relation_aware_report["run_status"] == "NO_RELEVANT_KG_EVIDENCE"
    assert run.relation_aware_report["paper_evidence"] == []
    assert run.relation_aware_report["clinical_trials"] == []
    assert run.relation_aware_report["kg_only_relations"] == []


def test_case1_relation_support_preserves_variant_specificity():
    candidate = kg_retrieval.load_candidates()["GCA-008ae3aad1a64c118318ef79"]
    observed = {
        "decision": "QUOTE",
        "observed_disease": "metastatic colorectal cancer",
        "observed_gene": "KRAS",
        "observed_alteration": "",
        "observed_drug": "panitumumab",
        "observed_direction": "RESISTANCE",
        "observed_evidence_type": "PREDICTIVE",
    }
    result = assess_relation_support(candidate, observed)
    assert result["fields"] == {
        "disease": "CONFIRMED", "gene": "CONFIRMED", "alteration": "NOT_CONFIRMED",
        "drug": "CONFIRMED", "direction": "CONFIRMED", "evidence_type": "CONFIRMED",
    }
    assert result["result"] == "PARTIAL_SUPPORT"


def test_v3_reader_observation_is_projected_into_the_canonical_paper_entry():
    candidate = kg_retrieval.load_candidates()["GCA-008ae3aad1a64c118318ef79"]
    enrichment = {
        "decision": "QUOTE", "source_unit_id": "SU-CASE1",
        "quote": "patients with mCRC bearing KRAS mutations are clinically resistant to therapy with panitumumab.",
        "observed_disease": "metastatic colorectal cancer", "observed_gene": "KRAS",
        "observed_alteration": "", "observed_drug": "panitumumab",
        "observed_direction": "RESISTANCE", "observed_evidence_type": "PREDICTIVE",
    }
    support = assess_relation_support(candidate, enrichment)
    report = build_relation_aware_report(_context(drug="panitumumab"), [candidate], paper_results={
        candidate["candidate_id"]: {
            "document_resolution_status": "RESOLVED", "selected_source_units": ["SU-CASE1"],
            "enrichment": enrichment, "validation": {"outcome": "ENRICHMENT_V3_ACCEPTED"},
            "quote_valid": True, "candidate_support": support,
        },
    })
    entry = report["paper_evidence"][0]
    assert entry["reader_decision"] == "QUOTE"
    assert entry["quote"] == enrichment["quote"]
    assert entry["quote_source_unit_id"] == "SU-CASE1"
    assert entry["support_level"] == "PARTIAL_SUPPORT"


def test_diagnostic_and_prognostic_profiles_do_not_require_drug_or_therapeutic_direction():
    candidates = kg_retrieval.load_candidates()
    fixtures = (
        (candidates["GCA-a082283f128c49620273b965"], "Lymphoid Leukemia", "JAK2", "V617F", "SUPPORTS", "DIAGNOSTIC"),
        (candidates["GCA-10134b6f4fa111b6ab641410"], "Acute Myeloid Leukemia", "DNMT3A", "R882", "DOES_NOT_SUPPORT", "PROGNOSTIC"),
    )
    for candidate, disease, gene, alteration, direction, evidence_type in fixtures:
        result = assess_relation_support(candidate, {
            "decision": "QUOTE", "observed_disease": disease,
            "observed_gene": gene, "observed_alteration": alteration,
            "observed_drug": "", "observed_direction": direction,
            "observed_evidence_type": evidence_type,
        })
        assert result["fields"]["drug"] == "NOT_APPLICABLE"
        assert result["result"] == "FULL_SUPPORT"


def test_disease_context_alone_is_not_partial_relation_support():
    result = assess_relation_support({
        "candidate_id": "GCA-CORE-MISSING",
        "disease": [{"label": "Lung Cancer"}],
        "biomarkers": [{"type": "Gene", "label": "EGFR"}],
        "interventions": [{"label": "gefitinib"}],
        "direction": "Sensitivity/Response",
        "evidence_scope": "Predictive",
    }, {
        "decision": "QUOTE", "observed_disease": "Lung Cancer",
        "observed_gene": "", "observed_alteration": "", "observed_drug": "",
        "observed_direction": "UNKNOWN", "observed_evidence_type": "UNKNOWN",
    })
    assert result["fields"]["disease"] == "CONFIRMED"
    assert result["result"] == "NO_SUPPORT"


def test_canonical_report_exposes_run_retrieval_and_provenance_summaries():
    candidates = kg_retrieval.load_candidates()
    report = build_relation_aware_report(
        _context(drug="panitumumab"),
        [candidates["GCA-008ae3aad1a64c118318ef79"]],
        run_status="PARTIAL",
        retrieval_summary={"matched_total": 1, "selected_total": 1, "cap_per_family": 3},
    )
    assert report["run_status"] == "PARTIAL"
    assert report["retrieval_summary"]["selected_total"] == 1
    assert report["provenance_summary"]["candidate_ids"] == ["GCA-008ae3aad1a64c118318ef79"]
    assert json.dumps(report, sort_keys=True)


def test_parser_v3_prompt_forbids_inference_and_preserves_ambiguity():
    assert case_prompt.PROMPT_VERSION == "casecontext-parser-prompt/3.0"
    text = (case_prompt.SYSTEM_PROMPT + case_prompt.TASK_PROMPT).casefold()
    assert "do not infer" in text
    assert "ambigu" in text
    assert "do not propose" in text


def test_reader_v3_contract_describes_observations_not_support_labels():
    required = set(prompt_v3.TOOL_SCHEMA["required"])
    assert {
        "decision", "source_unit_id", "quote", "observed_disease", "observed_gene",
        "observed_alteration", "observed_drug", "observed_direction",
        "observed_evidence_type", "abstain_reason",
    } <= required
    serialized = json.dumps(prompt_v3.TOOL_SCHEMA)
    assert "FULL_SUPPORT" not in serialized
    assert "PARTIAL_SUPPORT" not in serialized


def test_reader_v3_quote_must_be_literal_and_specific_variant_is_not_inferred():
    unit = {
        "source_unit_id": "SU-1", "document_id": "pmid:19223544",
        "text": "KRAS mutations are clinically resistant to therapy with panitumumab.",
    }
    candidate = kg_retrieval.load_candidates()["GCA-008ae3aad1a64c118318ef79"]
    enrichment = {
        "decision": "QUOTE", "source_unit_id": "SU-1",
        "quote": unit["text"], "observed_disease": "colorectal cancer",
        "observed_gene": "KRAS", "observed_alteration": "",
        "observed_drug": "panitumumab", "observed_direction": "RESISTANCE",
        "observed_evidence_type": "PREDICTIVE", "notes": "", "abstain_reason": "",
    }
    valid = validate_enrichment_v3(
        "V3_TRANSPORT_VALID", enrichment, candidate=candidate,
        paper_bundle={"document_id": "pmid:19223544", "resolved_source_unit_ids": ["SU-1"]},
        source_units_by_id={"SU-1": unit},
    )
    assert valid["outcome"] == "ENRICHMENT_V3_ACCEPTED"
    support = assess_relation_support(candidate, enrichment)
    assert support["fields"]["alteration"] == "NOT_CONFIRMED"
    invalid = validate_enrichment_v3(
        "V3_TRANSPORT_VALID", {**enrichment, "quote": "invented quote"},
        candidate=candidate,
        paper_bundle={"document_id": "pmid:19223544", "resolved_source_unit_ids": ["SU-1"]},
        source_units_by_id={"SU-1": unit},
    )
    assert invalid["outcome"] == "QUOTE_INVALID"


def test_insufficient_case_context_stops_before_retrieval_with_canonical_dossier():
    calls = {"retrieval": 0}
    context = {
        "case_id": "CASE-EMPTY", "disease": {"raw_value": "colorectal cancer"},
        "biomarkers": [], "previous_interventions": [], "target_intervention": None,
        "query_intent": None, "uncertainties": [],
    }

    def retrieve(_):
        calls["retrieval"] += 1
        raise AssertionError("retrieval must not run")

    with TemporaryDirectory() as tmp:
        run = orchestrator.run_case(
            case_id="CASE-EMPTY", clinical_text="colorectal cancer",
            call_parser_fn=_parser(context), call_enricher_fn=lambda *a, **k: {},
            source_units_by_id={}, budget=CallBudget(2),
            ledger=EventLedger(Path(tmp) / "empty.sqlite3"),
            research_frozen_artifacts=True, retrieve_fn=retrieve,
            match_verifier_fn=lambda *_: {
                "records": [], "essential_fields_pass": True, "warnings": [], "bypassed": True,
            }, call_narrator_fn=None,
        )
    assert calls["retrieval"] == 0
    assert run.relation_aware_report["run_status"] == "INSUFFICIENT_CASE_CONTEXT"
    assert run.relation_aware_report["paper_evidence"] == []
