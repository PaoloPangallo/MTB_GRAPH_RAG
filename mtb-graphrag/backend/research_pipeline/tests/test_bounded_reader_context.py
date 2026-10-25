"""Context expansion is bounded, provenance preserving and explicitly enabled."""
from types import SimpleNamespace

import pytest

from backend.research_pipeline.budget import CallBudget


def inputs():
    units = [{"source_unit_id": f"SU-{i}", "document_id": "pmid:1", "text": f"passage {i}"}
             for i in range(4)]
    paper = {"document_id": "pmid:1", "resolved_source_unit_ids": ["SU-0"], "bundle_id": "bundle"}
    return paper, units


def _braf_jats_units():
    from backend.research_pipeline.documents.parsers import JatsXmlParser

    xml = """<article><body><sec><title>Context</title><p>For patients with metastatic papillary thyroid carcinoma (PTC) refractory to radioactive iodine (RAI) treatment, systemic chemotherapy has limited efficacy. Such tumors frequently harbor BRAF V600E, and this alteration may predict responsiveness to vemurafenib treatment.</p></sec></body></article>"""
    return [unit.to_dict() for unit in JatsXmlParser().parse("pmcid:PMC4067722", xml)]


def test_braf_context_is_adjacent_but_never_becomes_citable():
    from backend.research_pipeline.enrichment.context_reader import (
        ContextPolicy, read_with_context_policy,
    )
    from backend.research_pipeline.enrichment.enricher_v3 import build_reader_payload
    from backend.research_pipeline.enrichment.validator_v3 import validate_enrichment_v3

    units = _braf_jats_units()
    cited = next(unit for unit in units if unit.get("unit_type") == "FULLTEXT_SENTENCE"
                 and unit.get("sentence_index") == 1)
    prior = next(unit for unit in units if unit.get("unit_type") == "FULLTEXT_SENTENCE"
                 and unit.get("sentence_index") == 0)
    paper = {"candidate_id": "GCA-BRAF", "document_id": "pmcid:PMC4067722",
             "resolved_source_unit_ids": [cited["source_unit_id"]]}
    observed_units = []

    def reader(_budget, _case_id, _candidate_id, _paper_id, _case_context,
               _candidate, _drug, source_units):
        observed_units.extend(source_units)
        return {"transport_result": "V3_TRANSPORT_VALID", "enrichment": {
            "decision": "QUOTE", "source_unit_id": cited["source_unit_id"],
            "quote": cited["text"]}}

    result = read_with_context_policy(
        reader, CallBudget(1), "braf", {}, {"candidate_id": "GCA-BRAF"},
        "vemurafenib", paper, [cited], units,
        ContextPolicy(adjacent_context_enabled=True),
    )

    assert result.paper["resolved_source_unit_ids"] == [cited["source_unit_id"]]
    assert prior["source_unit_id"] not in result.paper["resolved_source_unit_ids"]
    assert [unit["source_unit_id"] for unit in observed_units] == [
        cited["source_unit_id"], prior["source_unit_id"]
    ]
    assert observed_units[0]["reader_role"] == "EVIDENCE"
    assert observed_units[1]["reader_role"] == "CONTEXT"
    payload = build_reader_payload({}, {"candidate_id": "GCA-BRAF"},
                                   "pmcid:PMC4067722", observed_units)
    request = payload["messages"][1]["content"]
    assert cited["source_unit_id"] in request
    assert prior["source_unit_id"] in request
    assert "context_source_units" in request
    assert "Such tumors frequently harbor BRAF V600E" in request
    assert "metastatic papillary thyroid carcinoma" in request

    valid = validate_enrichment_v3(
        "V3_TRANSPORT_VALID", {"decision": "QUOTE", "source_unit_id": cited["source_unit_id"],
                               "quote": cited["text"]},
        candidate={"candidate_id": "GCA-BRAF"}, paper_bundle=result.paper,
        source_units_by_id={unit["source_unit_id"]: unit for unit in observed_units},
    )
    invalid_context_quote = validate_enrichment_v3(
        "V3_TRANSPORT_VALID", {"decision": "QUOTE", "source_unit_id": prior["source_unit_id"],
                               "quote": prior["text"]},
        candidate={"candidate_id": "GCA-BRAF"}, paper_bundle=result.paper,
        source_units_by_id={unit["source_unit_id"]: unit for unit in observed_units},
    )
    assert valid["outcome"] == "ENRICHMENT_V3_ACCEPTED"
    assert invalid_context_quote["reason_codes"] == ["SOURCE_UNIT_NOT_IN_SELECTED_DOCUMENT"]

    without_context = []

    def no_context_reader(*args):
        without_context.extend(args[-1])
        return {"transport_result": "V3_TRANSPORT_VALID", "enrichment": {
            "decision": "QUOTE", "source_unit_id": cited["source_unit_id"],
            "quote": cited["text"]}}

    read_with_context_policy(
        no_context_reader, CallBudget(1), "braf", {}, {"candidate_id": "GCA-BRAF"},
        "vemurafenib", paper, [cited], units,
        ContextPolicy(adjacent_context_enabled=False),
    )
    assert [unit["source_unit_id"] for unit in without_context] == [cited["source_unit_id"]]
    assert without_context[0]["text"] == observed_units[0]["text"] == cited["text"]


