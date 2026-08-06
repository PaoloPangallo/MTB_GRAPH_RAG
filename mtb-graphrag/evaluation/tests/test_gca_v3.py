"""Test del contratto GraphCandidateAssertion v3 (§21-§24).

Le fixture sono **reali**: provengono dall'export congelato e dai casi
individuati nell'audit RQ1 (i 486 con inversione di direzione, i 1 294 con
regime spezzato). Nessun test effettua chiamate di rete o LLM.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gca_v3 import CONTRACT_VERSION
from gca_v3.alterations import (
    ATOMIC, MALFORMED_EXPRESSION, MISSING, PARSED_EXACT, ast_from_dict,
    expression_hash, parse_alteration_expression,
)
from gca_v3.contract import GraphCandidateAssertionV3
from gca_v3.matching import (
    EXPRESSION_UNAVAILABLE, EXPRESSION_UNSUPPORTED, FULL_MATCH,
    INSUFFICIENT_CASE_INFORMATION, NO_MATCH, PARTIAL_MATCH,
    evaluate_alteration_expression,
)
from gca_v3.polarity import (
    DOES_NOT_SUPPORT_ASSERTION, NOT_REPORTED, SOURCE_ALIGNED,
    SOURCE_ALIGNMENT_NOT_AVAILABLE, SOURCE_DOES_NOT_SUPPORT, SOURCE_NEUTRAL,
    SUPPORTS_ASSERTION, UNMAPPED_SOURCE_VALUE, describe, graph_direction,
    source_alignment_status, source_support_polarity, source_supported_direction,
)
from gca_v3.regimens import (
    MULTI_COMPONENT_UNRESOLVED, NOT_APPLICABLE, SEMANTICS_UNAVAILABLE_IN_SOURCE,
    SINGLE_AGENT, build_intervention, eligible_for_intervention_exact_match,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
V3 = (REPO_ROOT / "benchmarks" / "mtb_evidence" / "document_grounded_claims"
      / "graph_candidate_repository" / "3.0")
V2 = (REPO_ROOT / "benchmarks" / "mtb_evidence" / "document_grounded_claims"
      / "graph_candidate_repository" / "2.0")


# ============================================================ §21 — POLARITÀ

def test_supports_is_aligned():
    result = describe("Sensitivity/Response", "Supports")
    assert result["graph_direction"] == "SENSITIVITY"
    assert result["source_support_polarity"] == SUPPORTS_ASSERTION
    assert result["source_supported_direction"] == "SENSITIVITY"
    assert result["source_alignment_status"] == SOURCE_ALIGNED


def test_does_not_support_resistance_does_not_become_sensitivity():
    """Il caso reale dei 486: DNMT3A R882 / daunorubicina."""
    result = describe("Resistance", "Does Not Support")
    assert result["graph_direction"] == "RESISTANCE", "la direzione proposta resta quella del grafo"
    assert result["source_support_polarity"] == DOES_NOT_SUPPORT_ASSERTION
    assert result["source_supported_direction"] is None, "nessuna direzione opposta inventata"
    assert result["source_alignment_status"] == SOURCE_DOES_NOT_SUPPORT
    assert result["source_supported_direction"] != "SENSITIVITY"


def test_does_not_support_sensitivity_does_not_become_resistance():
    result = describe("Sensitivity/Response", "Does Not Support")
    assert result["graph_direction"] == "SENSITIVITY"
    assert result["source_supported_direction"] is None
    assert result["source_supported_direction"] != "RESISTANCE"
    assert result["source_alignment_status"] == SOURCE_DOES_NOT_SUPPORT


def test_neutral_significance_is_not_aligned_even_when_supported():
    for significance in ("Uncertain Significance", "Unaltered Function"):
        result = describe(significance, "Supports")
        assert result["source_alignment_status"] == SOURCE_NEUTRAL
        assert result["source_supported_direction"] is None


def test_missing_direction_is_not_assumed_to_support():
    result = describe("Resistance", "")
    assert result["source_support_polarity"] == NOT_REPORTED
    assert result["source_alignment_status"] == SOURCE_ALIGNMENT_NOT_AVAILABLE
    assert result["source_alignment_status"] != SOURCE_ALIGNED


def test_unknown_source_value_is_flagged_not_guessed():
    assert source_support_polarity("Probably Supports") == UNMAPPED_SOURCE_VALUE
    assert source_alignment_status(UNMAPPED_SOURCE_VALUE, "RESISTANCE") == "SOURCE_ALIGNMENT_UNCLEAR"
    assert graph_direction("Something Novel") == "UNMAPPED_SOURCE_VALUE"


def test_all_eighteen_observed_significance_values_map():
    observed = [
        "Sensitivity/Response", "Resistance", "Positive", "Predisposition",
        "Poor Outcome", "Uncertain Significance", "Oncogenicity", "Better Outcome",
        "Dominant Negative", "Gain of Function", "Loss of Function",
        "Reduced Sensitivity", "Adverse Response", "Negative", "Neomorphic",
        "Unaltered Function", "Protectiveness",
    ]
    for value in observed:
        assert graph_direction(value) != "UNMAPPED_SOURCE_VALUE", value
    assert graph_direction("") == "UNKNOWN"


def test_supported_direction_requires_support():
    assert source_supported_direction(DOES_NOT_SUPPORT_ASSERTION, "RESISTANCE") is None
    assert source_supported_direction(NOT_REPORTED, "RESISTANCE") is None
    assert source_supported_direction(SUPPORTS_ASSERTION, "RESISTANCE") == "RESISTANCE"


def test_source_properties_preserved_in_raw():
    result = describe("Resistance", "Does Not Support")
    assert result["source_polarity_raw"] == {
        "significance": "Resistance", "evidence_direction": "Does Not Support"}


# ======================================================== §22 — ALTERAZIONI

def test_atomic_expression():
    result = parse_alteration_expression("BRAF V600E")
    assert result["alteration_parse_status"] == ATOMIC
    assert result["alteration_terms"] == [
        {"gene": "BRAF", "alteration": "V600E", "raw": "BRAF V600E"}]


def test_and_expression_keeps_all_terms():
    result = parse_alteration_expression("EGFR T790M AND EGFR Exon 19 Deletion AND EGFR C797S")
    assert result["alteration_parse_status"] == PARSED_EXACT
    assert [t["alteration"] for t in result["alteration_terms"]] == [
        "T790M", "Exon 19 Deletion", "C797S"]
    assert ast_from_dict(result["alteration_expression_ast"]).node_type == "AND"


def test_or_expression_is_not_turned_into_and():
    result = parse_alteration_expression("BRCA1 Mutation OR BRCA2 Mutation")
    node = ast_from_dict(result["alteration_expression_ast"])
    assert node.node_type == "OR"
    assert node.node_type != "AND"


def test_nested_parentheses_group_correctly():
    result = parse_alteration_expression("BRAF Amplification AND ( BRAF V600E OR BRAF V600K )")
    node = ast_from_dict(result["alteration_expression_ast"])
    assert node.node_type == "AND"
    assert [o.node_type for o in node.operands] == ["TERM", "OR"]
    assert len(node.terms()) == 3


def test_hgvs_parentheses_are_not_grouping():
    result = parse_alteration_expression("VHL R200W (c.598C>T)")
    assert result["alteration_parse_status"] == ATOMIC
    assert result["alteration_terms"][0]["alteration"] == "R200W (c.598C>T)"


def test_not_operator():
    result = parse_alteration_expression("MET Amplification AND NOT KRAS Mutation")
    node = ast_from_dict(result["alteration_expression_ast"])
    assert node.node_type == "AND"
    assert node.operands[1].node_type == "NOT"


def test_repeated_gene_is_not_deduplicated():
    result = parse_alteration_expression("BRAF V600E AND BRAF V600M")
    assert [t["gene"] for t in result["alteration_terms"]] == ["BRAF", "BRAF"]
    assert len(result["alteration_terms"]) == 2


def test_multi_gene_expression_keeps_each_gene():
    result = parse_alteration_expression(
        "NTRK1 Amplification OR NTRK3 Amplification OR NTRK2 Amplification")
    assert [t["gene"] for t in result["alteration_terms"]] == ["NTRK1", "NTRK3", "NTRK2"]


def test_fusion_gene_is_kept_whole():
    result = parse_alteration_expression("EML4::ALK Fusion AND ALK C1156Y")
    assert result["alteration_terms"][0]["gene"] == "EML4::ALK"


def test_malformed_expression_preserves_raw_and_does_not_take_first_term():
    result = parse_alteration_expression("BRAF V600E AND")
    assert result["alteration_parse_status"] == MALFORMED_EXPRESSION
    assert result["alteration_expression_raw"] == "BRAF V600E AND"
    assert result["alteration_terms"] == [], "nessun termine estratto da un'espressione rotta"


def test_missing_expression():
    assert parse_alteration_expression(None)["alteration_parse_status"] == MISSING
    assert parse_alteration_expression("")["alteration_parse_status"] == MISSING


def test_round_trip_raw_to_ast_to_canonical():
    raw = "EGFR T790M AND EGFR Exon 19 Deletion AND EGFR C797S"
    first = parse_alteration_expression(raw)
    second = parse_alteration_expression(first["alteration_canonical_expression"])
    assert (ast_from_dict(first["alteration_expression_ast"]).terms()
            and [t.raw for t in ast_from_dict(first["alteration_expression_ast"]).terms()]
            == [t.raw for t in ast_from_dict(second["alteration_expression_ast"]).terms()])


def test_expression_hash_is_stable_and_discriminating():
    a = parse_alteration_expression("A1 X AND B2 Y")
    b = parse_alteration_expression("A1 X AND B2 Y")
    c = parse_alteration_expression("A1 X OR B2 Y")
    assert a["alteration_expression_hash"] == b["alteration_expression_hash"]
    assert a["alteration_expression_hash"] != c["alteration_expression_hash"], \
        "AND e OR non possono avere lo stesso hash"
    assert expression_hash(None) is None


def test_every_profile_in_the_export_parses():
    """Nessuna espressione del corpus reale fallisce il parsing."""
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from evaluation.rq1.kg_source import FrozenKnowledgeGraph
    graph = FrozenKnowledgeGraph(
        REPO_ROOT.parent / "data_expl" / "DatasetTESI" / "Dataset TESI" / "Clean_Graph_Data")
    failures = []
    for row in graph.tables["node_molecular_profile.csv"]:
        result = parse_alteration_expression(row.get("name"))
        if result["alteration_parse_status"] in {
                MALFORMED_EXPRESSION, "UNSUPPORTED_EXPRESSION", "AMBIGUOUS_OPERATOR"}:
            failures.append(row.get("name"))
    assert failures == [], f"espressioni non analizzabili: {failures[:5]}"


# ------------------------------------------------------ match futuro (§9)

def _case(*pairs):
    return {"biomarkers": [{"gene": g, "alteration": a} for g, a in pairs]}


def test_partial_match_on_and_is_not_full_match():
    ast = parse_alteration_expression("EGFR T790M AND EGFR C797S")["alteration_expression_ast"]
    result = evaluate_alteration_expression(_case(("EGFR", "T790M")), ast)
    assert result["result"] == PARTIAL_MATCH
    assert result["result"] != FULL_MATCH


def test_and_requires_both():
    ast = parse_alteration_expression("EGFR T790M AND EGFR C797S")["alteration_expression_ast"]
    result = evaluate_alteration_expression(_case(("EGFR", "T790M"), ("EGFR", "C797S")), ast)
    assert result["result"] == FULL_MATCH


def test_or_requires_only_one():
    ast = parse_alteration_expression("BRCA1 Mutation OR BRCA2 Mutation")["alteration_expression_ast"]
    assert evaluate_alteration_expression(_case(("BRCA1", "Mutation")), ast)["result"] == FULL_MATCH


def test_no_match_and_insufficient_information_are_distinct():
    ast = parse_alteration_expression("BRAF V600E")["alteration_expression_ast"]
    assert evaluate_alteration_expression(_case(("KRAS", "G12D")), ast)["result"] == NO_MATCH
    assert evaluate_alteration_expression({"biomarkers": []}, ast)["result"] == INSUFFICIENT_CASE_INFORMATION


def test_unavailable_and_unsupported_expressions():
    assert evaluate_alteration_expression(_case(("BRAF", "V600E")), None)["result"] == EXPRESSION_UNAVAILABLE
    assert evaluate_alteration_expression(
        _case(("BRAF", "V600E")), {"node_type": "TERM"},
        parse_status=MALFORMED_EXPRESSION)["result"] == EXPRESSION_UNSUPPORTED


# =========================================================== §23 — REGIMI

_DRUGS = {"1": {"drug_name": "SORAFENIB"}, "2": {"drug_name": "IMATINIB"},
          "3": {"drug_name": "NILOTINIB"}}


def _rows(*ids):
    return [{"target_drug_concept_id": i} for i in ids]


def test_single_agent():
    result = build_intervention("34", _rows("1"), _DRUGS)
    assert result["intervention_structure"] == SINGLE_AGENT
    assert result["regimen_semantics_status"] == NOT_APPLICABLE
    assert eligible_for_intervention_exact_match(result)


def test_multi_component_is_unresolved_not_confirmed():
    """Il caso reale: evidence 34, SORAFENIB + IMATINIB + NILOTINIB."""
    result = build_intervention("34", _rows("1", "2", "3"), _DRUGS)
    assert result["intervention_structure"] == MULTI_COMPONENT_UNRESOLVED
    assert result["intervention_structure"] != "COMBINATION_CONFIRMED"
    assert result["regimen_semantics_status"] == SEMANTICS_UNAVAILABLE_IN_SOURCE
    assert len(result["intervention_components"]) == 3
    assert not eligible_for_intervention_exact_match(result)


def test_unresolved_regimen_keeps_every_component():
    result = build_intervention("34", _rows("1", "2", "3"), _DRUGS)
    assert {c["name"] for c in result["intervention_components"]} == {
        "SORAFENIB", "IMATINIB", "NILOTINIB"}


def test_no_pharmacological_role_is_invented():
    result = build_intervention("34", _rows("1", "2", "3"), _DRUGS)
    assert {c["component_role"] for c in result["intervention_components"]} == {"UNKNOWN"}


def test_regimen_id_is_order_independent_and_stable():
    a = build_intervention("34", _rows("1", "2", "3"), _DRUGS)["regimen_id"]
    b = build_intervention("34", _rows("3", "1", "2"), _DRUGS)["regimen_id"]
    assert a == b
    c = build_intervention("35", _rows("1", "2", "3"), _DRUGS)["regimen_id"]
    assert a != c


def test_component_order_is_preserved_in_the_list():
    result = build_intervention("34", _rows("3", "1"), _DRUGS)
    assert [c["name"] for c in result["intervention_components"]] == ["NILOTINIB", "SORAFENIB"]


def test_duplicate_components_are_not_silently_collapsed():
    result = build_intervention("34", _rows("1", "1"), _DRUGS)
    assert len(result["intervention_components"]) == 2
    assert result["intervention_structure"] == MULTI_COMPONENT_UNRESOLVED


def test_raw_label_is_preserved():
    result = build_intervention("34", _rows("1", "2"), _DRUGS)
    assert result["intervention_expression_raw"] == "SORAFENIB | IMATINIB"


# ======================================================== §24 — INVARIANTI

def _candidate(**overrides) -> GraphCandidateAssertionV3:
    parts = {
        "materialization_rule_id": "gca/3.0/evidence-to-intervention",
        "materialized_at": "2026-08-06T00:00:00Z",
        "subject": {"id": "Variant:1", "label": "V600E", "type": "Variant", "canonical_id": None},
        "predicate": "associated_with_resistance_to",
        "object": {"id": "Drug:1", "label": "SORAFENIB", "type": "Drug", "canonical_id": None},
        "disease": [],
        "graph_direction": "RESISTANCE",
        "source_support_polarity": SUPPORTS_ASSERTION,
        "source_supported_direction": "RESISTANCE",
        "source_alignment_status": SOURCE_ALIGNED,
        "source_polarity_raw": {"significance": "Resistance", "evidence_direction": "Supports"},
        "alteration_expression_raw": "BRAF V600E",
        "alteration_terms": [{"gene": "BRAF", "alteration": "V600E", "raw": "BRAF V600E"}],
        "alteration_expression_ast": {"node_type": "TERM", "gene": "BRAF",
                                      "alteration": "V600E", "raw": "BRAF V600E"},
        "alteration_parse_status": ATOMIC,
        "alteration_expression_hash": "x", "alteration_parse_warnings": [],
        "alteration_canonical_expression": "BRAF V600E",
        "intervention_expression_raw": "SORAFENIB",
        "intervention_components": [{"concept_id": "1", "name": "SORAFENIB",
                                     "node_id": "Drug:1", "component_role": "UNKNOWN"}],
        "intervention_structure": SINGLE_AGENT,
        "regimen_semantics_status": NOT_APPLICABLE,
        "regimen_id": "RGM-x", "regimen_limitations": [],
        "biomarkers": [], "evidence_scope": "Predictive", "diagnostic_scope": None,
        "graph_path": ["Variant:1"], "node_ids": ["Variant:1"], "edge_ids": ["edge:a"],
        "evidence_record_ids": ["evidence:1"], "document_identifiers": [],
        "source_properties": {}, "source_path_ids": ["p1"], "v2_candidate_ids": [],
        "known_limitations": [],
    }
    parts.update(overrides)
    return GraphCandidateAssertionV3.from_parts(**parts)


def test_invariant_1_source_path_required():
    assert "INV1_NO_SOURCE_PATH_ID" in _candidate(source_path_ids=[]).validate()
    assert not _candidate().validate()


def test_invariant_2_does_not_support_cannot_be_aligned():
    candidate = _candidate(source_support_polarity=DOES_NOT_SUPPORT_ASSERTION,
                           source_supported_direction=None)
    candidate.source_alignment_status = SOURCE_ALIGNED
    assert "INV2_DOES_NOT_SUPPORT_MARKED_ALIGNED" in candidate.validate()


def test_invariant_2b_supported_direction_requires_support():
    candidate = _candidate(source_support_polarity=DOES_NOT_SUPPORT_ASSERTION,
                           source_alignment_status=SOURCE_DOES_NOT_SUPPORT,
                           source_supported_direction="RESISTANCE")
    assert "INV2B_SUPPORTED_DIRECTION_WITHOUT_SUPPORT" in candidate.validate()


def test_invariant_3_parsed_terms_match_ast():
    candidate = _candidate(alteration_terms=[
        {"gene": "BRAF", "alteration": "V600E", "raw": "BRAF V600E"},
        {"gene": "EXTRA", "alteration": "X", "raw": "EXTRA X"}])
    assert "INV3_TERM_COUNT_MISMATCH" in candidate.validate()


def test_invariant_4_unresolved_needs_two_components():
    candidate = _candidate(intervention_structure=MULTI_COMPONENT_UNRESOLVED)
    assert "INV4_UNRESOLVED_WITH_FEWER_THAN_TWO_COMPONENTS" in candidate.validate()


def test_invariant_5_no_confirmed_combination_without_source_semantics():
    candidate = _candidate(intervention_structure="COMBINATION_CONFIRMED",
                           regimen_semantics_status=SEMANTICS_UNAVAILABLE_IN_SOURCE)
    assert "INV5_CONFIRMED_COMBINATION_WITHOUT_SOURCE_SEMANTICS" in candidate.validate()


def test_invariant_6_identity_is_deterministic():
    a, b = _candidate(), _candidate()
    assert a.candidate_id == b.candidate_id and a.payload_hash == b.payload_hash
    a.predicate = "tampered"
    assert "INV6_NON_DETERMINISTIC_IDENTITY" in a.validate()


# ==================================================== repository e migrazione

def test_v2_repository_is_unchanged():
    import hashlib
    digest = hashlib.sha256((V2 / "candidates.jsonl").read_bytes()).hexdigest()
    assert digest == "d6c65c2682313652b736f1f82968078292c12588823e2f79309e76d6e671235d"


def test_runtime_default_repository_is_still_v2():
    from gca_v3.repository import DEFAULT_VERSION, configured_version, describe as describe_repo
    assert DEFAULT_VERSION == "2.0"
    assert configured_version() == "2.0"
    assert describe_repo()["runtime_default_changed_to_v3"] is False


def test_unsupported_repository_version_raises_instead_of_defaulting(monkeypatch):
    from gca_v3.repository import UnsupportedRepositoryVersion, configured_version
    monkeypatch.setenv("GRAPH_CANDIDATE_REPOSITORY_VERSION", "9.9")
    with pytest.raises(UnsupportedRepositoryVersion):
        configured_version()


@pytest.mark.skipif(not (V3 / "manifest.json").exists(), reason="repository v3 non costruito")
def test_v3_manifest_declares_its_limits():
    manifest = json.loads((V3 / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["contract_version"] == CONTRACT_VERSION
    assert manifest["confirmed_combination_count"] == 0, \
        "l'export non consente di confermare alcuna combinazione"
    assert manifest["unresolved_multi_component_count"] == 572
    assert manifest["predecessor"]["unchanged"] is True
    assert any("REGIMEN_SEMANTICS_UNAVAILABLE_IN_EXPORT" in limit
               for limit in manifest["known_limitations"])


@pytest.mark.skipif(not (V3 / "v2_mapping.jsonl").exists(), reason="mapping non costruito")
def test_v2_to_v3_mapping_covers_every_v2_candidate():
    rows = [json.loads(line) for line in
            (V3 / "v2_mapping.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    v2_ids = {r["v2_candidate_id"] for r in rows if r["v2_candidate_id"]}
    assert len(v2_ids) == 46864
    many_to_one = [r for r in rows if r["relation_type"] == "MANY_TO_ONE"]
    assert len(many_to_one) == 1294, "gli 1294 archi dei record multi-farmaco"
    assert {r["reason_code"] for r in many_to_one} == {"REGIMEN_UNIT_MERGED"}


@pytest.mark.skipif(not (V3 / "candidates.jsonl").exists(), reason="repository v3 non costruito")
def test_no_v3_candidate_promotes_an_unsupported_source():
    """Nessuna candidate con fonte 'Does Not Support' risulta allineata."""
    offenders = []
    for line in (V3 / "candidates.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if (record["source_support_polarity"] == DOES_NOT_SUPPORT_ASSERTION
                and record["source_alignment_status"] == SOURCE_ALIGNED):
            offenders.append(record["candidate_id"])
    assert offenders == []
