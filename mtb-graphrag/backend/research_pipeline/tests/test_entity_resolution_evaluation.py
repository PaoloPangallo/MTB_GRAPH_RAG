import pytest
from backend.research_pipeline.terminology.evaluation import evaluate


def row(identifier, independent=False):
    return {"id": identifier, "text": "x", "domain": "GENE", "language": "en", "split": "test",
            "expected_entities": ["NCBIGene:1"], "annotation_sources": ["fixture"],
            "review_status": "INDEPENDENTLY_REVIEWED" if independent else "UNREVIEWED",
            "independence": independent, "concept_group": identifier}


def test_denominators_and_synthetic_separation():
    report = evaluate([row("a"), row("b", True)], {"fixture": lambda r: {"concept_ids": ["NCBIGene:1"]}})
    assert report["independent_evaluation"]["sample_count"] == 1
    assert report["regression_probes"]["sample_count"] == 1
    assert report["clinical_validation"] is False
    assert report["regression_probes"]["strategies"]["fixture"]["precision"] == 1


def test_leaked_groups_rejected_and_empty_gold_not_inflated():
    a, b = row("a"), row("b")
    a["split"] = "development"
    b["concept_group"] = "a"
    with pytest.raises(ValueError, match="leak"):
        evaluate([a, b], {})
    a["expected_entities"] = []
    report = evaluate([a], {"fixture": lambda r: {"concept_ids": []}})
    metrics = report["regression_probes"]["strategies"]["fixture"]
    assert metrics["precision"] is None and metrics["recall"] is None
    assert metrics["abstention_rate"] == 1
