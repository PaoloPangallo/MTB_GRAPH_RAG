"""Pure Protocol 1.2 statistics; no execution or result fabrication."""

from __future__ import annotations

import math
import random
from typing import Iterable, Sequence


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float] | None:
    if total == 0:
        return None
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


def paired_percentile_bootstrap(differences: Sequence[float], samples: int = 10000, seed: int = 20260809) -> tuple[float, float] | None:
    if not differences:
        return None
    rng = random.Random(seed)
    values = list(differences)
    means = [sum(rng.choice(values) for _ in values) / len(values) for _ in range(samples)]
    means.sort()
    return means[int(0.025 * (samples - 1))], means[int(0.975 * (samples - 1))]


def ranking_metrics(top_ids: Sequence[str], direct_ids: Iterable[str], k: int = 5) -> dict[str, float | int]:
    direct = set(direct_ids)
    top = list(top_ids[:k])
    hits = [idx + 1 for idx, item in enumerate(top) if item in direct]
    first = hits[0] if hits else None
    return {
        f"HitRate@{k}": int(bool(hits)),
        f"Recall@{k}": len(set(top) & direct) / len(direct) if direct else 0.0,
        f"Precision@{k}": len(set(top) & direct) / k,
        "MRR": 1 / first if first else 0.0,
        "MeanFirstRelevantRank": first if first else 0.0,
        "N_hits": int(bool(hits)),
        f"FullCoverage@{k}": int(bool(direct) and direct.issubset(set(top))),
    }
