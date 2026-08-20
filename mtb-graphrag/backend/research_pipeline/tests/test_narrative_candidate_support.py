from __future__ import annotations

from backend.research_pipeline.narrative.input_projection import build_narrator_input
from backend.research_pipeline.narrative.verifier import FAIL, PASS, verify_narrative


def _dossier(candidate_support=None):
    entry = {
        "candidate_id": "GCA-SUPPORT",
        "drug": "PANITUMUMAB",
        "graph_relation": "associated_with_resistance_to",
        "status": "PARTIAL",
        "warnings": [],
        "gate_results": {
            "bucket": "WARNING_BUCKET",
            "support_mask": {"direction": "UNRELATED_EVIDENCE"},
        },
        "document_support": {"selected_papers": ["EB-1"]},
        "author_context": [],
        "validation_results": [],
    }
    if candidate_support is not None:
        entry["validation_results"] = [{
            "paper_id": "EB-1",
            "candidate_support": candidate_support,
        }]
    return {
        "case_id": "CASE-SUPPORT",
        "case_context": {
            "disease": {"normalized_value": "colorectal cancer"},
            "biomarkers": [{"normalized_value": "KRAS G12D"}],
            "target_intervention": {"normalized_value": "panitumumab"},
            "query_intent": "THERAPY_EVALUATION",
        },
        "candidate_therapies": [entry],
        "limitations": [],
        "provenance": {},
    }


def _support(result, **fields):
    return {"result": result, "fields": fields}


def _narrative(text):
    return {
        "narrative_summary": "Sintesi",
        "candidate_narratives": [{"candidate_id": "GCA-SUPPORT", "text": text}],
        "limitations_summary": "Limitazioni",
        "closing_note": "Nota",
    }


def _multi_paper_dossier(supports, *, candidate_id="GCA-MULTI"):
    dossier = _dossier()
    entry = dossier["candidate_therapies"][0]
    entry["candidate_id"] = candidate_id
    entry["validation_results"] = []
    entry["author_context"] = []
    for index, support in enumerate(supports, start=1):
        paper_id = f"EB-{index}"
        source_unit_id = f"SU-{index}"
        entry["validation_results"].append({
            "paper_id": paper_id,
            "candidate_id": candidate_id,
            "candidate_support": {
                **support,
                "candidate_id": candidate_id,
                "paper_id": paper_id,
                "source_unit_id": source_unit_id,
            },
        })
        entry["author_context"].append({
            "paper_id": paper_id,
            "source_unit_id": source_unit_id,
            "author_claim_quote": f"quote-{candidate_id}-{paper_id}",
            "presentation_state": "VALIDATED_QUOTE",
        })
    return dossier


def test_projection_passes_strong_support_explicitly():
    result = build_narrator_input(_dossier(_support("STRONG_SUPPORT")))
    assert result["candidates"][0]["candidate_support"]["result"] == "STRONG_SUPPORT"


def test_projection_passes_partial_support_fields_explicitly():
    support = _support(
        "PARTIAL_SUPPORT",
        gene="CONFIRMED",
        alteration="NOT_CONFIRMED",
        drug="CONFIRMED",
        direction="CONFIRMED",
    )
    candidate = build_narrator_input(_dossier(support))["candidates"][0]
    assert candidate["candidate_support"] == support


def test_projection_passes_other_support_levels():
    for level in ("CONTEXT_ONLY", "CONTRADICTORY", "UNVERIFIABLE"):
        candidate = build_narrator_input(_dossier(_support(level)))["candidates"][0]
        assert candidate["candidate_support"]["result"] == level


def test_projection_does_not_invent_support_for_legacy_candidate():
    candidate = build_narrator_input(_dossier())["candidates"][0]
    assert candidate["candidate_support"] is None


def test_multi_paper_support_levels_are_not_collapsed():
    dossier = _multi_paper_dossier([
        _support("STRONG_SUPPORT"),
        _support("PARTIAL_SUPPORT", alteration="NOT_CONFIRMED"),
    ])
    candidate = build_narrator_input(dossier)["candidates"][0]
    assert [item["candidate_support"]["result"] for item in candidate["candidate_support_checks"]] == [
        "STRONG_SUPPORT", "PARTIAL_SUPPORT",
    ]


def test_multi_paper_contradiction_is_preserved_with_strong_support():
    dossier = _multi_paper_dossier([
        _support("STRONG_SUPPORT"),
        _support("CONTRADICTORY"),
    ])
    candidate = build_narrator_input(dossier)["candidates"][0]
    assert [item["candidate_support"]["result"] for item in candidate["candidate_support_checks"]] == [
        "STRONG_SUPPORT", "CONTRADICTORY",
    ]


