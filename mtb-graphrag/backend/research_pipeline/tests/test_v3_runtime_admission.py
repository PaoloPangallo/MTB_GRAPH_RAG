"""Loader v3, ammissione runtime, matching composto e policy sui regimi."""

from __future__ import annotations

import json

import pytest

from backend.research_pipeline.retrieval import admission as adm
from backend.research_pipeline.retrieval import repository_v3 as repo


# ============================================================ loader v3

def test_default_repository_is_still_v2(monkeypatch):
    monkeypatch.delenv("GRAPH_CANDIDATE_REPOSITORY_VERSION", raising=False)
    assert repo.configured_version() == "2.0"
    assert repo.describe()["runtime_default_changed_to_v3"] is False


def test_unsupported_version_raises_and_does_not_fall_back(monkeypatch):
    monkeypatch.setenv("GRAPH_CANDIDATE_REPOSITORY_VERSION", "9.9")
    with pytest.raises(repo.RepositoryVersionUnsupported):
        repo.configured_version()


def test_no_v3_to_v2_fallback_exists():
    assert repo.describe()["fallback_enabled"] is False


def test_manifest_is_validated():
    manifest = repo.validate_manifest("3.0", verify_repository_hash=False)
    assert manifest["contract_version"] == repo.EXPECTED_CONTRACT_VERSION


def test_repository_hash_is_verified():
    manifest = repo.validate_manifest("3.0")
    assert manifest["repository_hash"]


def _record(**over):
    base = {
        "candidate_id": "GCA3-x", "contract_version": repo.EXPECTED_CONTRACT_VERSION,
        "source_alignment_status": "SOURCE_ALIGNED",
        "source_support_polarity": "SUPPORTS_ASSERTION",
        "intervention_structure": "SINGLE_AGENT",
        "alteration_parse_status": "ATOMIC",
        "source_path_ids": ["p1"],
        "alteration_expression_ast": {"node_type": "TERM", "gene": "BRAF",
                                      "alteration": "V600E", "raw": "BRAF V600E"},
    }
    base.update(over)
    return base


def test_valid_record_passes():
    repo.validate_record(_record())


@pytest.mark.parametrize("field,value", [
    ("source_alignment_status", "SOMETHING_ELSE"),
    ("source_support_polarity", "MAYBE"),
    ("intervention_structure", "COCKTAIL"),
    ("alteration_parse_status", "GUESSED"),
])
def test_enum_violations_are_rejected(field, value):
    with pytest.raises(repo.RepositoryContractInvalid):
        repo.validate_record(_record(**{field: value}))


def test_missing_lineage_is_rejected():
    with pytest.raises(repo.RepositoryContractInvalid, match="lineage"):
        repo.validate_record(_record(source_path_ids=[]))


def test_wrong_contract_version_is_rejected():
    with pytest.raises(repo.RepositoryContractInvalid):
        repo.validate_record(_record(contract_version="graph-candidate-assertion/2.0"))


def test_does_not_support_marked_aligned_is_rejected():
    with pytest.raises(repo.RepositoryContractInvalid, match="SOURCE_ALIGNED"):
        repo.validate_record(_record(
            source_support_polarity="DOES_NOT_SUPPORT_ASSERTION",
            source_alignment_status="SOURCE_ALIGNED"))


def test_malformed_ast_is_rejected():
    with pytest.raises(repo.RepositoryContractInvalid, match="node_type"):
        repo.validate_record(_record(alteration_expression_ast={"nodes": []}))


# ================================================== ammissione runtime

def _candidate(**over):
    base = {
        "candidate_id": "GCA3-c", "source_alignment_status": "SOURCE_ALIGNED",
        "graph_direction": "SENSITIVITY", "intervention_structure": "SINGLE_AGENT",
        "intervention_components": [{"concept_id": "1", "name": "PANITUMUMAB",
                                     "node_id": "Drug:1", "component_role": "UNKNOWN"}],
        "alteration_parse_status": "ATOMIC",
        "alteration_expression_ast": {"node_type": "TERM", "gene": "KRAS",
                                      "alteration": "G12D", "raw": "KRAS G12D"},
        "disease": [{"label": "Colorectal Cancer"}],
        "biomarkers": [{"label": "KRAS", "type": "Gene"}],
    }
    base.update(over)
    return base


def _fields(**over):
    base = {"disease": "colorectal cancer", "genes": ["KRAS"], "alterations": ["G12D"],
            "target_intervention": "panitumumab", "previous_interventions": []}
    base.update(over)
    return base


def test_source_aligned_enters_positive_branch():
    result = adm.evaluate_candidate(_candidate(), _fields(), "THERAPY_EVALUATION")
    assert result.admission_status == adm.ADMITTED_NORMAL_GROUNDING
    assert result.is_positive


