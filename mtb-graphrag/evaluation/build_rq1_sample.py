"""Genera ``evaluation/gold/rq1_gca_manual_review.csv`` (§6).

Uso::

    python -m evaluation.build_rq1_sample

Richiede che ``python -m evaluation.run_rq1`` sia già stato eseguito: il
campione riporta i finding automatici, ma non li usa come giudizio.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

from evaluation.rq1.canonical_key import canonical_key
from evaluation.rq1.compare import load_candidates
from evaluation.rq1.sample import SAMPLE_FIELDS, build_sample

REPO_ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = (
    REPO_ROOT / "benchmarks" / "mtb_evidence" / "document_grounded_claims"
    / "graph_candidate_repository" / "2.0" / "candidates.jsonl"
)
MISMATCHES = REPO_ROOT / "evaluation" / "rq1_graph_candidate_fidelity" / "mismatches.csv"
OUT = REPO_ROOT / "evaluation" / "gold" / "rq1_gca_manual_review.csv"


def main() -> int:
    candidates = list(load_candidates(CANDIDATES))

    findings_by_candidate: dict[str, list[dict]] = defaultdict(list)
    if MISMATCHES.exists():
        with MISMATCHES.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("candidate_id"):
                    findings_by_candidate[row["candidate_id"]].append({
                        "class": row["error_class"],
                        "layer": row["layer"],
                        "field": row.get("field") or None,
                    })

    semantic_groups: dict[tuple, list[str]] = defaultdict(list)
    for candidate in candidates:
        semantic_groups[canonical_key(candidate).semantic()].append(candidate["candidate_id"])
    semantic_duplicate_ids = {
        cid for ids in semantic_groups.values() if len(ids) > 1 for cid in ids
    }

    rows = build_sample(candidates, findings_by_candidate, semantic_duplicate_ids)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SAMPLE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    strata = {}
    for row in rows:
        for stratum in row["stratum"].split("|"):
            strata[stratum] = strata.get(stratum, 0) + 1
    print(f"[rq1-sample] righe: {len(rows)} -> {OUT.relative_to(REPO_ROOT)}")
    print("[rq1-sample] strati:", json.dumps(strata, indent=1, ensure_ascii=False))
    blank = all(
        not row["reviewer_correct"] and not row["reviewer_complete"] and not row["reviewer_notes"]
        for row in rows
    )
    print(f"[rq1-sample] colonne revisore vuote: {blank}")
    return 0 if blank else 1


if __name__ == "__main__":
    sys.exit(main())
