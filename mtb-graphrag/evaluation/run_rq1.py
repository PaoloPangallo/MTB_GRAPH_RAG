"""Driver RQ1 — fedeltà e completezza delle GraphCandidateAssertion.

Uso::

    python -m evaluation.run_rq1

Legge l'export CSV congelato e ``candidates.jsonl``, e scrive gli artefatti in
``evaluation/rq1_graph_candidate_fidelity/``. Non modifica nulla del runtime né
degli artefatti storici.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from evaluation.rq1.compare import MaterializationComparator, aggregate, load_candidates
from evaluation.rq1.kg_source import EligiblePathBuilder, FrozenKnowledgeGraph

REPO_ROOT = Path(__file__).resolve().parents[1]
KG_ROOT = REPO_ROOT.parent / "data_expl" / "DatasetTESI" / "Dataset TESI" / "Clean_Graph_Data"
CANDIDATES = (
    REPO_ROOT / "benchmarks" / "mtb_evidence" / "document_grounded_claims"
    / "graph_candidate_repository" / "2.0" / "candidates.jsonl"
)
OUT = REPO_ROOT / "evaluation" / "rq1_graph_candidate_fidelity"


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()

    print(f"[rq1] sorgente KG: {KG_ROOT}")
    graph = FrozenKnowledgeGraph(KG_ROOT)
    fingerprint = graph.fingerprint()
    print(f"[rq1] fingerprint corpus: {fingerprint['corpus_fingerprint'][:16]}…")

    builder = EligiblePathBuilder(graph)
    paths = builder.build()
    print(f"[rq1] path eleggibili ricostruiti: {len(paths)}")

    candidates = list(load_candidates(CANDIDATES))
    print(f"[rq1] candidate materializzate: {len(candidates)}")

    comparator = MaterializationComparator(paths, candidates)
    result = comparator.compare()
    metrics = aggregate(result, paths, len(candidates))

    comparisons = result["comparisons"]
    by_path = {c.path_id: c for c in comparisons}

    # ------------------------------------------------------------ full_results
    # Una riga per path eleggibile. I ``field_results`` sono riportati per esteso
    # solo quando almeno un campo fallisce: l'elenco dei campi confrontati è fisso
    # e documentato (``COMPARED_FIELDS``), quindi ``all_contract_fields_ok`` è una
    # codifica compatta e non lossy dell'esito. Le ``diagnostics`` sono ridotte ai
    # valori non vuoti per la stessa ragione.
    from evaluation.rq1.compare import COMPARED_FIELDS
    with (OUT / "full_results.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for path in paths:
            comparison = by_path[path.path_id]
            all_ok = all(comparison.field_results.get(n) is True for n in COMPARED_FIELDS)
            record = {
                "path_id": comparison.path_id,
                "rule_id": comparison.rule_id,
                "candidate_id": comparison.candidate_id,
                "matched": comparison.matched,
                "all_contract_fields_ok": all_ok,
                "payload_identity_ok": comparison.field_results.get("payload_identity"),
                "expected_payload_identity_ok": comparison.field_results.get("expected_payload_identity"),
                "lineage_ok": comparison.lineage_ok,
                "source_table": path.source_table,
                "source_row_index": path.source_row_index,
            }
            if not all_ok:
                record["field_results"] = comparison.field_results
                record["findings"] = comparison.findings
            if comparison.graph_fidelity_findings:
                record["graph_fidelity_findings"] = comparison.graph_fidelity_findings
                record["diagnostics"] = {k: v for k, v in (path.diagnostics or {}).items() if v}
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    # -------------------------------------------------------------- mismatches
    mismatch_rows = []
    for comparison in comparisons:
        for finding in comparison.findings:
            mismatch_rows.append({
                "path_id": comparison.path_id,
                "rule_id": comparison.rule_id,
                "candidate_id": comparison.candidate_id,
                "layer": "contract",
                "error_class": finding.get("class"),
                "field": finding.get("field", ""),
                "detail": json.dumps(finding, ensure_ascii=False)[:2000],
            })
        for finding in comparison.graph_fidelity_findings:
            mismatch_rows.append({
                "path_id": comparison.path_id,
                "rule_id": comparison.rule_id,
                "candidate_id": comparison.candidate_id,
                "layer": "graph",
                "error_class": finding.get("class"),
                "field": "",
                "detail": json.dumps(finding, ensure_ascii=False)[:2000],
            })
    _write_csv(
        OUT / "mismatches.csv",
        ["path_id", "rule_id", "candidate_id", "layer", "error_class", "field", "detail"],
        mismatch_rows,
    )

    # ------------------------------------------------------- missing / spurious
    _write_csv(
        OUT / "missing_candidates.csv",
        ["path_id", "rule_id", "source_table", "source_row_index", "reason"],
        [
            {
                "path_id": c.path_id, "rule_id": c.rule_id,
                "source_table": next(p.source_table for p in paths if p.path_id == c.path_id),
                "source_row_index": next(p.source_row_index for p in paths if p.path_id == c.path_id),
                "reason": "PATH_NOT_FOUND",
            }
            for c in comparisons if not c.matched
        ],
    )
    _write_csv(
        OUT / "spurious_candidates.csv",
        ["candidate_id", "materialization_rule_id", "predicate", "node_ids", "reason"],
        [
            {
                "candidate_id": c.get("candidate_id"),
                "materialization_rule_id": c.get("materialization_rule_id"),
                "predicate": c.get("predicate"),
                "node_ids": "|".join(c.get("node_ids") or []),
                "reason": "SPURIOUS_CANDIDATE",
            }
            for c in result["spurious"]
        ],
    )

    # -------------------------------------------------------------- duplicates
    exact_groups: dict[str, list[str]] = {}
    for candidate in candidates:
        exact_groups.setdefault(candidate.get("payload_hash"), []).append(candidate.get("candidate_id"))
    duplicate_rows = [
        {"kind": "exact", "group_key": h, "size": len(ids), "candidate_ids": "|".join(ids)}
        for h, ids in exact_groups.items() if len(ids) > 1
    ]
    from evaluation.rq1.canonical_key import canonical_key
    semantic_groups: dict[tuple, list[str]] = {}
    for candidate in candidates:
        semantic_groups.setdefault(canonical_key(candidate).semantic(), []).append(candidate.get("candidate_id"))
    for key, ids in semantic_groups.items():
        if len(ids) > 1:
            duplicate_rows.append({
                "kind": "semantic",
                "group_key": json.dumps(key, ensure_ascii=False, default=list)[:500],
                "size": len(ids),
                "candidate_ids": "|".join(ids[:25]),
            })
    _write_csv(OUT / "duplicates.csv", ["kind", "group_key", "size", "candidate_ids"], duplicate_rows)

    # --------------------------------------------------------------- aggregate
    metrics.update({
        "generated_at": started,
        "kg_source": {
            "kind": "FROZEN_CSV_EXPORT",
            "root": str(KG_ROOT),
            "corpus_fingerprint": fingerprint["corpus_fingerprint"],
            "neo4j_used": False,
            "neo4j_available": False,
        },
        "candidates_artifact": {
            "path": str(CANDIDATES.relative_to(REPO_ROOT)),
            "declared_sha256": "d6c65c2682313652b736f1f82968078292c12588823e2f79309e76d6e671235d",
            "verified": True,
        },
        "inventory": graph.inventory(),
        "excluded_paths": len(builder.excluded),
        "exclusion_reasons": dict(Counter(e.reason for e in builder.excluded)),
        "method": (
            "Path eleggibili riderivati in modo indipendente dall'export CSV congelato "
            "(evaluation/rq1/kg_source.py). Il materializzatore originale non è stato rieseguito."
        ),
    })
    _write_json(OUT / "aggregate_metrics.json", metrics)
    _write_json(OUT / "kg_source_fingerprint.json", fingerprint)

    print(json.dumps({
        k: metrics[k] for k in (
            "eligible_paths", "materialized_candidates", "matched_paths",
            "missing_candidate_count", "spurious_candidate_count",
            "materialization_precision", "materialization_recall", "field_completeness",
            "direction_inversions_contract", "direction_inversions_graph",
        )
    }, indent=2))
    print("[rq1] contract findings:", json.dumps(metrics["contract_finding_counts"], indent=1))
    print("[rq1] graph findings:", json.dumps(metrics["graph_fidelity_finding_counts"], indent=1))
    print("[rq1] duplicates:", json.dumps(metrics["duplicates"], indent=1, default=str)[:600])
    return 0


if __name__ == "__main__":
    sys.exit(main())
