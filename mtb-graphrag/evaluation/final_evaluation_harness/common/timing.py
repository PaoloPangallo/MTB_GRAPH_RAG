"""Transparent monotonic timing instrumentation."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


def timed_call(function: Callable[..., Any], *args: Any, **kwargs: Any) -> tuple[Any, float]:
    start = time.monotonic()
    result = function(*args, **kwargs)
    return result, (time.monotonic() - start) * 1000.0
