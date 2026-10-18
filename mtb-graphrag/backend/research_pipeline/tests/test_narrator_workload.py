"""Large dossiers retain complete candidate coverage in bounded model requests."""
import json
from copy import deepcopy
from unittest.mock import patch

import pytest

from backend.research_pipeline.narrative import narrator, prompt


def _input(count):
    return {
        "narrator_input_hash": "original-input", "contract_version": "test",
        "candidates": [{"candidate_id": f"C-{i}", "canonical_status": "UNVERIFIABLE",
                        "validated_quotes": [], "warnings": ["DOCUMENT_PROVENANCE_NOT_AVAILABLE"]}
                       for i in range(count)],
        "counts": {"candidates": count},
        "summary_facts": {"candidate_count": count},
        "limitations": ["DOCUMENT_PROVENANCE_NOT_AVAILABLE"],
        # UI/verification duplicates must not consume model context.
        "clinical_trials": [{"audit": "presentation-only" * 10000}],
        "paper_evidence": [], "kg_only_relations": [],
    }


@pytest.mark.parametrize("count", [1, 40, 41, 294])
def test_all_candidates_narrated_once_without_duplicate_presentation_payload(count):
    source = _input(count)
    before = deepcopy(source)
    requests = []

    def provider(payload):
        content = payload["messages"][-1]["content"]
        data = json.loads(content[content.index("{"):])
        requests.append(data)
        assert "clinical_trials" not in data
        assert data["summary_facts"]["candidate_count"] == count
        assert data["limitations"] == source["limitations"]
        assert len(data["candidates"]) <= narrator.MAX_CANDIDATES_PER_REQUEST
        args = {"narrative_summary": "Sintesi globale.", "limitations_summary": "Limiti globali.",
                "closing_note": "Nota.", "candidate_narratives": [
                    {"candidate_id": c["candidate_id"], "text": "Relazione non verificabile."}
                    for c in data["candidates"]]}
        response = {"choices": [{"finish_reason": "tool_calls", "message": {
            "tool_calls": [{"type": "function", "function": {
                "name": prompt.TOOL_NAME, "arguments": json.dumps(args)}}]}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50}}
        return 200, response, None, 0

    with patch.object(narrator.tr, "post_with_infra_retry", side_effect=provider):
        result = narrator.call_narrator("CASE", source)
    assert result["transport_result"] == "FORCED_TOOL_VALID", result
    narrative = result["narrative"]
    assert [c["candidate_id"] for c in narrative["candidate_narratives"]] == [f"C-{i}" for i in range(count)]
    assert narrative["narrative_hash"] == narrator.narrative_hash(narrative)
    assert result["narrator_input_hash"] == "original-input"
    assert result["model_call_count"] == len(requests)
    assert result["input_tokens"] == 100 * len(requests)
    assert source == before


def test_failed_later_batch_never_exposes_partial_narration():
    source = _input(81)
    success = {"transport_result": "FORCED_TOOL_VALID", "model_call_count": 1,
               "narrative": {"candidate_narratives": [{"candidate_id": "C-0", "text": "text"} ]},
               "retry_count": 0, "latency_ms": 1}
    failure = {"transport_result": "HTTP_ERROR", "narrative": None,
               "model_call_count": 1, "retry_count": 0, "latency_ms": 1}
    with patch.object(narrator, "_call_narrator_batch", side_effect=[success, failure]) as call:
        result = narrator.call_narrator("CASE", source)
    assert call.call_count == 2
    assert result["transport_result"] == "HTTP_ERROR"
    assert result["narrative"] is None
    assert result["model_call_count"] == 2


def test_malformed_batch_is_split_without_dropping_failure_accounting():
    source = _input(40)
    sizes = []

    def provider(case_id, batch, run_index):
        sizes.append(len(batch["candidates"]))
        malformed = len(batch["candidates"]) > 20
        return {"transport_result": "INVALID_TOOL_ARGUMENTS" if malformed else "FORCED_TOOL_VALID",
                "model_call_count": 1, "latency_ms": 1, "retry_count": 0,
                "attempts": [{"transport_result": "INVALID_TOOL_ARGUMENTS" if malformed else "FORCED_TOOL_VALID"}],
                "narrative": None if malformed else {"candidate_narratives": [
                    {"candidate_id": c["candidate_id"], "text": "Not verified."} for c in batch["candidates"]]}}

    with patch.object(narrator, "_call_narrator_batch", side_effect=provider):
        result = narrator.call_narrator("CASE", source)
    assert sizes == [40, 20, 20]
    assert result["model_call_count"] == 3
    assert result["transport_result"] == "FORCED_TOOL_VALID"
    assert len(result["attempts"]) == 3
    assert result["attempts"][0]["transport_result"] == "INVALID_TOOL_ARGUMENTS"
    assert [c["candidate_id"] for c in result["narrative"]["candidate_narratives"]] == [c["candidate_id"] for c in source["candidates"]]


def test_malformed_recovery_is_bounded_and_never_retries_semantic_content():
    sizes = []

    def malformed(case_id, batch, run_index):
        sizes.append(len(batch["candidates"]))
        return {"transport_result": "INVALID_TOOL_ARGUMENTS", "narrative": None, "model_call_count": 1}

    with patch.object(narrator, "_call_narrator_batch", side_effect=malformed):
        result = narrator.call_narrator("CASE", _input(40))
    assert sizes == [40, 20, 10]
    assert result["narrative"] is None
    assert result["model_call_count"] == 3
