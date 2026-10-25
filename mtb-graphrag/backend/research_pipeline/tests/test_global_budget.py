import pytest
from backend.research_pipeline.budget import CallBudget, CallBudgetExceeded, active_budget


def test_transport_budget_includes_retry_and_narrator():
    budget = CallBudget(2)
    payload = {'messages': [{'role': 'user', 'content': 'hello'}], 'max_tokens': 10}
    with budget.activate():
        assert active_budget() is budget
        budget.before_transport(payload)
        budget.before_transport(payload)
        with pytest.raises(CallBudgetExceeded):
            budget.before_transport(payload)
    assert active_budget() is None
    assert budget.transport_snapshot()['physical_calls'] == 2


def test_unknown_usage_is_not_reported_as_zero():
    budget = CallBudget(2)
    budget.before_transport({'messages': [], 'max_tokens': 10})
    assert budget.transport_snapshot()['usage_complete'] is False
    budget.record_transport_usage({'usage': {'prompt_tokens': 12, 'completion_tokens': 3}})
    assert budget.transport_snapshot()['observed_input_tokens'] == 12
    assert budget.transport_snapshot()['usage_complete'] is True


def test_estimated_token_cap_refuses_before_call():
    budget = CallBudget(2, maximum_estimated_tokens=5)
    with pytest.raises(CallBudgetExceeded):
        budget.before_transport({'messages': [], 'max_tokens': 10})
    assert budget.transport_snapshot()['physical_calls'] == 0


def test_tool_schemas_are_part_of_input_reservation():
    first, second = CallBudget(2), CallBudget(2)
    first.before_transport({'messages': [], 'tools': []})
    second.before_transport({'messages': [], 'tools': [{'description': 'x' * 1000}]})
    assert second.transport_snapshot()['estimated_tokens_reserved'] > first.transport_snapshot()['estimated_tokens_reserved'] + 200
