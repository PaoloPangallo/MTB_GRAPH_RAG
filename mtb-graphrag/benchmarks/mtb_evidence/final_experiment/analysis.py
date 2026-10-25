"""Deterministic exploratory statistics frozen before gold access."""

from __future__ import annotations

import random
import statistics
from typing import Sequence

SCHEMA_VERSION = "mtb-final-experiment-analysis/1.0"
BASE_COMMIT = "84bcecaafdee60206799fd0a245cb78f816b257e"
CORPUS_VERSION = "qualified_claim_repository/1.4"
CORPUS_HASH = "31636f26c44bee03b16ed7d7c5e9b9580292f750e04b80e4effbaf9618ec39fa"
GATE_VERSION = "qualified_claim_structural_gate/1.3"
RETRIEVER_VERSION = "qualified_claim_retriever/1.0"
GENERATOR_VERSION = "final_experiment_generator/1.0"
CONTENT_SHA256 = "8398740590b9f7a40e02576fb890563e162f0ca594b055668ab7249d2a254779"


def paired_differences(left: Sequence[float], right: Sequence[float]) -> list[float]:
    if len(left) != len(right):
        raise ValueError("paired samples must have equal length")
    return [float(a - b) for a, b in zip(left, right, strict=True)]


def bootstrap_interval(
    values: Sequence[float], *, confidence: float = 0.95,
    samples: int = 10_000, seed: int = 20260731,
) -> tuple[float, float]:
    if not values:
        raise ValueError("bootstrap sample cannot be empty")
    if not 0 < confidence < 1 or samples < 2:
        raise ValueError("invalid bootstrap configuration")
    rng = random.Random(seed)
    vector = tuple(float(value) for value in values)
    means = sorted(
        statistics.fmean(rng.choice(vector) for _ in vector)
        for _ in range(samples)
    )
    alpha = (1.0 - confidence) / 2.0
    lo = max(0, min(samples - 1, int(alpha * samples)))
    hi = max(0, min(samples - 1, int((1.0 - alpha) * samples) - 1))
    return means[lo], means[hi]


def paired_effect_size(
    left: Sequence[float], right: Sequence[float]
) -> dict[str, float | None]:
    """Raw paired mean difference and paired standardized mean difference."""
    differences = paired_differences(left, right)
    if not differences:
        raise ValueError("paired sample cannot be empty")
    raw = statistics.fmean(differences)
    sd = statistics.stdev(differences) if len(differences) > 1 else 0.0
    return {
        "mean_difference": raw,
        "standardized_mean_difference": raw / sd if sd else None,
    }


def classify_failure(
    *, infrastructure_error: bool = False, timeout: bool = False,
    schema_valid: bool = True, candidates_generated: bool = True,
    retrieval_complete: bool = True, qualification_complete: bool = True,
    ranking_complete: bool = True, rendering_complete: bool = True,
) -> str | None:
    """Classify at the earliest predeclared failing stage."""
    if infrastructure_error:
        return "infrastructure"
    if timeout:
        return "timeout"
    if not schema_valid:
        return "schema"
    if not candidates_generated:
        return "candidate_generation"
    if not retrieval_complete:
        return "retrieval"
    if not qualification_complete:
        return "qualification"
    if not ranking_complete:
        return "ranking"
    if not rendering_complete:
        return "llm_rendering"
    return None

def agentic_summary(values: Sequence[float]) -> dict[str, float | int]:
    if not values:
        raise ValueError("agentic sample cannot be empty")
    vector = [float(value) for value in values]
    return {
        "n": len(vector), "mean": statistics.fmean(vector),
        "sd": statistics.stdev(vector) if len(vector) > 1 else 0.0,
        "min": min(vector), "max": max(vector),
    }
