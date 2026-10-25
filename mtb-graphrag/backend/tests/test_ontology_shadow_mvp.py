from pathlib import Path

from benchmarks.mtb_evidence.ontology_shadow_mvp import (
    EntityNormalizer,
    OntologyRegistry,
    OntologyShadowEvaluator,
)


ROOT = Path(__file__).resolve().parents[2]


def evaluator():
    registry = OntologyRegistry.from_local_assets(ROOT)
    return OntologyShadowEvaluator(registry, EntityNormalizer(registry))


def test_exact_synonym_and_missing_identifier_are_explicit():
    ev = evaluator()
    assert ev.compare("EGFR", "EGFR", "gene").match_type == "EXACT"
    assert ev.compare("EGFR L858R", "EGFR p.L858R", "variant").match_type == "SYNONYM"
    match = ev.compare("melanoma", "melanoma", "disease")
    assert match.match_type == "UNKNOWN"
    assert match.query_concept_id is None
    assert match.claim_concept_id is None


def test_directional_hierarchy_class_and_incompatibility():
    ev = evaluator()
    assert ev.compare(
        "Non-Small Cell Lung Cancer", "Lung Adenocarcinoma", "disease"
    ).match_type == "DESCENDANT"
    assert ev.compare(
        "Lung Adenocarcinoma", "Non-Small Cell Lung Cancer", "disease"
    ).match_type == "ANCESTOR"
    assert ev.compare("FGFR2 Fusion", "FGFR2::BICC1 Fusion", "variant").match_type == "RELATED"
    assert ev.compare("RMI2", "FGFR2::BICC1 Fusion", "variant").match_type == "INCOMPATIBLE"
    assert ev.compare("NSCLC", "Intrahepatic Cholangiocarcinoma", "disease").match_type == "INCOMPATIBLE"


def test_composition_variant_and_formulation_are_not_collapsed():
    ev = evaluator()
    assert ev.compare(
        "ALK Fusion AND ALK G1202R", "ALK G1202R AND v::ALK Fusion", "variant"
    ).match_type == "SYNONYM"
    assert ev.compare("EGFR L858R", "EGFR Exon 19 Deletion", "variant").match_type == "INCOMPATIBLE"
    assert ev.compare("FGFR2 Fusion", "FGFR2::BICC1 Fusion", "variant").compatible_candidate is False
    salt = ev.compare("alectinib", "alectinib hydrochloride", "intervention")
    assert salt.match_type in {"UNKNOWN", "RELATED"}
    assert salt.compatible_candidate is False


def test_shadow_evaluator_does_not_mutate_inputs_or_runtime_contract():
    ev = evaluator()
    claim = {"bucket": "primary", "score": 0.75, "claim_id": "x"}
    before = claim.copy()
    ev.evaluate_claim(claim, {"disease_context": "NSCLC", "biomarker_context": "EGFR L858R"})
    assert claim == before
