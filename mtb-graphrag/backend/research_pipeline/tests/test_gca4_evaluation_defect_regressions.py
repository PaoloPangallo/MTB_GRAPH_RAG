"""Regression cases distilled from the saved 2026-10-10 GCA4 outputs."""

import json
import gzip
import csv
from pathlib import Path

import pytest

from backend.research_pipeline.enrichment import transport
from backend.research_pipeline.enrichment.canonical_normalizer import entity_relation
from backend.research_pipeline.enrichment.document_verification import admit
from backend.research_pipeline.casecontext import parser as case_parser
from backend.research_pipeline.enrichment.document_verification import structural_verify
from backend.research_pipeline.tests.test_document_verification import _candidate, _source_unit


def _saved_quote(case_id: str, intervention: str) -> str:
    repo = Path(__file__).resolve().parents[4]
    with (repo / "experiments_real/results/gca4_paper_coverage_20261010/evidence_attempts.csv").open(
            encoding="utf-8-sig", newline="") as stream:
        return next(row["quote"] for row in csv.DictReader(stream)
                    if row["case_id"] == case_id and row["quote"]
                    and intervention.casefold() in row["quote"].casefold())


def test_saved_parser_text_json_response_is_recovered_as_one_valid_tool_call():
    # This is the exact saved HTTP response body, including the provider's
    # fenced JSON content and schema shape, not a reconstructed model output.
    repo = Path(__file__).resolve().parents[4]
    saved = json.load(gzip.open(repo / "experiments_real/results/gca4_paper_coverage_20261010/raw/gca4/GCA4-PUB-0004.json.gz", "rt", encoding="utf-8"))
    stage = next(s for s in saved["stages"] if s["stage_id"] == "stage_2_casecontext_parser")
    response = stage["output_preview"]["parser_diagnostics"]["raw_response_body"]
    arguments = json.loads(response["choices"][0]["message"]["content"].strip()[7:-3])[
        "submit_case_context"]

    outcome, _, recovered, reasons = transport.transport_result(
        200, response, None, "submit_case_context", lambda _: [])

    assert outcome == "FORCED_TOOL_VALID"
    assert recovered == arguments
    assert "TEXT_JSON_RECOVERED" in reasons


def test_parser_does_not_make_a_second_request_when_provider_returns_fenced_json(monkeypatch):
    arguments = {"disease": None, "biomarkers": [], "previous_interventions": [],
                 "target_intervention": None, "query_intent": "THERAPY_DISCOVERY",
                 "clinical_question": "Identify relevant evidence."}
    response = {"choices": [{"finish_reason": "stop", "message": {
        "content": "```json\n" + json.dumps({"submit_case_context": arguments}) + "\n```"}}]}
    calls = []

    def provider(_payload):
        calls.append(1)
        return 200, response, None, 0, {"http_status": 200, "raw_response_body": response}

    monkeypatch.setattr(case_parser.tr, "post_with_infra_retry_with_diagnostics", provider)
    result = case_parser.call_parser("SAVED-CASE", "A patient with a tumor.")

    assert len(calls) == 1
    assert result["transport_result"] == "FORCED_TOOL_VALID"
    assert result["parser_attempts"][0]["reason_codes"] == ["TEXT_JSON_RECOVERED"]


def test_semantic_schema_error_is_not_reported_when_structural_gate_already_failed():
    repo = Path(__file__).resolve().parents[4]
    saved = json.load(gzip.open(repo / "experiments_real/results/gca4_paper_coverage_20261010/raw/gca4/GCA4-PUB-0006.json.gz", "rt", encoding="utf-8"))
    stage = next(s for s in saved["stages"] if s["stage_id"] == "stage_10_enrichment_validation")
    record = next(v for v in stage["output_preview"]["validations"]
                  if v["candidate_support"]["verification_trace"]["final_admission"] == "REJECTED")
    mismatch = record["candidate_support"]["verification_trace"]
    # The saved trace contains no semantic assessment: the structural gate
    # rejected the single-drug target before semantic verification was called.
    assert mismatch["semantic_assessment"] is None
    assert mismatch["admission_reason_codes"] == ["SEMANTIC_OUTPUT_SCHEMA_INVALID"]

    result = admit(mismatch, None)

    assert result["final_admission"] == "NOT_RUN_STRUCTURAL"
    assert result["support_result"] == "UNVERIFIABLE"
    assert result["verification_status"] == "STRUCTURAL_INCOMPATIBILITY"
    assert result["admission_reason_codes"] == ["DRUG_IDENTITY_MISMATCH"]
    assert "SEMANTIC_OUTPUT_SCHEMA_INVALID" not in result["admission_reason_codes"]


