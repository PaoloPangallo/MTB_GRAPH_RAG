from copy import deepcopy

from backend.research_pipeline.tests.test_terminology_registry import term
from backend.research_pipeline.terminology.registry import Registry
from backend.research_pipeline.terminology.case_resolution import resolve_case, disease_context
from backend.research_pipeline.terminology.molecular import resolve_variant, parse_profile, evaluate_profile


def fixture():
    return Registry([term("DOID:9256", "colorectal cancer", "DISEASE", "PREFERRED"),
                     term("NCBIGene:673", "BRAF", scope="PREFERRED"),
                     term("CIViCVariant:12", "V600E", "VARIANT", gene_id="NCBIGene:673"),
                     term("CIViCVariant:13", "V600K", "VARIANT", gene_id="NCBIGene:673")], "test")


def test_projection_preserves_text_and_context():
    registry = fixture()
    case = {"disease": {"raw_value": "metastatic colorectal cancer"},
            "biomarkers": [{"gene": "BRAF", "alteration": "p.(Val600Glu)", "assertion_status": "PRESENT"}]}
    before = deepcopy(case)
    projected = resolve_case(case, registry)
    assert case == before
    assert projected["entity_resolution"]["diseases"][0]["residual_context"] == "metastatic"
    assert projected["entity_resolution"]["biomarkers"][0]["variant"]["concept_ids"] == ("CIViCVariant:12",)
    assert "REFERENCE_UNSPECIFIED" in projected["entity_resolution"]["biomarkers"][0]["variant"]["reasons"]
    assert "PREDICTED_PROTEIN_CONSEQUENCE" in projected["entity_resolution"]["biomarkers"][0]["variant"]["reasons"]


def test_competing_diseases_do_not_choose_first():
    registry = Registry([term("DOID:1", "lung cancer", "DISEASE"), term("DOID:2", "breast cancer", "DISEASE")], "test")
    assert disease_context("lung cancer and breast cancer", registry)["status"] == "AMBIGUOUS"
    assert disease_context("unknown cancer", registry)["status"] == "UNMAPPED"


def test_unknown_is_not_negative_and_boolean_syntax_is_explicit():
    registry = fixture()
    profile = parse_profile("BRAF V600E AND NOT BRAF V600K", registry)
    assert profile["status"] == "RESOLVED"
    positive = {"concept_ids": ["CIViCVariant:12"], "assertion_status": "PRESENT"}
    negative = {"concept_ids": ["CIViCVariant:13"], "assertion_status": "ABSENT"}
    assert evaluate_profile(profile["ast"], [positive]) == "UNKNOWN"
    assert evaluate_profile(profile["ast"], [positive, negative]) == "TRUE"
    assert parse_profile("BRAF V600E + BRAF V600K", registry)["status"] == "UNMAPPED"
    gene = registry.resolve("GENE", "BRAF")
    assert resolve_variant(gene, "NP_999999.1:p.Val600Glu", registry).status == "UNMAPPED"
