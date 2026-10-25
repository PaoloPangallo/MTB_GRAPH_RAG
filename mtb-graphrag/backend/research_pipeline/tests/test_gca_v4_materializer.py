import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from mtb_gca_v4 import materialize_source  # noqa: E402


def _write_csv(root: Path, name: str, rows: list[dict[str, str]]) -> None:
    path = root / name
    fields = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _minimal_source(tmp_path: Path) -> Path:
    source = tmp_path / "Clean_Graph_Data"
    source.mkdir()
    _write_csv(source, "node_gene.csv", [{"entrez_id": "1", "hugo_symbol": "GENE1"}])
    _write_csv(source, "node_variant.csv", [{"variant_id": "1", "variant_name": "V1"}])
    _write_csv(source, "node_molecular_profile.csv", [{"molecular_profile_id": "1", "name": "GENE1 V1"}])
    _write_csv(source, "node_evidence.csv", [{
        "evidence_id": "1", "evidence_statement": "GENE1 V1 supports treatment",
        "citation_id": "12345678", "evidence_direction": "Supports", "significance": "Sensitivity/Response",
        "evidence_type": "Predictive", "disease": "Disease 1", "doid": "1",
    }])
    _write_csv(source, "node_drug.csv", [{"concept_id": "drug:1", "drug_name": "Drug 1"}])
    _write_csv(source, "node_companion_diagnostic.csv", [{"device_id": "cdx:1", "device_name": "CDx 1"}])
    _write_csv(source, "nodes_clinical_trials.csv", [{"nct_id": "NCT00000001", "title": "Trial 1"}])
    _write_csv(source, "trial_eligibility_criteria.csv", [{"nct_id": "NCT00000001", "eligibility_criteria": "GENE1"}])
    _write_csv(source, "edge_has_evidence.csv", [{"source_molecular_profile_id": "1", "target_evidence_id": "1"}])
    _write_csv(source, "edge_targets_drug.csv", [{
        "source_evidence_id": "1", "target_drug_concept_id": "drug:1",
        "evidence_level": "A", "significance": "Sensitivity/Response", "evidence_direction": "Supports",
    }])
    _write_csv(source, "edge_interacts_with.csv", [{
        "source_gene_entrez_id": "1", "target_drug_concept_id": "drug:1",
        "interaction_type": "target", "interaction_score": "1", "source_db": "CIViC",
    }])
    _write_csv(source, "edge_has_variant.csv", [{"source_entrez_id": "1", "target_variant_id": "1"}])
    _write_csv(source, "edge_in_molecular_profile.csv", [{"source_variant_id": "1", "target_molecular_profile_id": "1"}])
    _write_csv(source, "edge_has_companion_diagnostic.csv", [{"source_drug_concept_id": "drug:1", "target_device_id": "cdx:1"}])
    _write_csv(source, "edge_diagnoses_gene.csv", [{"source_device_id": "cdx:1", "target_gene_entrez_id": "1"}])
    _write_csv(source, "edges_trial_drug.csv", [{"nct_id": "NCT00000001", "drug_name_raw": "Drug 1", "drug_name_normalized": "DRUG 1"}])
    _write_csv(source, "edges_trial_gene.csv", [{"nct_id": "NCT00000001", "gene_symbol": "GENE1", "source": "eligibility_criteria"}])
    return source


def test_materializes_all_autonomous_families_and_accounts_structural_edges(tmp_path: Path) -> None:
    result = materialize_source(_minimal_source(tmp_path), tmp_path / "repo")

    assert result["summary"]["materialized_candidates"] == 7
    assert result["summary"]["eligible_semantic_units"] == 7
    assert result["summary"]["excluded_with_reason"] == 0
    assert result["summary"]["unaccounted_eligible_units"] == 0
    assert {row["relation_family"] for row in result["candidates"]} == {
        "EVIDENCE_STATEMENT", "EVIDENCE_DRUG", "GENE_DRUG", "TRIAL_DRUG",
        "TRIAL_GENE", "DRUG_COMPANION_DIAGNOSTIC", "COMPANION_DIAGNOSTIC_GENE",
    }
    evidence = next(row for row in result["candidates"] if row["relation_family"] == "EVIDENCE_STATEMENT")
    assert "edge_has_evidence.csv" in evidence["source_datasets"]
    assert "edge_in_molecular_profile.csv" in evidence["edge_ids_by_dataset"]
    assert evidence["document_identifiers"] == [{"pmid": "12345678", "scope": "evidence_record"}]


def test_invalid_semantic_unit_is_excluded_and_not_silent(tmp_path: Path) -> None:
    source = _minimal_source(tmp_path)
    path = source / "edge_targets_drug.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    rows[0]["target_drug_concept_id"] = "drug:missing"
    _write_csv(source, path.name, rows)

    result = materialize_source(source, tmp_path / "repo")
    reasons = {row["reason"] for row in result["exclusions"]}
    assert "INVALID_REFERENCE" in reasons
    assert result["summary"]["unaccounted_eligible_units"] == 0


def test_materialization_is_deterministic(tmp_path: Path) -> None:
    source = _minimal_source(tmp_path)
    first = materialize_source(source, tmp_path / "repo1")
    second = materialize_source(source, tmp_path / "repo2")

    assert first["hashes"]["candidates_sha256"] == second["hashes"]["candidates_sha256"]
    assert first["hashes"]["exclusions_sha256"] == second["hashes"]["exclusions_sha256"]
    assert [row["candidate_id"] for row in first["candidates"]] == [row["candidate_id"] for row in second["candidates"]]


def test_optional_pmcid_enrichment_does_not_change_semantics(tmp_path: Path) -> None:
    source = _minimal_source(tmp_path)
    manifest = tmp_path / "pmid_manifest.jsonl"
    manifest.write_text(json.dumps({
        "pmid": "12345678", "pmcid": "PMC123", "final_document_status": "FULL_TEXT_PMC",
    }) + "\n", encoding="utf-8")

    baseline = materialize_source(source, tmp_path / "baseline")
    result = materialize_source(source, tmp_path / "repo", document_manifest=manifest)
    evidence = next(row for row in result["candidates"] if row["relation_family"] == "EVIDENCE_STATEMENT")
    baseline_evidence = next(row for row in baseline["candidates"] if row["relation_family"] == "EVIDENCE_STATEMENT")
    assert evidence["document_identifiers"] == [{"pmid": "12345678", "pmcid": "PMC123", "scope": "evidence_record"}]
    assert evidence["semantic_key"] == baseline_evidence["semantic_key"]