def test_saved_trametinib_case_treats_therapy_with_drug_as_single_intervention():
    quote = _saved_quote("GCA4-PUB-0127", "trametinib")
    candidate = _candidate(
        biomarkers=[{"label": "NRAS", "type": "Gene"}],
        disease=[{"label": "low grade serous ovarian cancer", "type": "Disease"}],
        interventions=[{"label": "trametinib", "type": "Drug"}],
    )
    unit = _source_unit(quote)
    observed = {"source_unit_id": unit["source_unit_id"], "quote": quote,
                "observed_relation": {"subjects": [{"type": "GENE", "surface_value": "NRAS"}],
                    "intervention": "trametinib", "disease": "low grade serous ovarian cancer",
                    "relation_scope": "SINGLE"}}
    result = structural_verify(candidate, {"document_id": unit["document_id"],
                                  "resolved_source_unit_ids": [unit["source_unit_id"]]}, unit, observed)
    assert result["structural_status"] == "PASS", result


def test_saved_btk_c481s_case_recognizes_variant_mutation_of_gene_link():
    quote = _saved_quote("GCA4-PUB-0278", "ibrutinib")
    candidate = _candidate(
        biomarkers=[{"label": "BTK", "type": "Gene"},
                    {"label": "C481S", "type": "Variant", "gene": "BTK"}],
        disease=[], interventions=[{"label": "ibrutinib", "type": "Drug"}],
    )
    unit = _source_unit(quote)
    observed = {"source_unit_id": unit["source_unit_id"], "quote": quote,
                "observed_relation": {"subjects": [
                    {"type": "ALTERATION", "surface_value": "C481S", "linked_gene": "BTK"},
                    {"type": "GENE", "surface_value": "BTK"}],
                    "intervention": "ibrutinib", "disease": None, "relation_scope": "SINGLE"}}
    result = structural_verify(candidate, {"document_id": unit["document_id"],
                                  "resolved_source_unit_ids": [unit["source_unit_id"]]}, unit, observed)
    assert result["structural_status"] == "PASS", result


@pytest.mark.parametrize("expected, observed", [
    ("TRETINOIN", "all-trans retinoic acid"),
    ("SIROLIMUS", "rapamycin"),
    ("PALBOCICLIB", "PD-0332991"),
    ("DORDAVIPRONE", "ONC201"),
    ("PICTILISIB", "GDC-0941"),
    ("PICTILISIB", "GDC-0941/Pictilisib"),
    ("FEXAGRATINIB", "AZD-4547"),
    ("IRINOTECAN HYDROCHLORIDE", "irinotecan"),
    ("JAK2 INHIBITOR AZD1480", "AZD1480"),
])
def test_verified_drug_synonyms_compare_as_identity(expected, observed):
    assert entity_relation(expected, observed, domain="INTERVENTION") == "CANONICAL_ALIAS"


def test_clinically_distinct_drugs_are_not_promoted_to_synonyms():
    assert entity_relation("TRETINOIN", "isotretinoin", domain="INTERVENTION") != "CANONICAL_ALIAS"
    assert entity_relation("CISPLATIN", "carboplatin", domain="INTERVENTION") != "CANONICAL_ALIAS"


def test_gene_and_variant_synonyms_use_the_linked_gene():
    assert entity_relation("ERBB2", "HER2", domain="GENE") == "CANONICAL_ALIAS"
    assert entity_relation("ERBB2", "HER-2", domain="GENE") == "CANONICAL_ALIAS"
    assert entity_relation(
        "ERBB2", "human epidermal growth factor receptor 2", domain="GENE"
    ) == "CANONICAL_ALIAS"
    assert entity_relation(
        "ERBB2", "amplification of human epidermal growth factor receptor 2", domain="GENE"
    ) != "CANONICAL_ALIAS"
    assert entity_relation("G12D", "p.Gly12Asp", domain="VARIANT",
                           gene_id="NCBIGene:3845") == "CANONICAL_ALIAS"


def test_combination_text_is_not_equal_to_a_single_drug_synonym():
    assert entity_relation("TRETINOIN", "all-trans retinoic acid and anthracycline-based chemotherapy",
                           domain="INTERVENTION") != "CANONICAL_ALIAS"


def test_large_excluded_candidate_list_has_compact_reconstructable_audit():
    from backend.research_pipeline.redaction import compact_excluded_candidates

    excluded = [{"candidate_id": f"candidate-{index:05d}",
                 "reason_codes": ["DISEASE_NOT_COMPATIBLE"],
                 "candidate": {"large_source_text": "x" * 1000}}
                for index in range(1000)]

    audit = compact_excluded_candidates(excluded)

    assert audit["count"] == 1000
    assert audit["reason_counts"] == {"DISEASE_NOT_COMPATIBLE": 1000}
    assert len(audit["sample_candidate_ids"]) <= 10
    assert len(audit["sha256"]) == 64
    assert "large_source_text" not in json.dumps(audit)