def test_does_not_support_never_enters_positive_branch():
    result = adm.evaluate_candidate(
        _candidate(source_alignment_status="SOURCE_DOES_NOT_SUPPORT",
                   graph_direction="RESISTANCE"),
        _fields(), "THERAPY_EVALUATION")
    assert result.admission_status == adm.ADMITTED_NEGATIVE_AUDIT_BRANCH
    assert result.is_positive is False
    assert result.is_audit_only
    assert result.allowed_branches == [adm.BRANCH_NEGATIVE]
    # La direzione del grafo è preservata, non invertita.
    assert result.direction_status == "RESISTANCE"


def test_neutral_never_enters_positive_branch():
    result = adm.evaluate_candidate(
        _candidate(source_alignment_status="SOURCE_NEUTRAL"), _fields(), "THERAPY_EVALUATION")
    assert result.admission_status == adm.ADMITTED_NEUTRAL_AUDIT_BRANCH
    assert result.is_positive is False
    assert result.allowed_branches == [adm.BRANCH_NEUTRAL]


def test_contradicts_never_enters_positive_branch():
    result = adm.evaluate_candidate(
        _candidate(source_alignment_status="SOURCE_CONTRADICTS"), _fields(), "THERAPY_EVALUATION")
    assert result.is_positive is False


def test_polarity_unavailable_is_admitted_with_warning_not_as_aligned():
    result = adm.evaluate_candidate(
        _candidate(source_alignment_status="SOURCE_ALIGNMENT_NOT_AVAILABLE"),
        _fields(), "THERAPY_EVALUATION")
    assert result.admission_status == adm.ADMITTED_GROUNDING_WITH_SOURCE_POLARITY_UNKNOWN
    assert result.is_positive
    assert "SOURCE_POLARITY_UNAVAILABLE" in result.warning_codes
    assert result.source_alignment_status != "SOURCE_ALIGNED"
    assert "DOCUMENT_GROUNDING_STILL_REQUIRED" in result.reason_codes


# =============================================== alterazioni composte

_AND_AST = {
    "node_type": "AND",
    "operands": [
        {"node_type": "TERM", "gene": "EGFR", "alteration": "T790M", "raw": "EGFR T790M"},
        {"node_type": "TERM", "gene": "EGFR", "alteration": "C797S", "raw": "EGFR C797S"},
    ],
}
_OR_AST = {
    "node_type": "OR",
    "operands": [
        {"node_type": "TERM", "gene": "BRCA1", "alteration": "Mutation", "raw": "BRCA1 Mutation"},
        {"node_type": "TERM", "gene": "BRCA2", "alteration": "Mutation", "raw": "BRCA2 Mutation"},
    ],
}


def test_compound_and_full_match():
    candidate = _candidate(alteration_expression_ast=_AND_AST,
                           alteration_parse_status="PARSED_EXACT",
                           biomarkers=[{"label": "EGFR", "type": "Gene"}])
    fields = _fields(genes=["EGFR", "EGFR"], alterations=["T790M", "C797S"])
    result = adm.evaluate_candidate(candidate, fields, "THERAPY_EVALUATION")
    assert result.alteration_match_status == "FULL_MATCH"
    assert result.is_positive


def test_compound_and_partial_is_never_promoted_to_full():
    candidate = _candidate(alteration_expression_ast=_AND_AST,
                           alteration_parse_status="PARSED_EXACT")
    fields = _fields(genes=["EGFR"], alterations=["T790M"])
    result = adm.evaluate_candidate(candidate, fields, "THERAPY_EVALUATION")
    assert result.alteration_match_status == "PARTIAL_MATCH"
    assert result.alteration_match_status != "FULL_MATCH"
    assert result.admission_status == adm.REJECTED_ALTERATION_INSUFFICIENT
    assert result.is_positive is False


def test_compound_or_needs_only_one():
    candidate = _candidate(alteration_expression_ast=_OR_AST,
                           alteration_parse_status="PARSED_EXACT",
                           biomarkers=[{"label": "BRCA1", "type": "Gene"}])
    fields = _fields(genes=["BRCA1"], alterations=["Mutation"])
    result = adm.evaluate_candidate(candidate, fields, "THERAPY_EVALUATION")
    assert result.alteration_match_status == "FULL_MATCH"


def test_compound_no_match_excludes_the_candidate():
    candidate = _candidate(alteration_expression_ast=_AND_AST,
                           alteration_parse_status="PARSED_EXACT")
    fields = _fields(genes=["KRAS"], alterations=["G12D"])
    result = adm.evaluate_candidate(candidate, fields, "THERAPY_EVALUATION")
    assert result.alteration_match_status == "NO_MATCH"
    assert result.admission_status == adm.REJECTED_ALTERATION_MISMATCH
    assert result.allowed_branches == []


def test_insufficient_case_information_does_not_promote():
    candidate = _candidate(alteration_expression_ast=_AND_AST,
                           alteration_parse_status="PARSED_EXACT")
    result = adm.evaluate_candidate(candidate, _fields(genes=[], alterations=[]),
                                    "THERAPY_EVALUATION")
    assert result.alteration_match_status == "INSUFFICIENT_CASE_INFORMATION"
    assert result.is_positive is False


