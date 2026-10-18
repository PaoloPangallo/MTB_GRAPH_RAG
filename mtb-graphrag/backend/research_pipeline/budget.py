"""Shared provider invocation budget, with explicit fixed or workload-sized bounds."""

from __future__ import annotations

from typing import Any
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import json
import time

_ACTIVE = ContextVar('research_transport_budget', default=None)


def active_budget():
    return _ACTIVE.get()


def run_budget_context(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        from .retrieval.document_plan import focused_enabled
        budget = kwargs.get('budget')
        if focused_enabled() and isinstance(budget, CallBudget):
            with budget.activate():
                return function(*args, **kwargs)
        return function(*args, **kwargs)
    return wrapped

MAX_REAL_CALLS_TOTAL = 20


class CallBudgetExceeded(RuntimeError):
    """A provider cannot start another call within the run's fixed budget."""


class CallBudget:
    def __init__(
        self, maximum: int = MAX_REAL_CALLS_TOTAL, *, workload_sized: bool = False,
        maximum_estimated_tokens: int | None = None,
    ):
        self.maximum = maximum
        self.workload_sized = workload_sized
        self.used = 0
        self.calls: list[dict[str, Any]] = []
        if maximum_estimated_tokens is not None and (type(maximum_estimated_tokens) is not int or maximum_estimated_tokens < 1):
            raise ValueError('Estimated token budget must be positive')
        self.maximum_estimated_tokens = maximum_estimated_tokens
        self.transport_attempts: list[dict[str, Any]] = []
        self.maximum_encoding_windows: int | None = None
        self.maximum_encoding_seconds: float | None = None
        self.encoding_windows = 0
        self.encoding_seconds = 0.0

    @contextmanager
    def activate(self):
        token = _ACTIVE.set(self)
        try:
            yield self
        finally:
            _ACTIVE.reset(token)

    def before_transport(self, payload: dict) -> None:
        if len(self.transport_attempts) >= self.maximum:
            raise CallBudgetExceeded('CALL_BUDGET_EXCEEDED: physical transport attempts, including retry/narrator')
        input_fields = {key: payload[key] for key in ('messages', 'tools', 'tool_choice', 'response_format') if key in payload}
        estimated = (len(json.dumps(input_fields, ensure_ascii=False)) + 3) // 4
        reserved = estimated + int(payload.get('max_tokens') or 0)
        if self.maximum_estimated_tokens is not None and sum(a['estimated_reservation'] for a in self.transport_attempts) + reserved > self.maximum_estimated_tokens:
            raise CallBudgetExceeded('CALL_BUDGET_EXCEEDED: estimated tokens, not a billing guarantee')
        self.transport_attempts.append({'estimated_reservation': reserved, 'input_tokens': None, 'output_tokens': None})

    def record_transport_usage(self, response: dict) -> None:
        if not self.transport_attempts:
            return
        usage = response.get('usage') if isinstance(response, dict) else None
        usage = usage if isinstance(usage, dict) else {}
        attempt = self.transport_attempts[-1]
        for public, source in (('input_tokens', 'prompt_tokens'), ('output_tokens', 'completion_tokens')):
            value = usage.get(source)
            attempt[public] = value if type(value) is int and value >= 0 else None

    def transport_snapshot(self) -> dict:
        complete = all(a['input_tokens'] is not None and a['output_tokens'] is not None for a in self.transport_attempts)
        return {'version': 'physical-provider-budget/1.0', 'physical_calls': len(self.transport_attempts),
                'maximum_calls': self.maximum, 'usage_complete': complete,
                'observed_input_tokens': sum(a['input_tokens'] or 0 for a in self.transport_attempts) if complete else None,
                'observed_output_tokens': sum(a['output_tokens'] or 0 for a in self.transport_attempts) if complete else None,
                'estimated_tokens_reserved': sum(a['estimated_reservation'] for a in self.transport_attempts),
                'maximum_estimated_tokens': self.maximum_estimated_tokens,
                'token_estimation': 'CHARS_DIV_4_PLUS_MAX_OUTPUT_NOT_VERIFIED_TOKENIZER',
                'encoding_windows_started': self.encoding_windows, 'encoding_seconds': self.encoding_seconds,
                'maximum_encoding_windows': self.maximum_encoding_windows,
                'maximum_encoding_seconds': self.maximum_encoding_seconds}

    @contextmanager
    def encoding_batch(self, windows: int):
        if self.maximum_encoding_windows is not None and self.encoding_windows + windows > self.maximum_encoding_windows:
            raise CallBudgetExceeded('ENCODING_WINDOW_BUDGET_EXCEEDED')
        if self.maximum_encoding_seconds is not None and self.encoding_seconds >= self.maximum_encoding_seconds:
            raise CallBudgetExceeded('ENCODING_TIME_BUDGET_EXCEEDED')
        self.encoding_windows += windows
        started = time.monotonic()
        try:
            yield
        finally:
            self.encoding_seconds += time.monotonic() - started

    def plan_remaining_calls(self, remaining: int) -> None:
        """Provision a finite workload bound; explicit fixed budgets never grow."""
        if type(remaining) is not int or remaining < 0:
            raise ValueError("remaining calls must be a nonnegative integer")
        if self.workload_sized:
            self.maximum = max(self.maximum, self.used + remaining)

    def spend(self, kind: str, case_id: str) -> None:
        if self.used >= self.maximum:
            raise CallBudgetExceeded(
                f"CALL_BUDGET_EXCEEDED: attempted {kind} for {case_id} at used={self.used}/{self.maximum}"
            )
        self.used += 1
        self.calls.append({"kind": kind, "case_id": case_id, "sequence": self.used})
