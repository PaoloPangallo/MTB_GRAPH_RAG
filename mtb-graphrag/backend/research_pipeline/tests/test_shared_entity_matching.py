from backend.research_pipeline.tests.test_terminology_registry import term
from backend.research_pipeline.terminology.registry import Registry
from backend.research_pipeline.terminology.matching import active_registry
from backend.research_pipeline.retrieval.kg_retrieval import _term_matches, _molecular_term_matches
from backend.research_pipeline.enrichment.canonical_normalizer import entity_relation


def test_shared_alias_policy_and_no_invented_hierarchy():
    registry = Registry([term("NCBIGene:2064", "ERBB2"), term("NCBIGene:2064", "HER2"),
                         term("DOID:9256", "colorectal cancer", "DISEASE"),
                         term("DOID:9256", "CRC", "DISEASE")], "shared/test")
    token = active_registry.set(registry)
    try:
        assert _term_matches("metastatic CRC", "colorectal cancer")
        assert not _term_matches("CRC", "metastatic colorectal cancer")
        assert _molecular_term_matches("ERBB2", "HER2")
        assert entity_relation("ERBB2", "HER2", domain="GENE") == "CANONICAL_ALIAS"
        assert entity_relation("lung cancer", "small cell lung cancer", domain="DISEASE") not in {"CANONICAL_ALIAS", "IDENTICAL", "SOURCE_NARROWER"}
    finally:
        active_registry.reset(token)
