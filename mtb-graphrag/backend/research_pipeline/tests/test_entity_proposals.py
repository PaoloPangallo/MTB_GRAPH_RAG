import pytest
from backend.research_pipeline.tests.test_terminology_registry import term
from backend.research_pipeline.terminology.registry import Registry
from backend.research_pipeline.terminology.proposals import propose


def test_shadow_unavailable_deduplicates_and_never_verifies():
    registry = Registry([term("DOID:1", "colorectal cancer", "DISEASE"), term("DOID:1", "colon cancer", "DISEASE"),
                         term("NCBIGene:1", "colon")], "test")
    result = propose("colorectal tumour", "DISEASE", registry, encoder=None)
    assert result["status"] == "MODEL_UNAVAILABLE"
    assert all(p["verified"] is False and p["domain"] == "DISEASE" for p in result["proposals"])
    assert len({p["concept_id"] for p in result["proposals"]}) == len(result["proposals"])
    assert registry.resolve("DISEASE", "colorectal tumour").status == "UNMAPPED"
    with pytest.raises(ValueError):
        propose("x", "DISEASE", registry, top_k=0)


def test_dense_failure_and_index_mismatch_are_explicit():
    class Encoder:
        model_identifier = "fixture"
        model_revision = "a" * 40
        index_registry_version = "wrong"
        supported_languages = {"en"}
        def encode(self, texts):
            raise AssertionError("must validate index first")
    registry = Registry([term("DOID:1", "cancer", "DISEASE")], "test")
    assert propose("cancer", "DISEASE", registry, encoder=Encoder())["reason"] == "INDEX_VERSION_MISMATCH"
    assert propose("cancro", "DISEASE", registry, encoder=Encoder(), language="it")["status"] == "UNSUPPORTED_LANGUAGE"
