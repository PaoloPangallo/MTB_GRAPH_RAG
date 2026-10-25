"""Budget regressions: execute all retrieved candidates, without network calls."""
from unittest.mock import Mock, patch

import pytest

from backend.pipeline.agentic.ledger import EventLedger
from backend.research_pipeline.casecontext.parser import adapt_case_context
from backend.research_pipeline import orchestrator, run_store
from backend.research_pipeline.enrichment.validator_v3 import validate_enrichment_v3
from backend.research_pipeline.pipeline import CallBudget
from backend.research_pipeline.tests.test_semantic_admission_contract import assessment
from backend.research_pipeline.tests.test_orchestrated_pre_freeze_matrix import (
    ControlledDocumentRuntime, _paper_candidate, _parser_output,
    _reader_observation, _source_unit,
)


@pytest.mark.parametrize("configured", [None, "", "  "])
def test_default_runtime_budget_sizes_to_workload(monkeypatch, configured):
    if configured is None:
        monkeypatch.delenv("RESEARCH_PIPELINE_MAX_LLM_CALLS_PER_RUN", raising=False)
    else:
        monkeypatch.setenv("RESEARCH_PIPELINE_MAX_LLM_CALLS_PER_RUN", configured)
    budget = run_store.new_run_budget()
    budget.plan_remaining_calls(50)
    assert budget.maximum == 50
    assert budget.workload_sized is True


def test_explicit_limit_stays_a_hard_limit(monkeypatch):
    monkeypatch.setenv("RESEARCH_PIPELINE_MAX_LLM_CALLS_PER_RUN", "7")
    budget = run_store.new_run_budget()
    budget.plan_remaining_calls(50)
    assert budget.maximum == 7
    assert budget.workload_sized is False


