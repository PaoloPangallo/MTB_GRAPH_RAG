"""Test del codice di valutazione (§27).

Coprono la chiave canonica, il confronto path/candidate, la normalizzazione dei
PMID, l'immutabilità del benchmark congelato, l'aggregazione delle metriche e
l'assenza di segreti negli artefatti.

Nessun test effettua chiamate di rete o al provider LLM.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from evaluation.rq1.canonical_key import (
    CanonicalKey, canonical_key, norm_document_identifiers, norm_entity,
    norm_identifier, norm_text,
)
from evaluation.rq1.compare import (
    ALTERATION_LOST, DIRECTION_INVERSION, MaterializationComparator,
    PATH_NOT_FOUND, REGIMEN_SPLIT, SPURIOUS_CANDIDATE, aggregate,
)
from evaluation.rq1.kg_source import EligiblePath, edge_identity, payload_identity
from evaluation.rq2.pairs import build_pairs, normalize_pmid, provenance_level
from evaluation.rq3.models import ExternalCitationCandidate
from evaluation.rq4 import metrics as rq4_metrics

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_ROOT = REPO_ROOT / "evaluation"


# --------------------------------------------------------------- chiave canonica

def _candidate(**overrides):
    base = {
        "candidate_id": "GCA-test",
        "materialization_rule_id": "gca/2.0/evidence-to-drug",
        "predicate": "associated_with_sensitivity_to",
        "subject": {"id": "Variant:1", "label": "V600E", "type": "Variant", "canonical_id": None},
        "object": {"id": "Drug:9", "label": "DABRAFENIB", "type": "Drug", "canonical_id": None},
        "disease": [{"id": "Disease:1", "label": "Melanoma", "canonical_id": "DOID:1909"}],
        "biomarkers": [
            {"id": "Gene:673", "label": "BRAF", "type": "Gene", "canonical_id": None},
            {"id": "Variant:1", "label": "V600E", "type": "Variant", "canonical_id": None},
        ],
        "interventions": [{"id": "Drug:9", "label": "DABRAFENIB", "type": "Drug", "canonical_id": None}],
        "regimen": [],
        "direction": "Sensitivity/Response",
        "evidence_scope": "Predictive",
        "diagnostic_scope": None,
        "graph_path": ["Variant:1", "MolecularProfile:1", "Evidence:1", "Drug:9"],
        "node_ids": ["Variant:1", "MolecularProfile:1", "Evidence:1", "Drug:9"],
        "edge_ids": ["edge:a", "edge:b"],
        "evidence_record_ids": ["evidence:1"],
        "document_identifiers": [{"pmid": "123", "scope": "evidence_record"}],
        "source_properties": {},
        "group_id": None,
    }
    base.update(overrides)
    # Il confronto verifica che candidate_id e payload_hash derivino davvero dal
    # payload: la fixture deve quindi portare un lineage coerente, altrimenti
    # ogni test scatterebbe su LINEAGE_BROKEN invece che sul caso in esame.
    payload = {k: base[k] for k in (
        "subject", "predicate", "object", "disease", "biomarkers", "interventions",
        "regimen", "direction", "evidence_scope", "diagnostic_scope", "graph_path",
        "node_ids", "edge_ids", "evidence_record_ids", "document_identifiers",
        "source_properties", "materialization_rule_id", "group_id",
    )}
    if "payload_hash" not in overrides:
        base["candidate_id"], base["payload_hash"] = payload_identity(payload)
    return base


def test_null_tokens_collapse_but_clinical_terms_do_not():
    assert norm_text("nan") is None
    assert norm_text("  ") is None
    assert norm_text("NULL") is None
    # Nessuna mappatura di sinonimi: BGJ398 e infigratinib restano distinti.
    assert norm_text("BGJ398") != norm_text("infigratinib")


def test_identifiers_are_case_sensitive_labels_are_not():
    assert norm_identifier("NCT01234567") != norm_identifier("nct01234567")
    assert norm_text("Melanoma") == norm_text("melanoma")


def test_canonical_key_separates_direction():
    """Due candidate identiche salvo la direction non devono collassare."""
    a = canonical_key(_candidate())
    b = canonical_key(_candidate(direction="Resistance"))
    assert a.semantic() != b.semantic()


def test_canonical_key_separates_disease():
    a = canonical_key(_candidate())
    b = canonical_key(_candidate(disease=[{"id": "Disease:2", "label": "Colorectal Cancer",
                                           "canonical_id": "DOID:9256"}]))
    assert a.semantic() != b.semantic()


def test_canonical_key_does_not_merge_on_shared_gene_or_drug_alone():
    """Condividere gene e farmaco non basta a fondere due candidate."""
    a = canonical_key(_candidate())
    b = canonical_key(_candidate(
        disease=[{"id": "Disease:7", "label": "Thyroid Cancer", "canonical_id": "DOID:1781"}],
        node_ids=["Variant:1", "MolecularProfile:2", "Evidence:5", "Drug:9"],
    ))
    assert a.gene == b.gene and a.interventions == b.interventions
    assert a.semantic() != b.semantic()


def test_identity_key_distinguishes_paths_with_same_content():
    a = canonical_key(_candidate())
    b = canonical_key(_candidate(edge_ids=["edge:c", "edge:d"]))
    assert a.semantic() == b.semantic(), "il contenuto è lo stesso"
    assert a.identity() != b.identity(), "il path no"


def test_document_identifier_scope_is_part_of_the_key():
    one = norm_document_identifiers([{"pmid": "1", "scope": "evidence_record"}])
    two = norm_document_identifiers([{"pmid": "1", "scope": "linked_publication"}])
    assert one != two


def test_norm_entity_handles_missing():
    assert norm_entity(None) is None
    assert norm_entity({}) is None, "un'entità vuota non è un'entità"
    assert norm_entity({"id": "Gene:1"}) == ("Gene:1", None, None, None)


# ----------------------------------------------------- confronto path/candidate

def _path(**overrides) -> EligiblePath:
    candidate = _candidate()
    expected = {k: candidate[k] for k in (
        "subject", "predicate", "object", "disease", "biomarkers", "interventions",
        "regimen", "direction", "evidence_scope", "diagnostic_scope", "graph_path",
        "node_ids", "edge_ids", "evidence_record_ids", "document_identifiers",
        "source_properties",
    )}
    expected.update(overrides.pop("expected", {}))
    return EligiblePath(
        path_id=overrides.pop("path_id", "p1"),
        rule_id=overrides.pop("rule_id", "gca/2.0/evidence-to-drug"),
        source_table="edge_targets_drug.csv", source_row_index=1,
        expected=expected, diagnostics=overrides.pop("diagnostics", {}),
    )


def test_matching_path_and_candidate_produce_no_findings():
    result = MaterializationComparator([_path()], [_candidate()]).compare()
    comparison = result["comparisons"][0]
    assert comparison.matched
    assert comparison.findings == []
    assert result["spurious"] == []


def test_missing_candidate_is_detected():
    result = MaterializationComparator([_path()], []).compare()
    comparison = result["comparisons"][0]
    assert not comparison.matched
    assert comparison.findings[0]["class"] == PATH_NOT_FOUND


def test_spurious_candidate_is_detected():
    result = MaterializationComparator([], [_candidate()]).compare()
    assert len(result["spurious"]) == 1
    metrics = aggregate(result, [], 1)
    assert metrics["spurious_candidate_count"] == 1
    assert metrics["materialization_precision"] == 0.0


def test_direction_inversion_is_classified_separately_from_field_mismatch():
    path = _path(expected={"direction": "Resistance"})
    result = MaterializationComparator([path], [_candidate()]).compare()
    classes = {f["class"] for f in result["comparisons"][0].findings}
    assert DIRECTION_INVERSION in classes


def test_unrelated_direction_change_is_plain_field_mismatch():
    path = _path(expected={"direction": "Supports"})
    result = MaterializationComparator([path], [_candidate()]).compare()
    classes = {f["class"] for f in result["comparisons"][0].findings}
    assert DIRECTION_INVERSION not in classes
    assert classes


def test_alteration_loss_is_graph_fidelity_not_contract_violation():
    path = _path(diagnostics={"profile_variant_ids": ["1", "2"], "selected_variant_id": "1",
                              "dropped_variant_ids": ["2"]})
    result = MaterializationComparator([path], [_candidate()]).compare()
    comparison = result["comparisons"][0]
    assert comparison.findings == [], "il contratto è rispettato"
    assert any(f["class"] == ALTERATION_LOST for f in comparison.graph_fidelity_findings)


def test_regimen_split_detected_only_for_multi_drug_evidence():
    single = _path(diagnostics={"evidence_drug_edge_count": 1})
    multi = _path(diagnostics={"evidence_drug_edge_count": 3, "sibling_drug_names": ["A", "B", "C"]})
    r1 = MaterializationComparator([single], [_candidate()]).compare()
    r2 = MaterializationComparator([multi], [_candidate()]).compare()
    assert not any(f["class"] == REGIMEN_SPLIT for f in r1["comparisons"][0].graph_fidelity_findings)
    assert any(f["class"] == REGIMEN_SPLIT for f in r2["comparisons"][0].graph_fidelity_findings)


def test_exact_duplicates_are_counted():
    duplicate = _candidate(payload_hash="same", candidate_id="GCA-a")
    other = _candidate(payload_hash="same", candidate_id="GCA-b")
    result = MaterializationComparator([], [duplicate, other]).compare()
    assert result["duplicates"]["exact_duplicate_groups"] == 1
    assert result["duplicates"]["exact_duplicate_records"] == 2


def test_edge_and_payload_identity_are_deterministic():
    row = {"a": "1", "b": "2"}
    assert edge_identity("edge_x.csv", row, 3) == edge_identity("edge_x.csv", row, 3)
    assert edge_identity("edge_x.csv", row, 3) != edge_identity("edge_x.csv", row, 4)
    first = payload_identity({"k": "v"})
    assert first == payload_identity({"k": "v"})
    assert first[0].startswith("GCA-") and len(first[0]) == 28


def test_metric_aggregation_on_perfect_corpus():
    metrics = aggregate(
        MaterializationComparator([_path()], [_candidate()]).compare(), [_path()], 1)
    assert metrics["materialization_precision"] == 1.0
    assert metrics["materialization_recall"] == 1.0
    assert metrics["field_completeness"] == 1.0
    assert metrics["missing_candidate_count"] == 0


# ------------------------------------------------------------------ RQ2 / PMID

@pytest.mark.parametrize("raw,expected", [
    ("16081687", "16081687"),
    ("  16081687 ", "16081687"),
    ("PMID:16081687", "16081687"),
])
def test_valid_pmids_normalize(raw, expected):
    assert normalize_pmid(raw) == (expected, None)


@pytest.mark.parametrize("raw,reason", [
    ("", "EMPTY"),
    (None, "MISSING"),
    ("10.1182/blood-2021-148205", "NON_NUMERIC"),
    ("29355075;35398880", "COMPOUND_VALUE"),
    ("0123", "LEADING_ZERO"),
    ("abc", "NON_NUMERIC"),
])
def test_invalid_pmids_are_reported_not_repaired(raw, reason):
    value, why = normalize_pmid(raw)
    assert value is None
    assert why == reason


def test_provenance_level_follows_the_rule_not_the_scope():
    assert provenance_level("gca/2.0/evidence-statement") == "PMID_CANDIDATE_LEVEL"
    assert provenance_level("gca/2.0/evidence-to-drug") == "PMID_PARENT_LEVEL_ONLY"


def test_pairs_deduplicate_scopes_of_the_same_pmid():
    candidate = _candidate(document_identifiers=[
        {"pmid": "123", "scope": "evidence_record"},
        {"pmid": "123", "scope": "linked_publication"},
    ])
    pairs = build_pairs([candidate])
    assert len(pairs) == 1
    assert pairs[0].scopes == ["evidence_record", "linked_publication"]


def test_pairs_keep_distinct_pmids_separate():
    candidate = _candidate(document_identifiers=[
        {"pmid": "1", "scope": "evidence_record"},
        {"pmid": "2", "scope": "linked_publication"},
    ])
    assert len(build_pairs([candidate])) == 2


# ------------------------------------------------------------------------ RQ3

def test_external_citation_candidate_cannot_be_promoted_to_proof():
    candidate = ExternalCitationCandidate.create(
        "GCA-x", origin="ONCOKB", oncokb_data_version="v7.4", query_gene="BRAF",
        query_alteration="V600E", query_disease="Melanoma", query_intervention=None,
        match_level="EXACT_MATCH",
    )
    candidate.validate()
    candidate.promoted_to_documentary_support = True
    with pytest.raises(ValueError, match="prova documentale"):
        candidate.validate()


def test_external_citation_candidate_rejects_other_origins():
    candidate = ExternalCitationCandidate.create(
        "GCA-x", origin="SOMEWHERE_ELSE", oncokb_data_version=None, query_gene=None,
        query_alteration=None, query_disease=None, query_intervention=None,
        match_level="NO_MATCH",
    )
    with pytest.raises(ValueError, match="origin"):
        candidate.validate()


# ------------------------------------------------------------------------ RQ4

def test_frozen_benchmark_matches_its_manifest():
    """Il gold non deve essere cambiato dopo l'esecuzione."""
    import hashlib
    out = EVAL_ROOT / "rq4_casecontext_robustness"
    manifest = json.loads((out / "frozen_benchmark_manifest.json").read_text(encoding="utf-8"))
    payload = (out / "benchmark.jsonl").read_text(encoding="utf-8")
    assert hashlib.sha256(payload.encode("utf-8")).hexdigest() == manifest["benchmark_sha256"]
    assert manifest["case_count"] == 35
    assert all(v is True for v in manifest["mandatory_cases_present"].values())


