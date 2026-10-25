from backend.research_pipeline.casecontext.pipeline import validate_minimal_case_context


def context(*, disease=None, gene=None, alteration=None, intervention=None, intent=None):
    biomarkers = []
    if gene or alteration:
        biomarkers.append({"gene": gene, "alteration": alteration})
    return {
        "disease": {"raw_value": disease} if disease else None,
        "biomarkers": biomarkers,
        "target_intervention": {"raw_value": intervention} if intervention else None,
        "previous_interventions": [],
        "query_intent": intent,
    }


def test_gene_only_without_disease_is_minimally_valid():
    assert validate_minimal_case_context(context(gene="ERBB2"))["valid"] is True


def test_evaluation_without_disease_is_valid_with_gene_and_target():
    result = validate_minimal_case_context(
        context(gene="ERBB2", intervention="trastuzumab", intent="THERAPY_EVALUATION")
    )
    assert result["valid"] is True


def test_evaluation_without_target_is_invalid():
    result = validate_minimal_case_context(context(gene="ERBB2", intent="THERAPY_EVALUATION"))
    assert result == {
        "valid": False,
        "run_status": "INSUFFICIENT_CASE_CONTEXT",
        "missing": ["target_intervention"],
        "ambiguities": [],
    }


def test_discovery_without_disease_is_valid_with_molecular_anchor():
    result = validate_minimal_case_context(context(gene="ERBB2", intent="THERAPY_DISCOVERY"))
    assert result["valid"] is True


def test_no_useful_anchor_is_invalid():
    result = validate_minimal_case_context(context(disease="breast cancer"))
    assert result["valid"] is False
    assert result["missing"] == ["clinical_anchor"]

