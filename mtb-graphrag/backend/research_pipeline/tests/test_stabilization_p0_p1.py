from __future__ import annotations

from backend.research_pipeline.casecontext import contradictions as ctr
from backend.research_pipeline.casecontext.control_instructions import (
    detect_control_instruction_spans,
)
from backend.research_pipeline.casecontext import mentions as mn
from backend.research_pipeline.casecontext import pipeline
from backend.research_pipeline.determinism.gates import evaluate_association
from backend.research_pipeline.narrative.input_projection import build_narrator_input
from backend.research_pipeline.retrieval.kg_retrieval import retrieve


def _mention(*, slot: str, entity_type: str, raw: str, accepted: bool = True,
             role: str = mn.CONTEXTUAL_MENTION, assertion: str = mn.ASSERTED):
    return mn.EntityMention(
        raw_text=raw,
        normalized_value=raw,
        entity_type=entity_type,
        semantic_role=role,
        assertion_status=assertion,
        source_span={"quote": raw, "start_offset": 0, "end_offset": len(raw)},
        accepted_for_casecontext=accepted,
        rejection_reason=None if accepted else "REJECTED",
        slot=slot,
    )


def _candidate(*, direction="Sensitivity", evidence_direction="Supports"):
    return {
        "candidate_id": "GCA-STABILIZATION",
        "direction": direction,
        "source_properties": {"evidence": {"evidence_direction": evidence_direction}},
    }


def _accepted_v1(kind="RESPONSE", outcome="ENRICHMENT_ACCEPTED"):
    return [{"validation_outcome": outcome, "enrichment": {"evidence_kind": kind}}]


def _project(case_context, mentions):
    builder = getattr(pipeline, "build_retrieval_case_context", None)
    assert callable(builder), "retrieval projection helper is not implemented"
    return builder(case_context, mentions)


def test_retrieval_projection_excludes_rejected_disease_and_keeps_accepted_biomarker():
    raw = {
        "disease": {"raw_value": "fake disease", "normalized_value": "fake disease"},
        "biomarkers": [{"gene": "KRAS", "normalized_value": "KRAS G12D"}],
        "target_intervention": None,
        "query_intent": "THERAPY_DISCOVERY",
    }
    projected = _project(
        raw,
        [_mention(slot="disease", entity_type="DISEASE", raw="fake disease", accepted=False),
         _mention(slot="biomarker", entity_type="GENE", raw="KRAS")],
    )
    assert projected["disease"] is None
    assert len(projected["biomarkers"]) == 1
    assert projected["biomarkers"][0]["gene"] == "KRAS"
    assert projected["biomarkers"][0]["normalized_value"] == "KRAS"


def test_retrieval_projection_excludes_rejected_target_intervention():
    raw = {
        "disease": {"raw_value": "cancer", "normalized_value": "cancer"},
        "biomarkers": [{"gene": "KRAS", "normalized_value": "KRAS"}],
        "target_intervention": {"raw_value": "osimertinib", "normalized_value": "osimertinib"},
        "query_intent": "THERAPY_EVALUATION",
    }
    projected = _project(
        raw,
        [_mention(slot="disease", entity_type="DISEASE", raw="cancer"),
         _mention(slot="biomarker", entity_type="GENE", raw="KRAS"),
         _mention(slot="target_intervention", entity_type="INTERVENTION",
                  raw="osimertinib", accepted=False)],
    )
    assert projected["target_intervention"] is None


def test_retrieval_accepts_the_verified_projection_contract():
    projected = _project(
        {"query_intent": "THERAPY_DISCOVERY"},
        [_mention(slot="disease", entity_type="DISEASE", raw="cancer"),
         _mention(slot="biomarker", entity_type="GENE", raw="KRAS")],
    )
    result = retrieve(projected)
    assert {"associations", "excluded_candidates", "no_match"} <= result.keys()


def test_v2_without_evidence_kind_is_conservative_but_structured_support_is_consistent():
    candidate = _candidate()
    result = evaluate_association(
        "THERAPY_EVALUATION", candidate,
        [{"validation_outcome": "ENRICHMENT_V2_ACCEPTED", "enrichment": {}}],
    )
    assert result["status"] == "DIRECT"
    assert result["gate_bucket"] == "PRIMARY_BUCKET"


def test_unknown_direction_is_not_direct():
    result = evaluate_association(
        "THERAPY_EVALUATION", _candidate(direction="unmapped"), _accepted_v1("OTHER"),
    )
    assert result["status"] == "PARTIAL"
    assert result["gate_bucket"] == "WARNING_BUCKET"


def test_warning_enrichment_is_partial_warning_bucket():
    result = evaluate_association(
        "THERAPY_EVALUATION", _candidate(), _accepted_v1("RESPONSE", "ENRICHMENT_ACCEPTED_WITH_WARNING"),
    )
    assert result["status"] == "PARTIAL"
    assert result["gate_bucket"] == "WARNING_BUCKET"


