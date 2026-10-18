import json

from backend.research_pipeline.narrative import input_projection
from backend.research_pipeline.narrative.input_projection import build_narrator_input
from backend.research_pipeline.narrative.verifier import FAIL, verify_narrative
from backend.research_pipeline.narrative.prompt import SYSTEM_PROMPT
import pytest


def _report():
    return {
        "case_summary": {"case_id": "C"},
        "paper_evidence": [{
            "candidate_id": "P", "relation": "supports", "document_id": "pmid:1",
            "quote": "validated quote", "quote_valid": True,
            "support_level": "PARTIAL_SUPPORT", "support_fields": {},
            "graph_provenance": {},
        }],
        "clinical_trials": [{
            "candidate_id": "T", "nct_id": "NCT00000001", "title": "Trial",
            "conditions": ["Cancer"], "interventions": [{"name": "Drug X"}],
            "phase": ["PHASE1"], "status": "RECRUITING",
            "trial_resolution_status": "RESOLVED", "eligibility_status": "NOT_EVALUATED",
            "evidence_interpretation": "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE",
            "graph_provenance": {},
        }],
        "kg_only_relations": [{
            "candidate_id": "K", "subject": {"label": "GENE"},
            "relation": "gene_drug_interaction", "object": {"label": "Drug Y"},
            "disease_context": [], "direction": None, "evidence_type": "MyCancerGenome",
            "source_database": "MyCancerGenome", "graph_provenance": {},
            "verification_status": "KG_ONLY", "document_provenance": "NOT_AVAILABLE",
        }],
        "limitations": [], "provenance_summary": {}, "run_status": "PARTIAL",
    }


def test_narrator_projection_contains_all_three_relation_families():
    projected = build_narrator_input(_report())
    assert {item["candidate_id"] for item in projected["candidates"]} == {"P", "T", "K"}
    assert projected["clinical_trials"][0]["eligibility_status"] == "NOT_EVALUATED"
    assert projected["kg_only_relations"][0]["verification_status"] == "KG_ONLY"
    kg_candidate = next(item for item in projected["candidates"] if item["candidate_id"] == "K")
    assert kg_candidate["canonical_status"] == "KG_ONLY"


def test_canonical_case_summary_reaches_narrator_without_legacy_context():
    report = _report()
    report["case_summary"] = {"case_id": "BRAF-case", "disease": "colorectal cancer",
                              "gene": "BRAF", "variant": "V600E",
                              "intent": "THERAPY_DISCOVERY", "intervention": None}
    case = build_narrator_input(report)["case"]
    assert case["case_id"] == "BRAF-case"
    assert case["disease"] == "colorectal cancer"
    assert case["query_intent"] == "THERAPY_DISCOVERY"
    assert case["biomarkers"] == ["BRAF V600E"]
    assert case["target_intervention"] == ""


def test_narrator_projection_computes_deterministic_summary_facts():
    projected = build_narrator_input(_report())

    assert projected["summary_facts"] == {
        "candidate_count": 3,
        "paper_count": 1,
        "trial_count": 1,
        "kg_only_count": 1,
        "full_support_count": 0,
        "partial_support_count": 1,
        "no_support_count": 0,
        "contradictory_count": 0,
        "unverifiable_count": 0,
        # A legacy quote_valid boolean is not record-level authentication.
        "validated_quote_count": 0,
    }


def test_aggregated_summary_from_summary_facts_passes_verifier():
    report = _report()
    report["paper_evidence"] = [
        {**report["paper_evidence"][0], "candidate_id": "P1"},
        {**report["paper_evidence"][0], "candidate_id": "P2"},
        {**report["paper_evidence"][0], "candidate_id": "P3",
         "support_level": "UNVERIFIABLE", "quote": None, "quote_valid": False},
    ]
    report["clinical_trials"] = [
        {**report["clinical_trials"][0], "candidate_id": f"T{i}"}
        for i in range(1, 4)
    ]
    report["kg_only_relations"] = [
        {**report["kg_only_relations"][0], "candidate_id": f"K{i}"}
        for i in range(1, 4)
    ]
    projected = build_narrator_input(report)
    assert projected["summary_facts"] == {
        "candidate_count": 9,
        "paper_count": 3,
        "trial_count": 3,
        "kg_only_count": 3,
        "full_support_count": 0,
        "partial_support_count": 2,
        "no_support_count": 0,
        "contradictory_count": 0,
        "unverifiable_count": 1,
        "validated_quote_count": 0,
    }
    narrative = _narrative(projected, {
        candidate["candidate_id"]: "La relazione resta descrittiva."
        for candidate in projected["candidates"]
    })
    narrative["narrative_summary"] = (
        "Il dossier contiene due evidenze con supporto parziale, una candidate "
        "non verificabile, tre associazioni a trial e tre relazioni KG-only."
    )
    result = verify_narrative(report, projected, narrative)
    assert result["status"] == "PASS", result["reason_codes"]