def test_context_respects_document_and_position_boundaries_and_char_budget():
    from backend.research_pipeline.enrichment.context_reader import (
        ContextPolicy, read_with_context_policy,
    )

    selected = {"source_unit_id": "SU-T", "document_id": "doc-a",
                "unit_type": "FULLTEXT_SENTENCE", "section": "Results",
                "subsection": None, "paragraph_index": 3, "sentence_index": 1,
                "text": "Such tumors were observed."}
    adjacent = {**selected, "source_unit_id": "SU-P", "sentence_index": 0,
                "text": "Previous sentence."}
    wrong_doc = {**adjacent, "source_unit_id": "SU-X", "document_id": "doc-b"}
    wrong_para = {**adjacent, "source_unit_id": "SU-Q", "paragraph_index": 2}
    huge = {**adjacent, "source_unit_id": "SU-HUGE", "sentence_index": 2,
            "text": "x" * 100}
    seen = []

    def reader(*args):
        seen.extend(args[-1])
        return {"transport_result": "INVALID_TOOL_ARGUMENTS", "enrichment": None}

    result = read_with_context_policy(
        reader, CallBudget(1), "case", {}, {"candidate_id": "GCA-1"}, "",
        {"candidate_id": "GCA-1", "document_id": "doc-a",
         "resolved_source_unit_ids": ["SU-T"]}, [selected],
        [selected, adjacent, wrong_doc, wrong_para, huge],
        ContextPolicy(adjacent_context_enabled=True, max_context_chars=32),
    )

    assert [unit["source_unit_id"] for unit in seen] == ["SU-T", "SU-P"]
    assert all(unit["reader_role"] == "CONTEXT" for unit in seen[1:])
    assert result.paper["resolved_source_unit_ids"] == ["SU-T"]


def test_non_anaphoric_source_does_not_receive_adjacent_context():
    from backend.research_pipeline.enrichment.context_reader import (
        ContextPolicy, read_with_context_policy,
    )
    paper, units = inputs()
    seen = []

    def reader(*args):
        seen.extend(args[-1])
        return {"transport_result": "INVALID_TOOL_ARGUMENTS", "enrichment": None}

    read_with_context_policy(
        reader, CallBudget(1), "case", {}, {"candidate_id": "GCA-1"}, "",
        paper, units[:1], units,
        ContextPolicy(adjacent_context_enabled=True), selector_fn=selector,
    )
    assert [unit["source_unit_id"] for unit in seen] == ["SU-0"]