def test_benchmark_structure_invariants():
    from evaluation.rq4.benchmark import validate_benchmark
    validate_benchmark()


def test_null_preservation_detects_a_populated_forbidden_field():
    case = {"case_id": "T", "category": "OUT_OF_SCOPE", "text": "Che tempo fa domani?",
            "fields_that_must_remain_null": ["disease"], "expected_disease": None,
            "expected_gene": [], "expected_alteration": [],
            "expected_previous_intervention": [], "expected_target_intervention": None}
    run = {"case_context": {"disease": {"raw_value": "domani", "normalized_value": "domani",
                                        "source_spans": []}, "biomarkers": []}}
    result = rq4_metrics.evaluate_case(case, run)
    assert result["null_preserved"] == 0
    assert any("POPULATED_BUT_MUST_BE_NULL" in h for h in result["hallucinated_fields"])


def test_quote_not_in_text_is_a_hallucination():
    context = {"disease": {"raw_value": "melanoma", "normalized_value": "melanoma",
                           "source_spans": [{"quote": "melanoma", "start_offset": 0, "end_offset": 8}]},
               "biomarkers": []}
    assert rq4_metrics.quotes_not_in_text(context, "the patient has a headache") == ["melanoma"]
    assert rq4_metrics.quotes_not_in_text(context, "a melanoma patient") == []