@pytest.mark.parametrize("document_cap", [2, None])
@pytest.mark.parametrize("with_narrator", [False, True, 'transport_batches'])
def test_discovery_verifies_every_candidate_beyond_pilot_budget(document_cap, with_narrator, physical_retries=False):
    raw = "lung cancer with EGFR L858R; discover associated therapies."
    parsed = _parser_output(raw, interventions=())
    parsed["query_intent"] = "THERAPY_DISCOVERY"
    context = adapt_case_context("budget-discovery", parsed, raw)
    candidates = {
        str(index): _paper_candidate(str(index), relation_family="EVIDENCE_DRUG",
                                    semantic_key=f"Evidence:{index}",
                                    document_identifiers=[{"pmid": str(pmid)} for pmid in
                                                         (12345678, 12345679, 12345680)])
        for index in range(12)
    }
    text = "EGFR L858R showed sensitivity to erlotinib in lung cancer."
    reader_ids, semantic_ids = [], []

    def structured_attempts(budget):
        from backend.research_pipeline.enrichment import transport
        responses = [Mock(status_code=status, json=Mock(return_value={'valid': valid}))
                     for status, valid in [(500, False), (200, False), (500, False), (200, True)]]
        endpoint = Mock(url='https://controlled.invalid', timeout_seconds=1)
        with budget.activate(), patch.object(transport, 'endpoint', return_value=endpoint), \
             patch.object(transport.requests, 'post', side_effect=responses) as post, \
             patch.object(transport.llm_config, 'api_key', return_value='controlled'), \
             patch.object(transport.time, 'sleep'):
            _, telemetry = transport.post_with_format_retry({'messages': []},
                lambda status, body, error: 'VALID' if body.get('valid') else 'INVALID_TOOL_ARGUMENTS')
        assert post.call_count == telemetry['model_call_count'] == 4

    def parser(budget, case_id, _text):
        budget.spend("casecontext_parser", case_id)
        return {"transport_result": "FORCED_TOOL_VALID", "case_context_raw": context,
                "model": "controlled", "prompt_version": "controlled"}

    def reader(budget, case_id, candidate_id, _doc, _context, candidate, _drug, units):
        budget.spend("paper_context_enricher_v3", case_id)
        if physical_retries:
            structured_attempts(budget)
        reader_ids.append(candidate_id)
        result = _reader_observation(candidate, units)
        if physical_retries:
            result['model_call_count'] = 4
        return result

    def semantic(budget, case_id, target, _gep):
        budget.spend("semantic_alignment_verifier", case_id)
        if physical_retries:
            structured_attempts(budget)
        semantic_ids.append(target["candidate_id"])
        return assessment(text)

    budget = CallBudget(20, workload_sized=True)
    def narrator(case_id, _input):
        if with_narrator == 'transport_batches':
            budget.before_transport({'messages': [], 'max_tokens': 1})
            budget.before_transport({'messages': [], 'max_tokens': 1})
        else:
            budget.spend('dossier_narrator', case_id)
        return {'transport_result': 'NARRATION_FAILED'}
    ledger = Mock(spec=EventLedger)
    units = [_source_unit(text, document_id=f"pmid:{pmid}", unit_id=f"SU-{pmid}")
             for pmid in (12345678, 12345679, 12345680)]
    with (
        patch("backend.research_pipeline.retrieval.kg_retrieval.load_candidates", return_value=candidates),
        patch("backend.research_pipeline.orchestrator.MAX_PAPERS_PER_ASSOCIATION", document_cap),
        patch("backend.research_pipeline.retrieval.live_sourceunit_selection.MAX_PAPERS_PER_ASSOCIATION", document_cap),
    ):
        run = orchestrator.run_case(
            case_id="budget-discovery", clinical_text=raw, call_parser_fn=parser,
            call_enricher_fn=reader, call_semantic_alignment_fn=semantic,
            source_units_by_id={}, budget=budget, ledger=ledger,
            document_runtime=ControlledDocumentRuntime(units),
            validate_fn=validate_enrichment_v3,
            call_narrator_fn=narrator if with_narrator else None,
        )
    assert run.status in {"COMPLETED", "PARTIAL"}, run.stopped_at
    assert set(reader_ids) == set(candidates)
    assert set(semantic_ids) == set(candidates)
    expected_documents = 3 if document_cap is None else 2
    base_calls = 1 + len(candidates) * expected_documents * 2
    expected_calls = base_calls + (2 if with_narrator == 'transport_batches' else int(with_narrator))
    assert len(reader_ids) == len(semantic_ids) == len(candidates) * expected_documents
    assert run.llm_calls == (len(budget.transport_attempts) if physical_retries else expected_calls)
    assert budget.used == (base_calls if with_narrator == 'transport_batches' else expected_calls)
    assert len(run.relation_aware_report["paper_evidence"]) == len(candidates)
    assert all(row["support_level"] == "FULL_SUPPORT"
               for row in run.relation_aware_report["paper_evidence"])
    retrieval = next(s for s in run.stages if s.stage_id == "stage_5_kg_retrieval")
    assert retrieval.output_preview["call_budget"]["maximum"] == 1 + (base_calls - 1) * 4 + int(bool(with_narrator))
    assert retrieval.output_preview['call_budget']['narrator_included'] is bool(with_narrator)
    assert retrieval.output_preview['call_budget']['initial_narrator_call_reservation'] == int(bool(with_narrator))
    progress = [call.args[3] for call in ledger.append.call_args_list
                if call.args[1] == "PIPELINE_WORK_PROGRESS"]
    assert {"READER", "VERIFICATION", "CANDIDATE_COMPLETED"}.issubset({p["phase"] for p in progress})
    assert progress[-1]["completed_candidates"] == progress[-1]["total_candidates"] == len(candidates)
    assert progress[-1]["reader_calls"] == len(reader_ids) * (4 if physical_retries else 1)


def test_workload_covers_all_bounded_format_and_infra_attempts():
    test_discovery_verifies_every_candidate_beyond_pilot_budget(2, False, physical_retries=True)


@pytest.mark.parametrize("remaining", [-1, 1.5])
def test_invalid_workload_is_rejected(remaining):
    with pytest.raises(ValueError):
        CallBudget(20, workload_sized=True).plan_remaining_calls(remaining)