def test_context_is_linked_only_to_the_anaphoric_evidence_unit():
    from backend.research_pipeline.enrichment.context_reader import (
        ContextPolicy, read_with_context_policy,
    )
    evidence = [
        {"source_unit_id": "SU-N", "document_id": "doc", "unit_type": "FULLTEXT_SENTENCE",
         "section": "Results", "subsection": None, "paragraph_index": 0,
         "sentence_index": 0, "text": "BRAF V600E was identified."},
        {"source_unit_id": "SU-A", "document_id": "doc", "unit_type": "FULLTEXT_SENTENCE",
         "section": "Results", "subsection": None, "paragraph_index": 0,
         "sentence_index": 2, "text": "Such tumors responded to treatment."},
    ]
    previous = {**evidence[0], "source_unit_id": "SU-P", "sentence_index": 1,
                "text": "The cohort included patients with metastatic disease."}
    seen = []

    def reader(*args):
        seen.extend(args[-1])
        return {"transport_result": "INVALID_TOOL_ARGUMENTS", "enrichment": None}

    read_with_context_policy(
        reader, CallBudget(1), "case", {}, {"candidate_id": "GCA-1"}, "",
        {"candidate_id": "GCA-1", "document_id": "doc",
         "resolved_source_unit_ids": ["SU-N", "SU-A"]}, evidence,
        [evidence[0], previous, evidence[1]],
        ContextPolicy(adjacent_context_enabled=True),
    )
    context = next(unit for unit in seen if unit.get("reader_role") == "CONTEXT")
    assert context["source_unit_id"] == "SU-P"
    assert context["context_for_source_unit_ids"] == ["SU-A"]


def selector(selection, *, top_k):
    ids = tuple(unit["source_unit_id"] for unit in selection.source_units[:top_k])
    return SimpleNamespace(selected_source_unit_ids=ids, to_dict=lambda **_: {"top_k": top_k})


def test_abstention_expands_once_and_counts_every_real_call():
    from backend.research_pipeline.enrichment.context_reader import read_with_context_policy, ContextPolicy

    paper, units = inputs()
    seen = []

    def reader(budget, case_id, _candidate_id, _paper_id, _context, _candidate, _drug, shown):
        budget.spend("reader", case_id)
        seen.append([unit["source_unit_id"] for unit in shown])
        return {"transport_result": "V3_TRANSPORT_VALID", "model_call_count": 1,
                "input_tokens": len(shown), "output_tokens": 1, "latency_ms": 2,
                "enrichment": {"decision": "ABSTAIN", "abstain_reason": "NO_RELEVANT_EVIDENCE"}}

    result = read_with_context_policy(reader, CallBudget(2), "case", {}, {"candidate_id": "GCA-1"},
                                     "", paper, units[:1], units,
                                     ContextPolicy(enabled=True, initial_top_k=1, expanded_top_k=3), selector_fn=selector)
    assert seen == [["SU-0"], ["SU-0", "SU-1", "SU-2"]]
    assert result.call["model_call_count"] == 2
    assert result.call["input_tokens"] == 4
    assert result.paper["resolved_source_unit_ids"] == ["SU-0", "SU-1", "SU-2"]
    assert len(result.call["context_expansion"]["attempts"]) == 2
    assert paper["resolved_source_unit_ids"] == ["SU-0"]


@pytest.mark.parametrize("transport,decision,reason", [
    ("INVALID_TOOL_ARGUMENTS", "ABSTAIN", "NO_RELEVANT_EVIDENCE"),
    ("V3_TRANSPORT_VALID", "QUOTE", None),
    ("V3_TRANSPORT_VALID", "ABSTAIN", "COMPOSITION_UNCLEAR"),
])
def test_invalid_quote_transport_or_real_ambiguity_never_triggers_repair(transport, decision, reason):
    from backend.research_pipeline.enrichment.context_reader import read_with_context_policy, ContextPolicy

    paper, units = inputs()
    calls = []
    def reader(*args):
        calls.append(True)
        return {"transport_result": transport, "enrichment": {"decision": decision, "abstain_reason": reason}}
    read_with_context_policy(reader, CallBudget(2), "case", {}, {"candidate_id": "GCA-1"}, "",
                             paper, units[:1], units, ContextPolicy(enabled=True), selector_fn=selector)
    assert len(calls) == 1