def test_unsupported_expression_is_audit_only():
    candidate = _candidate(alteration_parse_status="MALFORMED_EXPRESSION",
                           alteration_expression_ast=None)
    result = adm.evaluate_candidate(candidate, _fields(), "THERAPY_EVALUATION")
    assert result.admission_status == adm.AUDIT_ONLY_UNSUPPORTED_EXPRESSION
    assert result.is_positive is False


# ======================================================= regimi irrisolti

_UNRESOLVED = {
    "intervention_structure": "MULTI_COMPONENT_UNRESOLVED",
    "intervention_components": [
        {"concept_id": "1", "name": "SORAFENIB", "node_id": "Drug:1", "component_role": "UNKNOWN"},
        {"concept_id": "2", "name": "IMATINIB", "node_id": "Drug:2", "component_role": "UNKNOWN"},
        {"concept_id": "3", "name": "NILOTINIB", "node_id": "Drug:3", "component_role": "UNKNOWN"},
    ],
}


def test_unresolved_regimen_rejected_for_exact_match_in_evaluation():
    result = adm.evaluate_candidate(_candidate(**_UNRESOLVED),
                                    _fields(target_intervention="imatinib"),
                                    "THERAPY_EVALUATION")
    assert result.admission_status == adm.REJECTED_UNRESOLVED_REGIMEN_FOR_EXACT_MATCH
    assert result.is_positive is False
    assert "REGIMEN_SEMANTICS_UNAVAILABLE_IN_EXPORT" in result.warning_codes


def test_unresolved_regimen_is_audit_only_in_discovery():
    result = adm.evaluate_candidate(_candidate(**_UNRESOLVED),
                                    _fields(target_intervention=None),
                                    "THERAPY_DISCOVERY")
    assert result.admission_status == adm.AUDIT_ONLY_UNRESOLVED_REGIMEN
    assert result.is_positive is False
    assert result.is_audit_only


def test_no_component_is_individually_promoted():
    """Nemmeno se il caso nomina tutti i componenti."""
    for intent, target in (("THERAPY_EVALUATION", "sorafenib"), ("THERAPY_DISCOVERY", None)):
        result = adm.evaluate_candidate(_candidate(**_UNRESOLVED),
                                        _fields(target_intervention=target), intent)
        assert result.is_positive is False
        assert result.intervention_match_status == "UNRESOLVED_REGIMEN"


def test_mentioning_all_components_does_not_confirm_a_combination():
    result = adm.evaluate_candidate(_candidate(**_UNRESOLVED), _fields(), "THERAPY_EVALUATION")
    assert result.intervention_match_status != "MATCH"
    assert "REGIMEN_SEMANTICS_UNAVAILABLE_IN_EXPORT" in result.warning_codes


# ============================================================= intervento

def test_discovery_does_not_filter_on_intervention():
    status, reasons = adm.evaluate_intervention(_candidate(), None, "THERAPY_DISCOVERY")
    assert status == "NOT_APPLICABLE"
    assert status != "PASS_ALL"


def test_evaluation_requires_a_matching_intervention():
    status, _ = adm.evaluate_intervention(_candidate(), "osimertinib", "THERAPY_EVALUATION")
    assert status == "MISMATCH"


# ================================================================ branch

def test_audit_only_never_appears_in_the_positive_branch():
    admissions = [
        adm.evaluate_candidate(_candidate(source_alignment_status="SOURCE_DOES_NOT_SUPPORT"),
                               _fields(), "THERAPY_EVALUATION"),
        adm.evaluate_candidate(_candidate(source_alignment_status="SOURCE_NEUTRAL"),
                               _fields(), "THERAPY_EVALUATION"),
        adm.evaluate_candidate(_candidate(), _fields(), "THERAPY_EVALUATION"),
    ]
    branches = adm.split_branches(admissions)
    assert len(branches[adm.BRANCH_POSITIVE]) == 1
    assert len(branches[adm.BRANCH_NEGATIVE]) == 1
    assert len(branches[adm.BRANCH_NEUTRAL]) == 1


def test_admission_declares_its_producer_and_version():
    result = adm.evaluate_candidate(_candidate(), _fields(), "THERAPY_EVALUATION")
    assert result.producer == "DETERMINISTIC"
    assert result.policy_version == adm.ADMISSION_POLICY_VERSION


def test_real_v3_repository_has_no_does_not_support_in_positive_branch():
    """Verifica sull'intero repository reale, non su fixture."""
    candidates = repo.load_v3_candidates()
    offenders = []
    for record in candidates.values():
        if record["source_alignment_status"] != "SOURCE_DOES_NOT_SUPPORT":
            continue
        result = adm.evaluate_candidate(record, _fields(), "THERAPY_DISCOVERY")
        if result.is_positive:
            offenders.append(record["candidate_id"])
    assert offenders == []