def test_fabricated_oncology_distinguishes_inference_from_literal_copy():
    literal = {"disease": {"raw_value": "febbre", "normalized_value": "febbre",
                           "source_spans": []}, "biomarkers": []}
    assert rq4_metrics.fabricated_oncology(literal, "Ho la febbre.") == []
    assert rq4_metrics.symptom_copied_into_disease(literal, "Ho la febbre.") == "febbre"

    inferred = {"disease": {"raw_value": "bone sarcoma", "normalized_value": "bone sarcoma",
                            "source_spans": []}, "biomarkers": []}
    assert rq4_metrics.fabricated_oncology(inferred, "Mi fa male la gamba.")


def test_out_of_scope_stop_and_forbidden_downstream_are_measured():
    from evaluation.rq4.harness import StageTracker, routing_decision
    tracker = StageTracker()
    assert tracker.forbidden_calls == 0
    tracker.record("retrieval")
    assert tracker.forbidden_calls == 1
    assert routing_decision(True, "FORCED_TOOL_VALID") == "PROCEED_TO_RETRIEVAL"
    assert routing_decision(False, "FORCED_TOOL_VALID") == "STOP_CASECONTEXT_MISMATCH"
    assert routing_decision(True, "HTTP_ERROR") == "STOP_TRANSPORT_FAILURE"
    assert routing_decision(True, "FORCED_TOOL_IGNORED") == "STOP_NO_VALID_CASECONTEXT"