def test_multi_candidate_support_and_provenance_do_not_cross_contaminate():
    dossier = _multi_paper_dossier([_support("STRONG_SUPPORT")], candidate_id="GCA-A")
    second = _multi_paper_dossier(
        [_support("PARTIAL_SUPPORT", alteration="NOT_CONFIRMED")], candidate_id="GCA-B",
    )["candidate_therapies"][0]
    dossier["candidate_therapies"].append(second)
    candidates = build_narrator_input(dossier)["candidates"]
    assert candidates[0]["candidate_id"] == "GCA-A"
    assert candidates[1]["candidate_id"] == "GCA-B"
    assert candidates[0]["candidate_support_checks"][0]["candidate_support"]["result"] == "STRONG_SUPPORT"
    assert candidates[1]["candidate_support_checks"][0]["candidate_support"]["result"] == "PARTIAL_SUPPORT"
    assert candidates[0]["candidate_support_checks"][0]["document_id"] == "EB-1"
    assert candidates[1]["candidate_support_checks"][0]["document_id"] == "EB-1"
    assert candidates[0]["validated_quotes"][0]["quote"] == "quote-GCA-A-EB-1"
    assert candidates[1]["validated_quotes"][0]["quote"] == "quote-GCA-B-EB-1"


def test_partial_exact_support_claim_is_rejected():
    dossier = _dossier(_support(
        "PARTIAL_SUPPORT",
        gene="CONFIRMED",
        alteration="NOT_CONFIRMED",
        drug="CONFIRMED",
        direction="CONFIRMED",
    ))
    narrative = _narrative("KRAS G12D is associated with resistance to panitumumab.")
    result = verify_narrative(dossier, build_narrator_input(dossier), narrative)
    assert result["status"] == FAIL


def test_partial_narrative_preserves_missing_alteration():
    dossier = _dossier(_support(
        "PARTIAL_SUPPORT",
        gene="CONFIRMED",
        alteration="NOT_CONFIRMED",
        drug="CONFIRMED",
        direction="CONFIRMED",
    ))
    narrative = _narrative(
        "The document supports resistance to panitumumab in KRAS-mutated "
        "colorectal cancer, but the specific G12D alteration is not confirmed."
    )
    result = verify_narrative(dossier, build_narrator_input(dossier), narrative)
    assert result["status"] == PASS, result["reason_codes"]


def test_context_only_support_claim_is_rejected():
    dossier = _dossier(_support("CONTEXT_ONLY"))
    narrative = _narrative("The evidence supports KRAS G12D resistance to panitumumab.")
    result = verify_narrative(dossier, build_narrator_input(dossier), narrative)
    assert result["status"] == FAIL


def test_context_only_contextual_narrative_passes():
    dossier = _dossier(_support("CONTEXT_ONLY"))
    narrative = _narrative(
        "The cited passage provides contextual information about panitumumab "
        "but does not establish the candidate relationship."
    )
    result = verify_narrative(dossier, build_narrator_input(dossier), narrative)
    assert result["status"] == PASS, result["reason_codes"]


def test_contradictory_positive_narrative_is_rejected():
    dossier = _dossier(_support("CONTRADICTORY"))
    result = verify_narrative(
        dossier,
        build_narrator_input(dossier),
        _narrative("The candidate is confirmed and supported by the evidence."),
    )
    assert result["status"] == FAIL


def test_contradictory_narrative_preserving_opposition_passes():
    dossier = _dossier(_support("CONTRADICTORY"))
    result = verify_narrative(
        dossier,
        build_narrator_input(dossier),
        _narrative("The document reports evidence incompatible with the candidate."),
    )
    assert result["status"] == PASS, result["reason_codes"]


def test_unverifiable_confirmed_narrative_is_rejected():
    dossier = _dossier(_support("UNVERIFIABLE"))
    result = verify_narrative(
        dossier,
        build_narrator_input(dossier),
        _narrative("The candidate is confirmed."),
    )
    assert result["status"] == FAIL


def test_unverifiable_uncertain_narrative_passes():
    dossier = _dossier(_support("UNVERIFIABLE"))
    result = verify_narrative(
        dossier,
        build_narrator_input(dossier),
        _narrative("The available material is insufficient to verify the candidate."),
    )
    assert result["status"] == PASS, result["reason_codes"]