def _narrative(projected, text_by_id):
    return {"candidate_narratives": [
        {"candidate_id": cid, "text": text}
        for cid, text in text_by_id.items()
    ]}


def test_trial_efficacy_and_eligibility_claims_are_rejected():
    report = _report()
    projected = build_narrator_input(report)
    result = verify_narrative(report, projected, _narrative(projected, {
        "P": "The partial paper observation is uncertain.",
            "T": "This trial demonstrates efficacy; the patient is eligible.",
        "K": "The graph relation remains contextual.",
    }))
    assert result["status"] == FAIL
    assert "NARRATIVE_TRIAL_EFFICACY_ESCALATION" in result["reason_codes"]
    assert "NARRATIVE_TRIAL_ELIGIBILITY_ESCALATION" in result["reason_codes"]


def test_trial_negated_eligibility_is_allowed_but_positive_claim_is_not():
    report = _report()
    projected = build_narrator_input(report)
    base = {"P": "The paper observation is partial.", "K": "The graph relation is contextual."}
    allowed = verify_narrative(report, projected, _narrative(projected, {
        **base, "T": "A trial record evaluates drug X; patient eligibility was not evaluated."
    }))
    assert "NARRATIVE_TRIAL_ELIGIBILITY_ESCALATION" not in allowed["reason_codes"]
    blocked = verify_narrative(report, projected, _narrative(projected, {
        **base, "T": "The patient meets the eligibility criteria and qualifies for the trial."
    }))
    assert "NARRATIVE_TRIAL_ELIGIBILITY_ESCALATION" in blocked["reason_codes"]


def test_authorized_trial_nct_is_not_rejected_as_an_unknown_identifier():
    report = _report()
    projected = build_narrator_input(report)
    result = verify_narrative(report, projected, _narrative(projected, {
        "P": "The paper observation is partial.",
        "T": "Trial NCT00000001 is contextual; patient eligibility was not evaluated.",
        "K": "The graph relation is contextual.",
    }))
    assert "NARRATIVE_UNAUTHORIZED_ENTITY" not in result["reason_codes"]


def test_narrative_trace_projects_provenance_for_all_three_branches_without_mutation():
    import copy

    report = _report()
    before = copy.deepcopy(report)
    trace = input_projection.build_narrative_trace(report)
    by_candidate = {entry["candidate_id"]: entry for entry in trace["candidates"]}

    assert report == before
    assert by_candidate["P"]["branch"] == "PAPER"
    assert by_candidate["P"]["document"]["document_id"] == "pmid:1"
    assert by_candidate["P"]["document"]["validated_quote"] == "validated quote"
    assert by_candidate["T"]["branch"] == "TRIAL"
    assert by_candidate["T"]["trial"]["nct_id"] == "NCT00000001"
    assert by_candidate["T"]["trial"]["eligibility_status"] == "NOT_EVALUATED"
    assert by_candidate["K"]["branch"] == "KG_ONLY"
    assert by_candidate["K"]["graph"]["verification_status"] == "KG_ONLY"
    assert by_candidate["K"]["graph"]["document_provenance"] == "NOT_AVAILABLE"


def test_trial_modal_eligibility_claim_is_rejected():
    report = _report()
    projected = build_narrator_input(report)
    result = verify_narrative(report, projected, _narrative(projected, {
        "P": "The paper observation is partial.",
        "T": "The patient would qualify for the trial.",
        "K": "The graph relation is contextual.",
    }))
    assert "NARRATIVE_TRIAL_ELIGIBILITY_ESCALATION" in result["reason_codes"]


def test_kg_only_documentary_claim_is_rejected():
    report = _report()
    projected = build_narrator_input(report)
    result = verify_narrative(report, projected, _narrative(projected, {
        "P": "The paper is partial.",
        "T": "The trial is contextual, not efficacy evidence.",
        "K": "This is validated quote and documentary evidence.",
    }))
    assert result["status"] == FAIL
    assert "NARRATIVE_KG_ONLY_DOCUMENTARY_ESCALATION" in result["reason_codes"]


def test_kg_only_context_only_status_rewording_is_rejected():
    report = _report()
    projected = build_narrator_input(report)
    result = verify_narrative(report, projected, _narrative(projected, {
        "P": "The paper is partial.",
        "T": "The trial is contextual, not efficacy evidence.",
        "K": "The canonical status is CONTEXT_ONLY, with graph provenance only.",
    }))
    assert result["status"] == FAIL
    assert "NARRATIVE_KG_ONLY_STATUS_MISMATCH" in result["reason_codes"]


