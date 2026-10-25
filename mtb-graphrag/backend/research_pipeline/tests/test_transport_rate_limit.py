"""Bounded infrastructure retries for rate limiting, never semantic retries."""
from unittest.mock import Mock, patch
import threading
import time

import pytest

from backend.research_pipeline.enrichment import transport


@pytest.mark.parametrize("diagnostics", [False, True])
def test_rate_limit_is_not_retried_for_the_same_request(diagnostics):
    transport._reset_rate_limit_state()
    response = Mock(status_code=429, headers={"Retry-After": "2"})
    response.json.return_value = {"error": "rate limit"}
    function = transport.post_with_infra_retry_with_diagnostics if diagnostics else transport.post_with_infra_retry
    with patch.object(transport.requests, "post", return_value=response) as post, patch.object(transport.time, "sleep") as sleep:
        result = function({"messages": []})
    assert post.call_count == 1
    sleep.assert_not_called()
    assert result[0] == 429 and result[3] == 0


def test_rate_limit_cooldown_applies_to_the_next_independent_request():
    transport._reset_rate_limit_state()
    response = Mock(status_code=200, headers={})
    response.json.return_value = {"choices": []}
    fake_clock = [10.0]
    slept = []
    def advance(seconds):
        slept.append(seconds)
        fake_clock[0] += seconds
    with patch.object(transport.time, "monotonic", side_effect=lambda: fake_clock[0]), \
            patch.object(transport.time, "sleep", side_effect=advance), \
            patch.object(transport.requests, "post", return_value=response) as post:
        transport._record_rate_limit(2.0)
        result = transport.post_with_infra_retry({"messages": []})
    assert slept == [2.0]
    post.assert_called_once()
    assert result[0] == 200
    transport._reset_rate_limit_state()


def test_concurrent_waiters_recheck_a_cooldown_extended_by_a_later_429():
    transport._reset_rate_limit_state()
    transport._record_rate_limit(0.04)
    started = time.monotonic()
    observed = []
    barrier = threading.Barrier(4)

    def waiter():
        barrier.wait()
        transport._wait_for_rate_limit()
        observed.append(time.monotonic())

    threads = [threading.Thread(target=waiter) for _ in range(3)]
    for thread in threads:
        thread.start()
    barrier.wait()
    time.sleep(0.01)
    transport._record_rate_limit(0.15)
    with transport._RATE_LIMIT_LOCK:
        extended_deadline = transport._RATE_LIMIT_UNTIL
    for thread in threads:
        thread.join(timeout=2)

    assert len(observed) == 3
    assert min(observed) >= extended_deadline - 0.01
    assert max(observed) - min(observed) >= transport.RATE_LIMIT_SPACING_SECONDS - 0.01
    assert min(observed) - started >= 0.14
    transport._reset_rate_limit_state()


def test_long_retry_after_is_not_ignored_or_slept_through():
    transport._reset_rate_limit_state()
    response = Mock(status_code=429, headers={"Retry-After": "3600"})
    response.json.return_value = {}
    with patch.object(transport.requests, "post", return_value=response) as post, patch.object(transport.time, "sleep") as sleep:
        result = transport.post_with_infra_retry({})
    assert post.call_count == 1
    sleep.assert_not_called()
    assert result[0] == 429
    transport._reset_rate_limit_state()
