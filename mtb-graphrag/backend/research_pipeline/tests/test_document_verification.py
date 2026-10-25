"""Focused EVIDENCE_DRUG verification; no live LLM or final evaluation."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from backend.pipeline.agentic.ledger import EventLedger
from backend.research_pipeline.casecontext.parser import adapt_case_context
from backend.research_pipeline.dossier.builder import is_aggregation_eligible
from backend.research_pipeline.enrichment.document_verification import (
    admit, structural_verify,
)
from backend.research_pipeline.enrichment.semantic_alignment import (
    call_semantic_alignment, render_request, validate_output,
)
from backend.research_pipeline.enrichment.validator_v3 import validate_enrichment_v3
from backend.research_pipeline.orchestrator import run_case
from backend.research_pipeline.pipeline import CallBudget
from backend.research_pipeline.tests.test_semantic_admission_contract import assessment
from backend.research_pipeline.retrieval.kg_retrieval import load_candidates
from backend.research_pipeline.tests.test_orchestrated_pre_freeze_matrix import (
    ControlledDocumentRuntime, _paper_candidate, _parser_output,
    _reader_observation, _source_unit,
)


def _candidate(**changes):
    return _paper_candidate(**{"relation_family": "EVIDENCE_DRUG", **changes})


def _structural(text, *, candidate=None, observed=None, document_id="pmid:12345678", case_context=None):
    candidate = candidate or _candidate()
    unit = _source_unit(text, document_id=document_id)
    reader = observed or _reader_observation(candidate, [unit])["enrichment"]
    paper = {"document_id": document_id, "resolved_source_unit_ids": [unit["source_unit_id"]]}
    return structural_verify(candidate, paper, unit, reader, case_context=case_context)


def test_structural_direct_positive_and_trace():
    text = "EGFR L858R showed sensitivity to erlotinib in lung cancer."
    result = _structural(text)
    assert result["structural_status"] == "PASS", result
    assert result["GEP_snapshot"]["quote_offset"] == 0
    assert result["target_snapshot"]["candidate_id"] == _candidate()["candidate_id"]


def test_structural_and_admission_repeatability():
    text = "EGFR L858R showed sensitivity to erlotinib in lung cancer."
    outputs = [admit(_structural(text), assessment(text))
               for _ in range(2)]
    assert json.dumps(outputs[0], sort_keys=True) == json.dumps(outputs[1], sort_keys=True)


def test_reader_cannot_cross_pair_around_competing_identifier():
    candidate = _candidate(biomarkers=[
        {"label": "EGFR", "type": "Gene"},
        {"label": "G12C", "type": "Variant", "gene": "EGFR"},
    ])
    text = "EGFR and KRAS G12C showed sensitivity to erlotinib in lung cancer."
    unit = _source_unit(text)
    reader = _reader_observation(candidate, [unit])["enrichment"]
    result = structural_verify(candidate, {"document_id": unit["document_id"],
                                           "resolved_source_unit_ids": [unit["source_unit_id"]]},
                               unit, reader)
    assert result["structural_status"] == "UNRESOLVED"
    assert "GENE_VARIANT_PAIR_NOT_ADJACENT" in result["structural_reason_codes"]


@pytest.mark.parametrize("regimen", ["erlotinib + cetuximab", "erlotinib and cetuximab",
                                    "cetuximab + erlotinib"])
def test_reader_single_scope_does_not_hide_explicit_drug_coordination(regimen):
    text = f"EGFR L858R showed sensitivity to {regimen} in lung cancer."
    result = _structural(text)
    assert result["structural_status"] == "UNRESOLVED"
    assert "POSSIBLE_MULTI_AGENT_INTERVENTION" in result["structural_reason_codes"]


def test_explicit_alternative_drugs_license_target_specific_semantic_review():
    candidate = _candidate(interventions=[{"label": "panitumumab", "type": "Drug"}])
    text = "EGFR L858R showed sensitivity to panitumumab or cetuximab in lung cancer."
    unit = _source_unit(text)
    reader = _reader_observation(candidate, [unit])["enrichment"]
    reader["observed_relation"]["intervention"] = "panitumumab or cetuximab"

    result = structural_verify(
        candidate,
        {"document_id": unit["document_id"], "resolved_source_unit_ids": [unit["source_unit_id"]]},
        unit,
        reader,
    )

    assert result["structural_status"] == "PASS", result
    assert result["GEP_snapshot"]["grounded_arguments"]["candidate_intervention"] == "panitumumab"
    assert result["GEP_snapshot"]["grounded_arguments"]["intervention_match"] == "EXPLICIT_ALTERNATIVE"
    assert admit(result, None)["final_admission"] == "UNVERIFIABLE"


def test_explicit_alternatives_do_not_override_combination_scope():
    candidate = _candidate(interventions=[{"label": "panitumumab", "type": "Drug"}])
    text = "EGFR L858R showed sensitivity to panitumumab or cetuximab in lung cancer."
    unit = _source_unit(text)
    reader = _reader_observation(candidate, [unit])["enrichment"]
    reader["observed_relation"]["intervention"] = "panitumumab or cetuximab"
    reader["observed_relation"]["relation_scope"] = "COMBINATION"

    result = structural_verify(
        candidate,
        {"document_id": unit["document_id"], "resolved_source_unit_ids": [unit["source_unit_id"]]},
        unit,
        reader,
    )

    assert result["structural_status"] == "UNRESOLVED"
    assert "RELATION_SCOPE_NOT_ATOMIC" in result["structural_reason_codes"]


def test_erbb2_full_name_alias_is_exact_and_does_not_change_alteration_identity():
    candidate = _candidate(
        biomarkers=[{"label": "ERBB2", "type": "Gene"}],
        interventions=[{"label": "pictilisib", "type": "Drug"}],
    )
    text = "Human epidermal growth factor receptor 2 showed sensitivity to GDC-0941 in lung cancer."
    unit = _source_unit(text)
    reader = _reader_observation(candidate, [unit])["enrichment"]
    reader["observed_relation"]["subjects"] = [{
        "type": "GENE", "surface_value": "Human epidermal growth factor receptor 2",
    }]
    reader["observed_relation"]["subject_pairings"] = []
    reader["observed_relation"]["intervention"] = "GDC-0941"

    result = structural_verify(
        candidate,
        {"document_id": unit["document_id"], "resolved_source_unit_ids": [unit["source_unit_id"]]},
        unit,
        reader,
    )

    assert result["structural_status"] == "PASS", result
    wrong_alteration = _candidate(
        biomarkers=[{"label": "ERBB2 Amplification", "type": "Alteration"}],
        interventions=[{"label": "pictilisib", "type": "Drug"}],
    )
    wrong_result = structural_verify(
        wrong_alteration,
        {"document_id": unit["document_id"], "resolved_source_unit_ids": [unit["source_unit_id"]]},
        unit,
        reader,
    )
    assert wrong_result["structural_status"] != "PASS"


@pytest.mark.parametrize("mutation, expected", [
    ("wrong_document", "MISMATCH"),
    ("wrong_source_unit", "MISMATCH"),
    ("invalid_quote", "MISMATCH"),
    ("wrong_gene", "UNRESOLVED"),
    ("wrong_variant", "MISMATCH"),
    ("compound_variant", "UNRESOLVED"),
    ("wrong_drug", "MISMATCH"),
    ("combination", "UNRESOLVED"),
    ("wrong_disease", "MISMATCH"),
    ("cross_pair", "UNRESOLVED"),
])
def test_structural_hostile_mutations(mutation, expected):
    text = "EGFR L858R showed sensitivity to erlotinib in lung cancer."
    candidate = _candidate()
    unit = _source_unit(text)
    paper = {"document_id": unit["document_id"], "resolved_source_unit_ids": [unit["source_unit_id"]]}
    observed = _reader_observation(candidate, [unit])["enrichment"]
    if mutation == "wrong_document":
        paper["document_id"] = "pmid:99999999"
    elif mutation == "wrong_source_unit":
        paper["resolved_source_unit_ids"] = ["other"]
    elif mutation == "invalid_quote":
        observed["quote"] = "invented quote"
    elif mutation == "wrong_gene":
        observed["observed_relation"]["subjects"][0]["surface_value"] = "KRAS"
        unit["text"] += " KRAS."
        observed["quote"] = unit["text"]
    elif mutation == "wrong_variant":
        observed["observed_relation"]["subjects"][1]["surface_value"] = "T790M"
        unit["text"] += " T790M."
        observed["quote"] = unit["text"]
    elif mutation == "compound_variant":
        unit["text"] = "EGFR L858R/T790M showed sensitivity to erlotinib in lung cancer."
        observed["quote"] = unit["text"]
    elif mutation == "wrong_drug":
        observed["observed_relation"]["intervention"] = "gefitinib"
        unit["text"] += " gefitinib."
        observed["quote"] = unit["text"]
    elif mutation == "combination":
        unit["text"] = "EGFR L858R showed sensitivity to erlotinib plus cetuximab in lung cancer."
        observed["quote"] = unit["text"]
        observed["observed_relation"]["relation_scope"] = "COMBINATION"
    elif mutation == "wrong_disease":
        observed["observed_relation"]["disease"] = "breast cancer"
        unit["text"] += " breast cancer."
        observed["quote"] = unit["text"]
    elif mutation == "cross_pair":
        unit["text"] = "EGFR L858R and KRAS G12C showed sensitivity to erlotinib in lung cancer."
        observed["quote"] = unit["text"]
        observed["observed_relation"]["subjects"].extend([
            {"type": "GENE", "surface_value": "KRAS"},
            {"type": "ALTERATION", "surface_value": "G12C"},
        ])
    result = structural_verify(candidate, paper, unit, observed)
    assert result["structural_status"] == expected, result
    assert admit(result, {"relation_alignment": "SAME", "assertion_scope": "DIRECT_ASSERTION",
                          "reason": "forced", "decisive_text": "x"})["final_admission"] != "DOCUMENT_SUPPORTED"


@pytest.mark.parametrize("label, scope, final", [
    ("SAME", "DIRECT_ASSERTION", "DOCUMENT_SUPPORTED"),
    ("OPPOSITE", "DIRECT_ASSERTION", "REJECTED"),
    ("INSUFFICIENT", "DIRECT_ASSERTION", "INSUFFICIENT_INFORMATION"),
    ("AMBIGUOUS", "DIRECT_ASSERTION", "UNVERIFIABLE"),
    ("SAME", "REPORTED_PRIOR_WORK", "UNVERIFIABLE"),
    ("SAME", "HYPOTHETICAL", "UNVERIFIABLE"),
    ("SAME", "REJECTED_ASSERTION", "UNVERIFIABLE"),
    ("SAME", "UNCERTAIN_ASSERTION", "UNVERIFIABLE"),
    ("SAME", "QUESTIONED_ASSERTION", "UNVERIFIABLE"),
    ("SAME", "UNKNOWN", "UNVERIFIABLE"),
])
def test_admission_table(label, scope, final):
    structural = _structural("EGFR L858R showed sensitivity to erlotinib in lung cancer.")
    assert admit(structural, assessment(structural["GEP_snapshot"]["required_context"],
                                       relation_alignment=label, assertion_scope=scope))[
        "final_admission"] == final


def test_semantic_contract_excludes_reader_verdict_and_requires_literal_decisive_text():
    structural = _structural("EGFR L858R showed sensitivity to erlotinib in lung cancer.")
    request = render_request(structural["target_snapshot"], structural["GEP_snapshot"])
    for forbidden in ("RELATION_ASSERTED", "observed_stance", "effect_direction", "Reader says SUPPORTS"):
        assert forbidden not in request
    assert "required_context" in request
    assert "proposition" in request
    with pytest.raises(ValueError):
        validate_output({"relation_alignment": "SAME", "assertion_scope": "DIRECT_ASSERTION",
                         "reason": "x", "decisive_text": "invented"}, structural["GEP_snapshot"])
    with pytest.raises(ValueError):
        validate_output({"relation_alignment": "UNKNOWN", "assertion_scope": "UNKNOWN",
                         "reason": "x", "decisive_text": ""}, structural["GEP_snapshot"])
    with pytest.raises(ValueError):
        validate_output({"relation_alignment": "SAME", "reason": "missing scope",
                         "decisive_text": "EGFR"}, structural["GEP_snapshot"])


def test_aggregation_rejects_stale_full_without_document_admission():
    record = {"relation_family": "EVIDENCE_DRUG", "validation_outcome": "ENRICHMENT_V3_ACCEPTED",
              "quote_valid": True, "source_unit_id": "SU-1", "document_id": "pmid:12345678",
              "candidate_support": {"result": "FULL_SUPPORT"}}
    assert is_aggregation_eligible(record) == (False, "DOCUMENT_VERIFICATION_NOT_ADMITTED")


def test_aggregation_requires_direct_assertion_scope_for_document_full():
    record = {"relation_family": "EVIDENCE_DRUG", "validation_outcome": "ENRICHMENT_V3_ACCEPTED",
              "quote_valid": True, "source_unit_id": "SU-1", "document_id": "pmid:12345678",
              "candidate_support": {"result": "FULL_SUPPORT"},
              "document_verification": admit(_structural("EGFR L858R showed sensitivity to erlotinib in lung cancer."),
                                             assessment("EGFR L858R showed sensitivity to erlotinib in lung cancer."))}
    assert is_aggregation_eligible(record) == (True, None)
    record["document_verification"]["assertion_scope"] = "REPORTED_PRIOR_WORK"
    assert is_aggregation_eligible(record) == (False, "DOCUMENT_VERIFICATION_NOT_ADMITTED")


def test_admission_rejects_unvalidated_decisive_text():
    structural = _structural("EGFR L858R showed sensitivity to erlotinib in lung cancer.")
    semantic = {"relation_alignment": "SAME", "assertion_scope": "DIRECT_ASSERTION",
                "reason": "forced", "decisive_text": "invented"}
    assert admit(structural, semantic)["final_admission"] == "UNVERIFIABLE"


@pytest.mark.parametrize("failure", [
    "timeout", "network_failure", "invalid_json", "unknown_label",
    "missing_decisive_text", "empty_response", "provider_exception",
])
def test_semantic_provider_failures_never_admit(failure):
    structural = _structural("EGFR L858R showed sensitivity to erlotinib in lung cancer.")
    if failure in {"timeout", "provider_exception"}:
        error = TimeoutError("timeout") if failure == "timeout" else RuntimeError("provider failure")
        post = patch("backend.research_pipeline.enrichment.semantic_alignment.transport.post_with_infra_retry",
                     side_effect=error)
        result = None
    else:
        post = patch("backend.research_pipeline.enrichment.semantic_alignment.transport.post_with_infra_retry",
                     return_value=(None, None, "network failure", 1) if failure == "network_failure"
                     else (200, {}, None, 0))
        result = {
            "invalid_json": ("INVALID_TOOL_ARGUMENTS", None, None, []),
            "unknown_label": ("FORCED_TOOL_VALID", None, {
                "relation_alignment": "UNKNOWN", "assertion_scope": "UNKNOWN",
                "reason": "invalid", "decisive_text": ""}, []),
            "missing_decisive_text": ("FORCED_TOOL_VALID", None, {
                "relation_alignment": "SAME", "assertion_scope": "DIRECT_ASSERTION",
                "reason": "invalid", "decisive_text": ""}, []),
            "empty_response": ("MISSING_TOOL_CALL", None, None, []),
        }.get(failure)
    with post:
        if result is None:
            semantic = call_semantic_alignment(
                CallBudget(1), "provider-failure", structural["target_snapshot"], structural["GEP_snapshot"])
        else:
            with patch("backend.research_pipeline.enrichment.semantic_alignment.transport.transport_result",
                       return_value=result):
                semantic = call_semantic_alignment(
                    CallBudget(1), "provider-failure", structural["target_snapshot"], structural["GEP_snapshot"])
    assert semantic["relation_alignment"] == "AMBIGUOUS"
    assert semantic["assertion_scope"] == "UNKNOWN"
    assert admit(structural, semantic)["final_admission"] == "TECHNICAL_ERROR"


def test_structural_abstains_when_required_disease_is_not_grounded():
    text = "EGFR L858R showed sensitivity to erlotinib."
    observed = _reader_observation(_candidate(), [_source_unit(text)])["enrichment"]
    observed["observed_relation"]["disease"] = None
    result = _structural(text, observed=observed)
    assert result["structural_status"] == "UNRESOLVED"
    assert "DISEASE_CONTEXT_NOT_GROUNDED" in result["structural_reason_codes"]


def test_real_gca4_lineage_profile_is_recovered_without_inventing_regimen():
    candidate = load_candidates()["GCA4-c66674c4c007dafdffb62255"]
    text = "BRAF V600E showed sensitivity to VEMURAFENIB in Papillary Thyroid Carcinoma."
    unit = _source_unit(text, document_id="pmid:24987354")
    observed = {"source_unit_id": unit["source_unit_id"], "quote": text,
                "observed_relation": {"subjects": [
                    {"type": "GENE", "surface_value": "BRAF"},
                    {"type": "ALTERATION", "surface_value": "V600E", "linked_gene": "BRAF"}],
                    "intervention": "VEMURAFENIB", "disease": "Papillary Thyroid Carcinoma",
                    "relation_scope": "SINGLE"}}
    result = structural_verify(candidate, {"document_id": "pmid:24987354",
                                           "resolved_source_unit_ids": [unit["source_unit_id"]]},
                               unit, observed)
    assert result["structural_status"] == "PASS", result
    assert result["target_snapshot"]["profile_id"] == "MolecularProfile:12"
    assert result["target_snapshot"]["profile"] == "BRAF V600E"
    assert result["target_snapshot"]["linked_drugs"] == [
        {"id": "Drug:rxcui:1147220", "name": "VEMURAFENIB"}]


def test_real_gca_candidate_and_source_passage_reach_semantic_callback():
    candidate = load_candidates()["GCA4-c66674c4c007dafdffb62255"]
    profile_candidate = load_candidates()["GCA4-9f1374e8016ecf8c94b696c6"]
    raw = ("Papillary Thyroid Carcinoma with BRAF V600E; evaluate evidence for "
           "vemurafenib treatment.")
    context = adapt_case_context("real-gca-positive-boundary", _parser_output(
        raw, disease="Papillary Thyroid Carcinoma", biomarkers=(("BRAF", "V600E"),),
        interventions=(("vemurafenib", "TARGET"),),
    ), raw)
    passage = ("Vemurafenib showed antitumour activity in patients with progressive, "
               "BRAF(V600E)-positive papillary thyroid cancer refractory to radioactive "
               "iodine who had never been treated with a multikinase inhibitor.")
    observed_disease = ("progressive, BRAF(V600E)-positive papillary thyroid cancer "
                        "refractory to radioactive iodine")
    unit = _source_unit(passage, document_id="pmid:24987354", unit_id="SU-PMID-24987354-ABSTRACT")

    def parser(_budget, case_id, _text):
        return {"transport_result": "FORCED_TOOL_VALID", "case_context_raw": context,
                "model": "controlled-parser", "prompt_version": "controlled"}

    def reader(_budget, case_id, candidate_id, document_id, _context, _candidate, _drug, units):
        selected = next(item for item in units if item["source_unit_id"] == unit["source_unit_id"])
        return {"transport_result": "V3_TRANSPORT_VALID", "model": "controlled-reader",
                "prompt_version": "controlled", "enrichment": {
                    "decision": "QUOTE", "source_unit_id": selected["source_unit_id"],
                        "quote": selected["text"], "candidate_id": candidate_id,
                    "paper_id": document_id, "observed_relation": {
                        "subjects": [
                            {"type": "GENE", "surface_value": "BRAF"},
                            {"type": "ALTERATION", "surface_value": "V600E", "linked_gene": "BRAF"},
                        ],
                        "subject_pairings": [{"gene": "BRAF", "alteration": "V600E"}],
                            "intervention": "Vemurafenib", "disease": observed_disease,
                        "effect_direction": "SENSITIVITY_RESPONSE", "observed_stance": "SUPPORTS",
                        "relation_scope": "SINGLE", "relation_assertion": "RELATION_ASSERTED",
                    },
                }, "model_call_count": 1}

    semantic_calls = []

    def semantic(_budget, _case_id, target, gep):
        semantic_calls.append((deepcopy(target), deepcopy(gep)))
        return {**assessment(passage), "model": "controlled-semantic", "prompt_version": "controlled"}

    ledger_path = Path(__file__).with_name(f".gca4-real-positive-{uuid4().hex}.sqlite3")
    with patch("backend.research_pipeline.retrieval.kg_retrieval.load_candidates",
               return_value={candidate["candidate_id"]: candidate,
                             profile_candidate["candidate_id"]: profile_candidate}):
        try:
            run = run_case(
                case_id="real-gca-positive-boundary", clinical_text=raw, call_parser_fn=parser,
                call_enricher_fn=reader, call_semantic_alignment_fn=semantic,
                source_units_by_id={}, budget=CallBudget(20), ledger=EventLedger(ledger_path),
                document_runtime=ControlledDocumentRuntime([unit]), validate_fn=validate_enrichment_v3,
            )
        finally:
            for suffix in ("", "-wal", "-shm"):
                Path(f"{ledger_path}{suffix}").unlink(missing_ok=True)
    validation_stage = next(s for s in run.stages if s.stage_id == "stage_10_enrichment_validation")
    assert len(semantic_calls) == 1
    assert validation_stage.output_preview["semantic_verification"]["attempted_calls"] == 1
    assert semantic_calls[0][0]["candidate_id"].startswith("GCA4-DERIVED-")
    assert semantic_calls[0][1]["source_unit_id"] == unit["source_unit_id"]
    verdict = next(v for v in validation_stage.output_preview["validations"]
                   if v.get("candidate_id") == semantic_calls[0][0]["candidate_id"])
    assert "DISEASE_CONTEXT_REQUIRES_SEMANTIC_REVIEW" in verdict[
        "document_verification"]["structural_reason_codes"]


def test_real_gca_candidate_rejects_non_selected_source_unit_before_semantics():
    candidate = load_candidates()["GCA4-c66674c4c007dafdffb62255"]
    text = "Extended Antitumor Response of a BRAF V600E Papillary Thyroid Carcinoma to Vemurafenib."
    unit = _source_unit(text, document_id="pmid:24987354", unit_id="SU-PMID-24987354-UNSELECTED")
    observed = {
        "source_unit_id": unit["source_unit_id"], "quote": text,
        "observed_relation": {"subjects": [
            {"type": "GENE", "surface_value": "BRAF"},
            {"type": "ALTERATION", "surface_value": "V600E", "linked_gene": "BRAF"},
        ], "intervention": "Vemurafenib", "disease": "Papillary Thyroid Carcinoma",
            "relation_scope": "SINGLE"},
    }
    result = structural_verify(candidate,
                               {"document_id": "pmid:24987354", "resolved_source_unit_ids": ["SU-OTHER"]},
                               unit, observed)
    assert result["structural_status"] == "MISMATCH"
    assert "SOURCE_UNIT_NOT_AUTHORIZED" in result["structural_reason_codes"]


def test_papillary_thyroid_cancer_alias_reaches_semantics_with_limited_context():
    candidate = load_candidates()["GCA4-c66674c4c007dafdffb62255"]
    quote = ("Vemurafenib showed antitumour activity in patients with progressive, "
             "BRAF(V600E)-positive papillary thyroid cancer refractory to radioactive "
             "iodine who had never been treated with a multikinase inhibitor.")
    unit = _source_unit(quote, document_id="pmid:24987354", unit_id="SU-24987354-ABSTRACT")
    observation = {
        "source_unit_id": unit["source_unit_id"], "quote": quote,
        "observed_relation": {
            "subjects": [
                {"type": "GENE", "surface_value": "BRAF"},
                {"type": "ALTERATION", "surface_value": "V600E", "linked_gene": "BRAF"},
            ],
            "intervention": "Vemurafenib",
            "disease": "progressive, BRAF(V600E)-positive papillary thyroid cancer refractory to radioactive iodine",
            "effect_direction": "SENSITIVITY_RESPONSE", "observed_stance": "SUPPORTS",
            "relation_scope": "SINGLE", "relation_assertion": "RELATION_ASSERTED",
        },
    }
    result = structural_verify(
        candidate, {"document_id": "pmid:24987354",
                    "resolved_source_unit_ids": [unit["source_unit_id"]]},
        unit, observation,
    )
    assert result["structural_status"] == "PASS", result
    assert "DISEASE_CONTEXT_REQUIRES_SEMANTIC_REVIEW" in result["structural_reason_codes"]


def test_missing_optional_lineage_index_abstains_for_real_gca4_candidate():
    candidate = load_candidates()["GCA4-c66674c4c007dafdffb62255"]
    text = "BRAF V600E showed sensitivity to VEMURAFENIB in Papillary Thyroid Carcinoma."
    unit = _source_unit(text, document_id="pmid:24987354")
    observed = {"source_unit_id": unit["source_unit_id"], "quote": text,
                "observed_relation": {"subjects": [
                    {"type": "GENE", "surface_value": "BRAF"},
                    {"type": "ALTERATION", "surface_value": "V600E", "linked_gene": "BRAF"}],
                    "intervention": "VEMURAFENIB", "disease": "Papillary Thyroid Carcinoma",
                    "relation_scope": "SINGLE"}}
    with patch("backend.research_pipeline.enrichment.document_verification._lineage_index", return_value={}):
        result = structural_verify(candidate, {"document_id": "pmid:24987354",
                                               "resolved_source_unit_ids": [unit["source_unit_id"]]},
                                   unit, observed)
    assert result["structural_status"] == "UNRESOLVED"
    assert "TARGET_MOLECULAR_CONDITION_UNSPECIFIED" in result["structural_reason_codes"]


def _run(text: str, semantic_status: str | None, *, case_id: str,
         assertion_scope: str = "DIRECT_ASSERTION", reader_abstains: bool = False,
         reader_transport_failure: bool = False, semantic_fields: dict | None = None,
         narrative_text: str | None = None, narrative_entry_fields: dict | None = None,
         candidate_overrides: list[dict] | None = None,
         relation_family: str = "EVIDENCE_DRUG"):
    candidate = _candidate(relation_family=relation_family)
    candidates = [candidate, *(candidate_overrides or [])]
    raw = "lung cancer with EGFR L858R; current target erlotinib."
    context = adapt_case_context(case_id, _parser_output(raw), raw)

    def parser(_budget, _case_id, _text):
        return {"transport_result": "FORCED_TOOL_VALID", "case_context_raw": context,
                "model": "controlled-parser", "prompt_version": "controlled"}

    def reader(_budget, _case_id, _candidate_id, _document_id, _context,
               candidate_, _drug, units):
        if reader_transport_failure:
            return {"transport_result": "INVALID_TOOL_ARGUMENTS", "enrichment": None,
                    "model_call_count": 1}
        if reader_abstains:
            return {"transport_result": "V3_TRANSPORT_VALID", "enrichment": {
                "decision": "ABSTAIN", "abstain_reason": "NO_RELEVANT_EVIDENCE",
                "source_unit_id": None, "quote": None, "observed_relation": None,
            }, "model_call_count": 1}
        return _reader_observation(candidate_, units)

    semantic_calls = []

    def semantic(_budget, _case_id, target, gep):
        semantic_calls.append((deepcopy(target), deepcopy(gep)))
        status = (semantic_status.get(target.get("candidate_id"))
                  if isinstance(semantic_status, dict) else semantic_status)
        if status is None:
            raise RuntimeError("controlled failure")
        return {**assessment(text, relation_alignment=status, assertion_scope=assertion_scope,
                             **(semantic_fields or {})),
                "model": "controlled-semantic", "prompt_version": "controlled/2.0"}

    def narrator(_case_id, narrator_input):
        candidate = narrator_input["candidates"][0]
        entry = {"candidate_id": candidate["candidate_id"], "text": narrative_text or
                 "Il dossier riporta lo stato documentale registrato per questa relazione."}
        entry.update(narrative_entry_fields or {})
        return {
            "transport_result": "FORCED_TOOL_VALID", "model": "controlled-narrator",
            "narrative": {
                "narrative_summary": "Il dossier contiene una relazione documentale.",
                "candidate_narratives": [entry],
                "limitations_summary": "Sintesi di ricerca, non raccomandazione clinica.",
                "closing_note": "Per revisione del team multidisciplinare.",
                "narrative_hash": "controlled-narrative-hash",
            },
        }

    unit = _source_unit(text)
    # pytest's Windows tmp_path directories inherit a sandbox ACL that blocks
    # nested SQLite/WAL operations in this workspace. Keep the ledger file
    # directly in this already-existing test directory and remove its sidecars.
    ledger_path = Path(__file__).with_name(f".gca4-test-{uuid4().hex}.sqlite3")
    try:
        with patch("backend.research_pipeline.retrieval.kg_retrieval.load_candidates",
                   return_value={item["candidate_id"]: item for item in candidates}):
            run = run_case(
                case_id=case_id, clinical_text=raw, call_parser_fn=parser,
                call_enricher_fn=reader, call_semantic_alignment_fn=semantic,
                source_units_by_id={}, budget=CallBudget(20),
                ledger=EventLedger(ledger_path),
                document_runtime=ControlledDocumentRuntime([unit]),
                validate_fn=validate_enrichment_v3,
                call_narrator_fn=narrator if narrative_text is not None else None,
            )
    finally:
        for suffix in ("", "-wal", "-shm"):
            Path(f"{ledger_path}{suffix}").unlink(missing_ok=True)
    return run, semantic_calls


@pytest.mark.parametrize("text,semantic_status,expected", [
    ("EGFR L858R showed sensitivity to erlotinib in lung cancer.", "SAME", "FULL_SUPPORT"),
    ("Our results showed that EGFR L858R was associated with response to erlotinib in lung cancer.", "SAME", "FULL_SUPPORT"),
    ("Although other variants did not respond, EGFR L858R showed sensitivity to erlotinib in lung cancer.", "SAME", "FULL_SUPPORT"),
    ("EGFR L858R did not show sensitivity to erlotinib in lung cancer.", "OPPOSITE", "CONTRADICTORY"),
    ("Previous studies reported that EGFR L858R showed sensitivity to erlotinib in lung cancer.", "AMBIGUOUS", "UNVERIFIABLE"),
    ("It was hypothesized that EGFR L858R showed sensitivity to erlotinib in lung cancer.", "AMBIGUOUS", "UNVERIFIABLE"),
    ("The finding that EGFR L858R showed sensitivity to erlotinib in lung cancer was retracted.", "AMBIGUOUS", "UNVERIFIABLE"),
    ("EGFR L858R and erlotinib were studied in lung cancer.", "INSUFFICIENT", "INSUFFICIENT_INFORMATION"),
    ("EGFR L858R showed sensitivity to erlotinib in lung cancer.", None, "UNVERIFIABLE"),
])
def test_real_orchestrator_semantic_boundary(text, semantic_status, expected):
    run, calls = _run(text, semantic_status, case_id=f"document-{len(text)}-{semantic_status}")
    paper = run.relation_aware_report["paper_evidence"][0]
    assert paper["claim"]["status"] == expected, paper
    assert calls and "observed_stance" not in str(calls[0])
    trace = paper["evidence_records"][0]["document_verification"]
    assert trace["candidate_id"] if "candidate_id" in trace else trace["target_snapshot"]["candidate_id"]


@pytest.mark.parametrize("semantic_status", ["SAME", None])
def test_stage_10_records_actual_semantic_attempt_even_on_failure(semantic_status):
    run, calls = _run("EGFR L858R showed sensitivity to erlotinib in lung cancer.",
                      semantic_status, case_id=f"semantic-producer-{semantic_status}")
    stage = next(s for s in run.stages if s.stage_id == "stage_10_enrichment_validation")
    assert len(calls) == 1
    assert stage.producer.kind == "HYBRID"
    assert stage.output_preview["semantic_verification"]["attempted_calls"] == 1
    assert stage.output_preview["semantic_verification"]["policy_version"].endswith("/2.1")


def test_stage_10_without_semantic_invocation_is_deterministic():
    run, calls = _run("EGFR L858R showed sensitivity to another-agent in lung cancer.",
                      "SAME", case_id="semantic-not-invoked")
    stage = next(s for s in run.stages if s.stage_id == "stage_10_enrichment_validation")
    assert calls == []
    assert stage.producer.kind == "DETERMINISTIC"
    assert stage.output_preview["semantic_verification"]["attempted_calls"] == 0
    validation = stage.output_preview["validations"][0]
    assert validation["document_verification"]["structural_status"] == "MISMATCH"


def test_evidence_statement_uses_deterministic_policy_without_semantic_llm():
    run, calls = _run(
        "EGFR L858R showed sensitivity to erlotinib in lung cancer.", "SAME",
        case_id="evidence-statement-deterministic-policy",
        relation_family="EVIDENCE_STATEMENT",
    )
    stage = next(s for s in run.stages if s.stage_id == "stage_10_enrichment_validation")

    assert calls == []
    assert stage.producer.kind == "DETERMINISTIC"
    assert stage.output_preview["semantic_verification"]["attempted_calls"] == 0
    assert stage.output_preview["validations"][0]["candidate_support"][
        "verification_policy"]["requires_semantic_comparison"] is False


def test_canonical_run_case_returns_bidirectional_dossier_reconciliation():
    run, _ = _run("EGFR L858R showed sensitivity to erlotinib in lung cancer.", "SAME",
                  case_id="dossier-reconciliation-integration")
    accounting = run.relation_aware_report["pipeline_accounting"]
    reconciliation = accounting["bidirectional_reconciliation"]
    assert reconciliation["status"] == "PASS", reconciliation
    assert reconciliation["accepted_not_represented"] == []
    assert reconciliation["claims_without_admitted_record"] == []
    assert len(accounting["reader_attempts"]["records"]) == accounting["reader_attempts"]["total"]


def test_canonical_run_case_reconciles_multiple_same_pmid_records_and_mixed_states():
    text = "EGFR L858R showed sensitivity to erlotinib in lung cancer."
    second = _candidate(candidate_id="GCA4-E2E-PAPER-SECOND",
                        semantic_key="EVIDENCE_STATEMENT|Evidence:E2E-SECOND",
                        edge_ids=["edge:e2e:2"],
                        source_record_ids=["source-row:2"])
    statuses = {"GCA4-E2E-PAPER": "SAME", "GCA4-E2E-PAPER-SECOND": "OPPOSITE"}
    run, calls = _run(text, statuses, case_id="canonical-mixed-same-pmid",
                      candidate_overrides=[second])
    report = run.relation_aware_report
    papers = report["paper_evidence"]
    assert len(calls) == 2
    assert len(papers) == 2
    assert {item["support_level"] for item in papers} == {"FULL_SUPPORT", "CONTRADICTORY"}
    assert {item["document_id"] for item in papers} == {"pmid:12345678"}
    assert {item["evidence_records"][0]["source_unit_id"] for item in papers} == {
        _source_unit(text)["source_unit_id"]
    }
    reconciliation = report["pipeline_accounting"]["bidirectional_reconciliation"]
    assert reconciliation["status"] == "PASS", reconciliation
    assert reconciliation["accepted_not_represented"] == []
    assert reconciliation["claims_without_admitted_record"] == []


def test_reader_abstention_is_not_reported_as_source_unit_authorization_failure():
    run, calls = _run(
        "EGFR L858R showed sensitivity to erlotinib in lung cancer.",
        "SAME", case_id="semantic-reader-abstention", reader_abstains=True,
    )
    stage = next(s for s in run.stages if s.stage_id == "stage_10_enrichment_validation")
    validation = next(v for v in stage.output_preview["validations"]
                      if v["relation_family"] == "EVIDENCE_DRUG")
    trace = validation["document_verification"]
    assert calls == []
    assert trace["verification_status"] == "NOT_RUN"
    assert trace["structural_reason_codes"] == ["READER_ABSTAINED"]


def test_reader_transport_failure_is_not_reported_as_source_unit_authorization_failure():
    run, calls = _run(
        "EGFR L858R showed sensitivity to erlotinib in lung cancer.",
        "SAME", case_id="semantic-reader-transport-failure", reader_transport_failure=True,
    )
    stage = next(s for s in run.stages if s.stage_id == "stage_10_enrichment_validation")
    validation = next(v for v in stage.output_preview["validations"]
                      if v["relation_family"] == "EVIDENCE_DRUG")
    trace = validation["document_verification"]
    assert calls == []
    assert trace["verification_status"] == "NOT_RUN"
    assert trace["structural_reason_codes"] == ["READER_OUTPUT_UNAVAILABLE"]
    assert trace["reader_validation_outcome"] == "REJECTED_TRANSPORT"


def test_run_case_routes_partial_evidence_through_narrative_limit_check_and_api_markdown():
    import os
    from backend.api import research_routes
    from backend.research_pipeline.run_store import RunHandle, RunStore

    quote = "EGFR L858R showed sensitivity to erlotinib in a preclinical model of lung cancer."
    limitation = "in a preclinical model"
    run, _ = _run(
        quote, "SAME", case_id="canonical-dossier-partial-narrative",
        semantic_fields={"population_scope": "NARROWER", "population_span": limitation},
        narrative_text=f"Il supporto documentale è parziale e limitato a {limitation}.",
    )
    paper = run.relation_aware_report["paper_evidence"][0]
    assert paper["support_level"] == "PARTIAL_SUPPORT"
    assert paper["accepted_evidence_records"][0]["source_unit_id"] == "SU-1"
    accounting = run.relation_aware_report["pipeline_accounting"]
    assert accounting["bidirectional_reconciliation"]["status"] == "PASS"
    stage = next(stage for stage in run.stages if stage.stage_id == "stage_15_narrative_verifier")
    assert stage.status == "SUCCEEDED"
    assert stage.output_preview["verification"]["status"] == "PASS"

    route_ledger = Path(__file__).with_name(f".gca4-route-test-{uuid4().hex}.sqlite3")
    with patch("backend.research_pipeline.run_store.research_ledger_path", return_value=route_ledger):
        store = RunStore(max_workers=1, queue_capacity=0)
    store._runs[run.run_id] = RunHandle(
        run_id=run.run_id, case_id=run.case_id, status=run.status,
        started_at=run.started_at, run=run,
    )
    try:
        with patch.object(research_routes, "get_store", return_value=store), \
             patch.dict(os.environ, {"VERIFIABLE_PIPELINE_RESEARCH_ENABLED": "1"}):
            response = research_routes.get_dossier(run.run_id)
    finally:
        store.shutdown()
        for suffix in ("", "-wal", "-shm"):
            Path(f"{route_ledger}{suffix}").unlink(missing_ok=True)
    assert response["dossier"] == run.relation_aware_report
    assert response["narrative"] is not None
    assert response["narrative_verification"]["status"] == "PASS"
    assert "PARTIAL_SUPPORT" in response["dossier_markdown"]
    assert limitation in response["dossier_markdown"]
    assert "12345678" in response["dossier_markdown"]
    assert "SU-1" in response["dossier_markdown"]


def test_run_case_narrative_omission_keeps_structured_dossier_and_hides_prose():
    limitation = "in a preclinical model"
    run, _ = _run(
        "EGFR L858R showed sensitivity to erlotinib in a preclinical model of lung cancer.",
        "SAME", case_id="canonical-dossier-omitted-limit",
        semantic_fields={"population_scope": "NARROWER", "population_span": limitation},
        narrative_text="Il supporto documentale è parziale.",
    )
    stage = next(stage for stage in run.stages if stage.stage_id == "stage_15_narrative_verifier")
    assert stage.status == "WARNING"
    assert stage.output_preview["verification"]["status"] == "FAIL"
    assert "NARRATIVE_CRITICAL_LIMITATION_OMITTED" in stage.output_preview["verification"]["reason_codes"]
    assert stage.output_preview["verified_narrative"] is None
    assert run.relation_aware_report["paper_evidence"][0]["support_level"] == "PARTIAL_SUPPORT"
    from backend.api import research_routes

    with patch.object(research_routes, "_snapshot_or_404", return_value=run.to_dict()):
        response = research_routes.get_dossier(run.run_id)
    assert response["dossier"] == run.relation_aware_report
    assert response["narrative"] is None
    assert response["presentation_mode"] == "STRUCTURED_DOSSIER_FALLBACK"
    assert "PARTIAL_SUPPORT" in response["dossier_markdown"]


@pytest.mark.parametrize("narrative_text,expected_reason,expected_omission", [
    ("Il supporto documentale è completo per questa relazione, limitato a in a preclinical model.",
     "NARRATIVE_SUPPORT_LEVEL_ESCALATION", None),
    ("Il beneficio clinico nei pazienti è dimostrato; il limite riportato è in a preclinical model.",
     "NARRATIVE_CRITICAL_LIMITATION_OMITTED", "PRECLINICAL_SCOPE_CLINICAL_BENEFIT_ESCALATION"),
])
def test_run_case_rejects_partial_support_promoted_to_full_or_clinical_benefit(
    narrative_text, expected_reason, expected_omission,
):
    run, _ = _run(
        "EGFR L858R showed sensitivity to erlotinib in a preclinical model of lung cancer.",
        "SAME", case_id=f"canonical-dossier-promotion-{len(narrative_text)}",
        semantic_fields={"population_scope": "NARROWER", "population_span": "in a preclinical model"},
        narrative_text=narrative_text,
    )
    stage = next(stage for stage in run.stages if stage.stage_id == "stage_15_narrative_verifier")
    assert stage.status == "WARNING"
    assert stage.output_preview["verification"]["status"] == "FAIL"
    result = stage.output_preview["verification"]
    assert expected_reason in result["reason_codes"]
    if expected_omission:
        assert any(item["omitted"] == expected_omission for item in result["critical_omissions"])
    assert stage.output_preview["verified_narrative"] is None


def test_run_case_allows_explicitly_negated_clinical_benefit_for_preclinical_evidence():
    run, _ = _run(
        "EGFR L858R showed sensitivity to erlotinib in a preclinical model of lung cancer.",
        "SAME", case_id="canonical-dossier-preclinical-benefit-denied",
        semantic_fields={"population_scope": "NARROWER", "population_span": "in a preclinical model"},
        narrative_text=("Il beneficio clinico nei pazienti non è dimostrato; i risultati riguardano "
                        "in a preclinical model."),
    )
    stage = next(stage for stage in run.stages if stage.stage_id == "stage_15_narrative_verifier")
    assert stage.status == "SUCCEEDED"
    assert stage.output_preview["verification"]["status"] == "PASS"


def test_run_case_allows_english_explicitly_negated_clinical_benefit():
    run, _ = _run(
        "EGFR L858R showed sensitivity to erlotinib in a preclinical model of lung cancer.",
        "SAME", case_id="canonical-dossier-preclinical-benefit-denied-english",
        semantic_fields={"population_scope": "NARROWER", "population_span": "in a preclinical model"},
        narrative_text="No clinical benefit was shown in patients; results concern in a preclinical model.",
    )
    stage = next(stage for stage in run.stages if stage.stage_id == "stage_15_narrative_verifier")
    assert stage.status == "SUCCEEDED"
    assert stage.output_preview["verification"]["status"] == "PASS"


def test_run_case_does_not_let_unrelated_negation_hide_positive_clinical_benefit():
    run, _ = _run(
        "EGFR L858R showed sensitivity to erlotinib in a preclinical model of lung cancer.",
        "SAME", case_id="canonical-dossier-negation-cannot-cross-contrast",
        semantic_fields={"population_scope": "NARROWER", "population_span": "in a preclinical model"},
        narrative_text=("No response was observed, but clinical benefit was demonstrated in patients; "
                        "results concern in a preclinical model."),
    )
    stage = next(stage for stage in run.stages if stage.stage_id == "stage_15_narrative_verifier")
    assert stage.status == "WARNING"
    result = stage.output_preview["verification"]
    assert result["status"] == "FAIL"
    assert any(item["omitted"] == "PRECLINICAL_SCOPE_CLINICAL_BENEFIT_ESCALATION"
               for item in result["critical_omissions"])


def test_run_case_rejects_narrative_that_suppresses_contradiction():
    run, _ = _run(
        "EGFR L858R did not show sensitivity to erlotinib in lung cancer.", "OPPOSITE",
        case_id="canonical-dossier-contradiction-omitted",
        narrative_text="La relazione è descritta nel dossier per il contesto clinico indicato.",
    )
    paper = run.relation_aware_report["paper_evidence"][0]
    stage = next(stage for stage in run.stages if stage.stage_id == "stage_15_narrative_verifier")
    assert paper["support_level"] == "CONTRADICTORY"
    assert paper["contradiction_present"] is True
    assert "CONTRADICTORY" in paper["claim"]["contradicting_evidence_ids"] or paper["claim"]["contradicting_evidence_ids"]
    assert stage.output_preview["verification"]["status"] == "FAIL"
    result = stage.output_preview["verification"]
    assert "NARRATIVE_CRITICAL_LIMITATION_OMITTED" in result["reason_codes"]
    assert any(item["omitted"] == "CONTRADICTION_NOT_STATED" for item in result["critical_omissions"])


def test_run_case_rejects_unauthorized_narrative_quote_and_source_reference():
    run, _ = _run(
        "EGFR L858R showed sensitivity to erlotinib in lung cancer.", "SAME",
        case_id="canonical-dossier-unauthorized-citation",
        narrative_text=('La fonte afferma "This invented statement is taken from the scientific paper '
                        'and reports clear clinical benefit".'),
        narrative_entry_fields={"source_refs": ["PMID:99999999", "SU-FOREIGN"]},
    )
    stage = next(stage for stage in run.stages if stage.stage_id == "stage_15_narrative_verifier")
    result = stage.output_preview["verification"]
    assert result["status"] == "FAIL"
    assert "NARRATIVE_UNAUTHORIZED_QUOTE" in result["reason_codes"]
    assert "NARRATIVE_UNAUTHORIZED_SOURCE_REF" in result["reason_codes"]
    assert stage.output_preview["verified_narrative"] is None


@pytest.mark.parametrize(("semantic_status", "expected_support", "expected_verification"), [
    ("SAME", "FULL_SUPPORT", "FULL_SUPPORT"),
    ("OPPOSITE", "CONTRADICTORY", "CONTRADICTORY"),
    ("NO_SUPPORT", "NO_SUPPORT", "NO_SUPPORT"),
    ("INSUFFICIENT", "INSUFFICIENT_INFORMATION", "INSUFFICIENT_INFORMATION"),
    ("AMBIGUOUS", "UNVERIFIABLE", "UNVERIFIABLE"),
    (None, "UNVERIFIABLE", "TECHNICAL_ERROR"),
])
def test_run_case_keeps_scientific_and_execution_statuses_distinct(
    semantic_status, expected_support, expected_verification,
):
    run, _ = _run("EGFR L858R showed sensitivity to erlotinib in lung cancer.",
                  semantic_status, case_id=f"canonical-state-{semantic_status}")
    paper = run.relation_aware_report["paper_evidence"][0]
    record = paper["accepted_evidence_records"][0]
    assert paper["support_level"] == expected_support
    assert record["candidate_support"]["result"] == expected_support
    assert record["document_verification"]["verification_status"] == (
        "TECHNICAL_ERROR" if semantic_status is None else "ASSESSED")
    accounting = run.relation_aware_report["pipeline_accounting"]
    accounted = next(item for item in accounting["reader_attempts"]["records"]
                     if item["evidence_id"] == record["evidence_id"])
    assert accounted["disposition"] == "ADMITTED_TO_DOSSIER"
    assert accounted["verification_disposition"] == expected_verification
    if expected_support == "INSUFFICIENT_INFORMATION":
        assert record["evidence_id"] in paper["claim"]["insufficient_information_evidence_ids"]
        assert record["evidence_id"] not in paper["claim"]["no_support_evidence_ids"]


def test_run_case_rejected_reader_record_is_not_rendered_as_support():
    from backend.api import research_routes

    run, _ = _run("EGFR L858R showed sensitivity to erlotinib in lung cancer.", "SAME",
                  case_id="canonical-unadmitted-reader-output", reader_transport_failure=True)
    paper = run.relation_aware_report["paper_evidence"][0]
    assert paper["accepted_evidence_records"] == []
    assert paper["rejected_evidence"]
    with patch.object(research_routes, "_snapshot_or_404", return_value=run.to_dict()):
        response = research_routes.get_dossier(run.run_id)
    assert "EXCLUDED_RECORD" in response["dossier_markdown"]
    assert response["dossier"]["paper_evidence"][0]["documentary_findings"][0]["disposition"] == "EXCLUDED_RECORD"
    assert "EGFR L858R showed sensitivity" not in response["dossier_markdown"]
    assert "##### FULL_SUPPORT" not in response["dossier_markdown"]


@pytest.mark.parametrize("text,scope", [
    ("Previous studies reported that EGFR L858R showed sensitivity to erlotinib in lung cancer.",
     "REPORTED_PRIOR_WORK"),
    ("A prior report stated that EGFR L858R showed sensitivity to erlotinib in lung cancer.",
     "REPORTED_PRIOR_WORK"),
    ("The claim that EGFR L858R showed sensitivity to erlotinib in lung cancer was rejected.",
     "REJECTED_ASSERTION"),
    ("It was hypothesized that EGFR L858R showed sensitivity to erlotinib in lung cancer.",
     "HYPOTHETICAL"),
    ("EGFR L858R may show sensitivity to erlotinib in lung cancer.", "UNCERTAIN_ASSERTION"),
    ("Does EGFR L858R show sensitivity to erlotinib in lung cancer?", "QUESTIONED_ASSERTION"),
])
def test_non_direct_assertion_scope_never_supports_even_when_relation_is_same(text, scope):
    run, _ = _run(text, "SAME", case_id=f"scope-{scope}-{len(text)}",
                  assertion_scope=scope)
    assert run.relation_aware_report["paper_evidence"][0]["claim"]["status"] == "UNVERIFIABLE"


@pytest.mark.parametrize("text", [
    "EGFR L858R showed sensitivity to erlotinib in lung cancer (Smith et al., 2020).",
    "Earlier studies debated response; our results show that EGFR L858R was sensitive to erlotinib in lung cancer.",
])
def test_direct_assertion_survives_non_governing_prior_citation(text):
    run, _ = _run(text, "SAME", case_id=f"direct-citation-{len(text)}",
                  assertion_scope="DIRECT_ASSERTION")
    assert run.relation_aware_report["paper_evidence"][0]["claim"]["status"] == "FULL_SUPPORT"


def test_reported_negative_from_another_source_cannot_be_admitted_as_direct_support():
    text = "Previous studies reported that EGFR L858R did not show sensitivity to erlotinib in lung cancer."
    run, _ = _run(text, "SAME", case_id="reported-negative",
                  assertion_scope="REPORTED_PRIOR_WORK")
    assert run.relation_aware_report["paper_evidence"][0]["claim"]["status"] == "UNVERIFIABLE"


def test_structural_mismatch_is_not_scientific_no_support():
    structural = {**_structural("EGFR L858R showed sensitivity to erlotinib in lung cancer."),
                  "structural_status": "MISMATCH",
                  "structural_reason_codes": ["DRUG_IDENTITY_MISMATCH"]}
    result = admit(structural, None)
    assert result["final_admission"] == "NOT_RUN_STRUCTURAL"
    assert result["support_result"] == "UNVERIFIABLE"
    assert result["verification_status"] == "STRUCTURAL_INCOMPATIBILITY"


@pytest.mark.parametrize("phrase", ["treated with trametinib", "targeted therapy with trametinib"])
def test_ordinary_therapy_with_drug_is_not_misread_as_combination(phrase):
    text = f"NRAS Q61K showed response during {phrase} in lung cancer."
    candidate = _candidate(biomarkers=[
        {"label": "NRAS", "type": "Gene"},
        {"label": "Q61K", "type": "Variant", "gene": "NRAS"},
    ], interventions=[{"label": "trametinib", "type": "Drug"}])
    unit = _source_unit(text)
    observed = {"source_unit_id": unit["source_unit_id"], "quote": text,
                "observed_relation": {"subjects": [
                    {"type": "GENE", "surface_value": "NRAS"},
                    {"type": "ALTERATION", "surface_value": "Q61K", "linked_gene": "NRAS"}],
                    "intervention": "trametinib", "disease": "lung cancer", "relation_scope": "SINGLE"}}
    result = structural_verify(candidate, {"document_id": unit["document_id"],
                                           "resolved_source_unit_ids": [unit["source_unit_id"]]},
                               unit, observed)
    assert result["structural_status"] == "PASS", result


def test_gene_variant_pair_can_be_linked_by_mutation_of_phrase():
    text = "C481S mutation of BTK was associated with reduced ibrutinib sensitivity in lung cancer."
    candidate = _candidate(biomarkers=[
        {"label": "BTK", "type": "Gene"},
        {"label": "C481S", "type": "Variant", "gene": "BTK"},
    ], interventions=[{"label": "ibrutinib", "type": "Drug"}])
    unit = _source_unit(text)
    observed = {"source_unit_id": unit["source_unit_id"], "quote": text,
                "observed_relation": {"subjects": [
                    {"type": "ALTERATION", "surface_value": "C481S", "linked_gene": "BTK"},
                    {"type": "GENE", "surface_value": "BTK"}],
                    "intervention": "ibrutinib", "disease": "lung cancer", "relation_scope": "SINGLE"}}
    result = structural_verify(candidate, {"document_id": unit["document_id"],
                                           "resolved_source_unit_ids": [unit["source_unit_id"]]},
                               unit, observed)
    assert result["structural_status"] == "PASS", result


def test_combination_with_a_drug_class_is_not_promoted_to_single_agent():
    text = ("FLT3 ITD was associated with poor survival during treatment with erlotinib "
            "and anthracycline-based chemotherapy in lung cancer.")
    candidate = _candidate(biomarkers=[
        {"label": "FLT3", "type": "Gene"},
        {"label": "ITD", "type": "Variant", "gene": "FLT3"},
    ])
    unit = _source_unit(text)
    observed = {"source_unit_id": unit["source_unit_id"], "quote": text,
                "observed_relation": {"subjects": [
                    {"type": "GENE", "surface_value": "FLT3"},
                    {"type": "ALTERATION", "surface_value": "ITD", "linked_gene": "FLT3"}],
                    "intervention": "erlotinib", "disease": "lung cancer", "relation_scope": "SINGLE"}}
    result = structural_verify(candidate, {"document_id": unit["document_id"],
                                           "resolved_source_unit_ids": [unit["source_unit_id"]]},
                               unit, observed)
    assert result["structural_status"] == "UNRESOLVED", result
    assert "POSSIBLE_MULTI_AGENT_INTERVENTION" in result["structural_reason_codes"]


def test_partial_support_requires_narrower_context_and_is_not_full():
    text = "In a subgroup of patients with EGFR L858R lung cancer, response to erlotinib was observed."
    output = assessment(text, population_scope="NARROWER", population_span="a subgroup of patients")
    result = admit(_structural(text), output)
    assert result["final_admission"] == "PARTIALLY_SUPPORTED"
    assert result["support_result"] == "PARTIAL_SUPPORT"
    assert result["verification_status"] == "ASSESSED"
    assert result["final_admission"] != "DOCUMENT_SUPPORTED"


def test_preclinical_support_keeps_relation_and_clinical_applicability_separate():
    text = "In cell lines, EGFR L858R showed sensitivity to erlotinib in lung cancer."
    structural = _structural(text, case_context={"disease": "lung cancer",
                                                "biomarkers": [{"gene": "EGFR", "alteration": "L858R"}]})
    result = admit(structural, assessment(text))
    assert result["support_result"] == "FULL_SUPPORT"
    assert result["study_context"] == "PRECLINICAL_CELL"
    assert result["applicability_to_case"] == "LIMITED_PRECLINICAL"


def test_preclinical_study_context_does_not_claim_case_applicability_without_case():
    text = "In cell lines, EGFR L858R showed sensitivity to erlotinib in lung cancer."
    result = admit(_structural(text), assessment(text))
    assert result["study_context"] == "PRECLINICAL_CELL"
    assert result["applicability_to_case"] == "NOT_ASSESSED"


def test_dossier_keeps_partial_and_technical_statuses_separate_from_full():
    from backend.research_pipeline.dossier.builder import aggregate_evidence_records

    text = "In a subgroup of patients with EGFR L858R lung cancer, response to erlotinib was observed."
    partial_verification = admit(
        _structural(text),
        assessment(text, population_scope="NARROWER", population_span="a subgroup of patients"),
    )
    record = {"relation_family": "EVIDENCE_DRUG", "validation_outcome": "ENRICHMENT_V3_ACCEPTED",
              "quote_valid": True, "source_unit_id": "SU-1", "document_id": "pmid:12345678",
              "candidate_support": {"result": "PARTIAL_SUPPORT"},
              "document_verification": partial_verification}
    aggregation = aggregate_evidence_records([record])
    assert aggregation["support_level"] == "PARTIAL_SUPPORT"
    assert aggregation["partial_evidence_ids"] and not aggregation["full_evidence_ids"]
    limitation = aggregation["evidence_records"][0]["document_verification"]["support_limitation"]
    assert limitation["population_scope"]["literal_span"] == "a subgroup of patients"


@pytest.mark.parametrize("scope,expected", [
    ("COMBINATION", "UNVERIFIABLE"),
    ("DIFFERENT", "UNVERIFIABLE"),
])
def test_partial_never_erases_intervention_or_molecular_mismatch(scope, expected):
    text = "EGFR L858R showed sensitivity to erlotinib plus cetuximab in lung cancer."
    output = assessment(text, population_scope="NARROWER", population_span="lung cancer",
                        intervention_scope=scope)
    result = admit(_structural("EGFR L858R showed sensitivity to erlotinib in lung cancer."), output)
    assert result["final_admission"] == expected


def test_technical_failure_is_separate_from_insufficient_source_information():
    structural = _structural("EGFR L858R showed sensitivity to erlotinib in lung cancer.")
    technical = {"relation_alignment": "AMBIGUOUS", "assertion_scope": "UNKNOWN",
                 "reason": "SEMANTIC_PROVIDER_FAILURE:TimeoutError", "decisive_text": ""}
    technical_result = admit(structural, technical)
    insufficient = assessment(structural["GEP_snapshot"]["required_context"],
                              relation_alignment="INSUFFICIENT")
    insufficient_result = admit(structural, insufficient)
    assert technical_result["verification_status"] == "TECHNICAL_ERROR"
    assert insufficient_result["support_result"] == "INSUFFICIENT_INFORMATION"


def test_structural_ambiguity_is_not_misreported_as_insufficient_scientific_evidence():
    result = admit({"structural_status": "UNRESOLVED",
                    "structural_reason_codes": ["POSSIBLE_MULTI_AGENT_INTERVENTION"],
                    "GEP_snapshot": {}}, None)
    assert result["support_result"] == "UNVERIFIABLE"
    assert result["verification_status"] == "STRUCTURAL_AMBIGUITY"
    assert result["final_admission"] == "NOT_RUN_STRUCTURAL"