def test_kg_only_documentary_absence_is_not_status_escalation():
    report = _report()
    projected = build_narrator_input(report)
    result = verify_narrative(report, projected, _narrative(projected, {
        "P": "The paper is partial.",
        "T": "The trial is contextual, not efficacy evidence.",
        "K": "The KG_ONLY association is not supported by documentary evidence.",
    }))
    assert result["status"] == "PASS"
    assert "NARRATIVE_STATUS_ESCALATION" not in result["reason_codes"]


def test_full_paper_support_remains_narratable():
    report = _report()
    report["paper_evidence"][0]["support_level"] = "FULL_SUPPORT"
    projected = build_narrator_input(report)
    result = verify_narrative(report, projected, _narrative(projected, {
        "P": "The paper relation is fully supported.",
        "T": "The trial is contextual, not efficacy evidence.",
        "K": "The graph relation remains contextual.",
    }))
    assert "NARRATIVE_STATUS_ESCALATION" not in result["reason_codes"]


def test_global_summary_escalation_is_rejected():
    report = _report()
    projected = build_narrator_input(report)
    narrative = _narrative(projected, {
        "P": "The paper observation is partial.",
        "T": "The trial is contextual.", "K": "The graph relation is contextual.",
    })
    narrative["narrative_summary"] = "All candidates are fully supported."
    result = verify_narrative(report, projected, narrative)
    assert result["status"] == FAIL
    assert "NARRATIVE_SUPPORT_LEVEL_ESCALATION" in result["reason_codes"]


def test_narrator_prompt_declares_all_three_families():
    for phrase in ("PAPER", "TRIAL", "KG_ONLY", "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE",
                   "eligibility_status=NOT_EVALUATED", "verification_status=KG_ONLY",
                   "document_provenance=NOT_AVAILABLE"):
        assert phrase in SYSTEM_PROMPT


def test_narrator_prompt_uses_the_canonical_full_support_vocabulary():
    assert "FULL_SUPPORT" in SYSTEM_PROMPT
    assert "STRONG_SUPPORT" not in SYSTEM_PROMPT


def test_verifier_detects_rejected_quote_without_legacy_candidate_therapies():
    report = _report()
    rejected = "This rejected source statement must never be presented as validated evidence."
    report["paper_evidence"][0]["quote_valid"] = False
    report["paper_evidence"][0]["rejected_quotes"] = [{"quote": rejected}]
    projected = build_narrator_input(report)
    assert "candidate_therapies" not in report
    narrative = _narrative(projected, {
        "P": f'"{rejected}"', "T": "The trial is contextual.",
        "K": "The graph relation is contextual.",
    })
    result = verify_narrative(report, projected, narrative)
    assert result["status"] == FAIL
    assert "NARRATIVE_REJECTED_QUOTE_PROMOTED" in result["reason_codes"]


def test_projection_does_not_expose_rejected_quote_payload_to_narrator():
    report = _report()
    rejected = "This rejected source statement must never be presented as validated evidence."
    report["paper_evidence"][0]["quote_valid"] = False
    report["paper_evidence"][0]["quote"] = rejected
    report["paper_evidence"][0]["rejected_quotes"] = [{"quote": rejected}]
    projected = build_narrator_input(report)
    assert rejected not in json.dumps(projected, ensure_ascii=False)


def test_projection_is_pure_and_preserves_canonical_report():
    import copy
    report = _report()
    before = copy.deepcopy(report)
    projected = build_narrator_input(report)
    assert report == before
    assert projected["counts"]["candidates"] == 3
    projected["paper_evidence"][0]["support_fields"]["gene"] = "MUTATED"
    projected["clinical_trials"][0]["conditions"].append("MUTATED")
    projected["kg_only_relations"][0]["graph_provenance"]["mutated"] = True
    projected["candidates"][1]["trial_context"]["conditions"].append("MUTATED_CANDIDATE")
    projected["candidates"][2]["kg_context"]["graph_provenance"]["mutated"] = True
    projected["candidates"][0]["support_mask"]["gene"] = "MUTATED_CANDIDATE"
    assert report == before


@pytest.mark.parametrize("branches", [
    ("paper_evidence",), ("clinical_trials",), ("kg_only_relations",),
    ("paper_evidence", "clinical_trials"),
    ("paper_evidence", "kg_only_relations"),
    ("clinical_trials", "kg_only_relations"),
    ("paper_evidence", "clinical_trials", "kg_only_relations"),
])
def test_each_branch_combination_is_projected_without_dropping_families(branches):
    report = _report()
    expected = {"P": "paper_evidence", "T": "clinical_trials", "K": "kg_only_relations"}
    for candidate_id, key in expected.items():
        if key not in branches:
            report[key] = []
    projected = build_narrator_input(report)
    assert {item["candidate_id"] for item in projected["candidates"]} == {
        cid for cid, key in expected.items() if key in branches
    }