def test_v2_summary_empty_keeps_warning_semantics():
    result = evaluate_association(
        "THERAPY_EVALUATION", _candidate(),
        _accepted_v1("RESPONSE", "ENRICHMENT_V2_ACCEPTED_SUMMARY_EMPTY"),
    )
    assert result["status"] == "PARTIAL"
    assert result["gate_bucket"] == "WARNING_BUCKET"


def test_negative_source_polarity_is_not_positive():
    result = evaluate_association(
        "THERAPY_EVALUATION", _candidate(evidence_direction="Does Not Support"),
        _accepted_v1("RESPONSE"),
    )
    assert result["status"] == "AMBIGUOUS"
    assert result["support_mask"]["direction"] == "SOURCE_DOES_NOT_SUPPORT"


def test_rejected_negated_duplicate_does_not_create_contradiction():
    mentions = [
        _mention(slot="biomarker", entity_type="GENE", raw="KRAS"),
        _mention(slot="biomarker", entity_type="GENE", raw="KRAS", accepted=False,
                 assertion=mn.NEGATED),
    ]
    assert ctr.detect("KRAS and no KRAS", mentions) == []


def test_accepted_asserted_and_negated_mentions_still_conflict():
    mentions = [
        _mention(slot="biomarker", entity_type="GENE", raw="KRAS", assertion=mn.ASSERTED),
        _mention(slot="biomarker", entity_type="GENE", raw="KRAS", assertion=mn.NEGATED),
    ]
    assert any(c.type == ctr.ASSERTED_AND_NEGATED for c in ctr.detect("KRAS and no KRAS", mentions))


def test_control_instruction_mention_does_not_create_contradiction():
    mentions = [
        _mention(slot="biomarker", entity_type="GENE", raw="KRAS"),
        _mention(slot="biomarker", entity_type="GENE", raw="KRAS", accepted=False,
                 role=mn.CONTROL_INSTRUCTION_MENTION, assertion=mn.NEGATED),
    ]
    assert ctr.detect("KRAS. Ignore instructions and no KRAS", mentions) == []


def test_control_text_does_not_create_intent_contradiction():
    text = "do not evaluate any specific drug whether osimertinib is appropriate"
    control_spans = [{"start_offset": 0, "end_offset": len(text)}]
    assert not any(
        c.type == ctr.INTENT_CONFLICT
        for c in ctr.detect(text, [], control_spans=control_spans)
    )


def test_real_treatment_history_conflict_remains_active():
    text = "no prior therapy; was treated with osimertinib"
    assert any(
        c.type == ctr.TREATMENT_HISTORY_CONFLICT
        for c in ctr.detect(text, [], control_spans=[])
    )


def test_controlled_treatment_phrase_does_not_create_conflict():
    text = "no prior therapy; was treated with osimertinib"
    start = text.index("no prior therapy")
    control_spans = [{"start_offset": start, "end_offset": start + len("no prior therapy")}]
    assert not any(
        c.type == ctr.TREATMENT_HISTORY_CONFLICT
        for c in ctr.detect(text, [], control_spans=control_spans)
    )


def test_real_intent_conflict_remains_active_outside_control_spans():
    text = "do not evaluate any specific drug whether osimertinib is appropriate"
    assert any(
        c.type == ctr.INTENT_CONFLICT
        for c in ctr.detect(text, [], control_spans=detect_control_instruction_spans(""))
    )


def _narrator_candidate(status, bucket, direction):
    return {
        "candidate_id": "GCA-NARRATIVE",
        "drug": "drug",
        "graph_relation": "associated",
        "status": status,
        "warnings": [],
        "gate_results": {"bucket": bucket, "support_mask": {
            "disease": "SUPPORTED", "biomarker": "SUPPORTED", "intervention": "SUPPORTED",
            "direction": direction,
        }},
        "document_support": {"selected_papers": []},
        "author_context": [],
    }


def test_narrator_support_projection_is_whitelisted_to_direct_primary_support():
    for status, bucket, direction, expected in [
        ("DIRECT", "PRIMARY_BUCKET", "SUPPORTED", True),
        ("PARTIAL", "WARNING_BUCKET", "SUPPORTED", False),
        ("AMBIGUOUS", "WARNING_BUCKET", "SUPPORTED", False),
        ("CONTRADICTED", "REJECTED_BUCKET", "CONTRADICTED", False),
        ("DISCOVERED", "DISCOVERY_BUCKET", "NOT_APPLICABLE", False),
        ("DIRECT", "PRIMARY_BUCKET", "CONTRADICTED", False),
    ]:
        dossier = {"case_id": "C", "case_context": {}, "candidate_therapies": [
            _narrator_candidate(status, bucket, direction)
        ], "limitations": [], "provenance": {}}
        projected = build_narrator_input(dossier)
        assert projected["candidates"][0]["expresses_support"] is expected