def test_disabled_policy_and_budget_exhaustion_do_not_make_an_extra_call():
    from backend.research_pipeline.enrichment.context_reader import read_with_context_policy, ContextPolicy

    paper, units = inputs()
    for enabled in (False, True):
        budget = CallBudget(1)
        def reader(*args):
            budget.spend("reader", "case")
            return {"transport_result": "V3_TRANSPORT_VALID", "enrichment": {
                "decision": "ABSTAIN", "abstain_reason": "NO_RELEVANT_EVIDENCE"}}
        result = read_with_context_policy(reader, budget, "case", {}, {"candidate_id": "GCA-1"}, "",
                                         paper, units[:1], units, ContextPolicy(enabled=enabled), selector_fn=selector)
        assert budget.used == 1
        assert len(result.units) == 1


def test_failed_expansion_retains_both_attempts_and_observed_usage():
    from backend.research_pipeline.enrichment.context_reader import read_with_context_policy, ContextPolicy
    from backend.research_pipeline.live_providers import LiveStageFailed

    paper, units = inputs()
    budget = CallBudget(2)

    def reader(*args):
        budget.spend("reader", "case")
        if budget.used == 1:
            return {"transport_result": "V3_TRANSPORT_VALID", "model_call_count": 1,
                    "input_tokens": 5, "output_tokens": 1,
                    "enrichment": {"decision": "ABSTAIN", "abstain_reason": "NO_RELEVANT_EVIDENCE"}}
        error = LiveStageFailed("reader", "LIVE_STAGE_FAILED", "controlled failure")
        error.call_result = {"model_call_count": 1, "input_tokens": 9, "output_tokens": None}
        raise error

    with pytest.raises(LiveStageFailed) as raised:
        read_with_context_policy(reader, budget, "case", {}, {"candidate_id": "GCA-1"}, "",
                                 paper, units[:1], units, ContextPolicy(enabled=True), selector_fn=selector)
    assert raised.value.call_result["model_call_count"] == budget.used == 2
    assert raised.value.call_result["input_tokens"] == 14
    assert raised.value.call_result["output_tokens"] is None
    assert len(raised.value.call_result["context_expansion"]["attempts"]) == 2


@pytest.mark.parametrize("spent", [False, True])
def test_expansion_without_provider_response_keeps_completed_attempt(spent):
    from backend.research_pipeline.enrichment.context_reader import read_with_context_policy, ContextPolicy
    from backend.research_pipeline.live_providers import LiveStageFailed

    paper, units = inputs()
    budget = CallBudget(2)
    attempts = []

    def reader(*args):
        attempts.append(True)
        if len(attempts) == 1:
            budget.spend("reader", "case")
            return {"transport_result": "V3_TRANSPORT_VALID", "model_call_count": 1, "input_tokens": 10,
                    "enrichment": {"decision": "ABSTAIN", "abstain_reason": "NO_RELEVANT_EVIDENCE"}}
        if spent:
            budget.spend("reader", "case")
        raise LiveStageFailed("reader", "LIVE_STAGE_FAILED", "timeout")

    with pytest.raises(LiveStageFailed) as raised:
        read_with_context_policy(reader, budget, "case", {}, {"candidate_id": "GCA-1"}, "",
                                 paper, units[:1], units, ContextPolicy(enabled=True), selector_fn=selector)
    call = raised.value.call_result
    assert call["model_call_count"] == budget.used == 1 + int(spent)
    assert call["input_tokens"] is None
    assert call["context_expansion"]["attempts"][0]["input_tokens"] == 10
    assert call["context_expansion"]["expanded"] is True