def test_call_budget_is_enforced():
    from evaluation.rq4.harness import CallBudget
    budget = CallBudget(max_calls=1)
    budget.spend("c1")
    with pytest.raises(RuntimeError, match="budget"):
        budget.spend("c2")


# ------------------------------------------------------------------- sicurezza

def _artifact_files() -> list[Path]:
    skip = {".pyc"}
    return [
        p for p in EVAL_ROOT.rglob("*")
        if p.is_file() and p.suffix not in skip and "__pycache__" not in p.parts
    ]


def test_no_secrets_in_evaluation_artifacts():
    """Nessun token o credenziale negli artefatti prodotti."""
    import os
    from dotenv import dotenv_values
    secrets = {
        value for key, value in dotenv_values(REPO_ROOT / ".env").items()
        if value and len(value) >= 12 and any(
            token in key.upper() for token in ("TOKEN", "KEY", "PASSWORD", "SECRET")
        )
    }
    secrets |= {v for v in (os.getenv("ONCOKB_TOKEN"), os.getenv("OLLAMA_API_KEY")) if v and len(v) >= 12}
    assert secrets, "nessun segreto configurato: il test non proverebbe nulla"

    bearer = re.compile(r"Bearer\s+[A-Za-z0-9._\-]{12,}")
    offenders = []
    for path in _artifact_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(secret in text for secret in secrets) or bearer.search(text):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], f"segreti trovati in: {offenders}"


def test_no_patient_data_markers_in_artifacts():
    """Il benchmark è sintetico: nessun marcatore di dato reale di paziente."""
    forbidden = re.compile(r"\b(MRN|medical record number|codice fiscale|SSN)\b", re.I)
    offenders = [
        str(p.relative_to(REPO_ROOT)) for p in _artifact_files()
        if p.suffix in {".jsonl", ".json", ".csv"}
        and forbidden.search(p.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert offenders == []


def test_reviewer_columns_remain_empty():
    """Il giudizio umano non è precompilato in nessun campione."""
    import csv
    for name, columns in (
        ("rq1_gca_manual_review.csv", ("reviewer_correct", "reviewer_complete", "reviewer_notes")),
        ("rq2_pmid_manual_review.csv", ("reviewer_relevant", "reviewer_direction",
                                        "reviewer_specificity", "reviewer_notes")),
    ):
        path = EVAL_ROOT / "gold" / name
        if not path.exists():
            pytest.skip(f"{name} non ancora generato")
        with path.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        assert rows, f"{name} è vuoto"
        for row in rows:
            for column in columns:
                assert row[column] == "", f"{name}: {column} precompilato"
