"""Generate the ontology MVP artefacts without importing or invoking V3 runtime."""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from .evaluator import OntologyShadowEvaluator
from .normalizer import EntityNormalizer
from .registry import OntologyRegistry


FIELDS = [
    "claim_id",
    "entity_type",
    "query_value",
    "claim_value",
    "query_concept_id",
    "claim_concept_id",
    "literal_gate_result",
    "ontology_match_type",
    "ontology_distance",
    "ontology_path",
    "shadow_compatible_candidate",
    "disagreement_type",
    "confidence",
    "notes",
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_claims(repo_root: Path) -> list[dict[str, Any]]:
    corpus = repo_root / "backend/pipeline/evidence/corpus/v3/qualified_claim_repository_1_4"
    rows = read_jsonl(corpus / "therapeutic_claims.jsonl") + read_jsonl(corpus / "diagnostic_claims.jsonl")
    return [row for row in rows if not row.get("deprecated", False)]


def load_parents(repo_root: Path) -> dict[str, dict[str, Any]]:
    path = repo_root / "backend/pipeline/evidence/corpus/v3/qualified_claim_repository_1_4/graph_evidence_parents.jsonl"
    return {row["parent_id"]: row for row in read_jsonl(path)}


def literal_gate(query: str | None, claim: str | None, normalizer: EntityNormalizer, entity_type: str) -> str:
    if not query or not claim:
        return "MISSING"
    left = normalizer.normalize(query, entity_type)
    right = normalizer.normalize(claim, entity_type)
    return "PASS" if left.normalized == right.normalized else "FAIL"


def disagreement(literal: str, match_type: str, query: str | None, claim: str | None) -> str:
    if not query or not claim or match_type == "UNKNOWN":
        return "ONTOLOGY_DATA_MISSING"
    if literal == "PASS" and match_type == "INCOMPATIBLE":
        return "LITERAL_PASS_ONTOLOGY_INCOMPATIBLE"
    if literal == "FAIL" and match_type == "EXACT":
        return "LITERAL_FAIL_ONTOLOGY_EXACT"
    if literal == "FAIL" and match_type == "SYNONYM":
        return "LITERAL_FAIL_ONTOLOGY_SYNONYM"
    if literal == "FAIL" and match_type in {"DESCENDANT", "ANCESTOR"}:
        return "LITERAL_FAIL_ONTOLOGY_HIERARCHICAL"
    if match_type in {"RELATED", "CLASS_MATCH"}:
        return "REQUIRES_MANUAL_REVIEW"
    return "NO_DISAGREEMENT" if literal == "PASS" else "ONTOLOGY_DATA_MISSING"


def make_rows(claims: list[dict[str, Any]], parents: dict[str, dict[str, Any]], evaluator: OntologyShadowEvaluator) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for claim in claims:
        parent = parents.get(claim.get("parent_id"), {})
        pairs: list[tuple[str, str | None, str | None]] = [
            ("disease", parent.get("disease_context"), claim.get("disease_scope")),
            ("variant", parent.get("biomarker_context"), claim.get("biomarker")),
        ]
        if claim.get("claim_domain") == "diagnostic":
            pairs.append(("diagnostic", parent.get("biomarker_context"), claim.get("biomarker")))
        else:
            associations = parent.get("original_intervention_associations") or []
            pairs.append(("intervention", associations[0] if associations else None, claim.get("intervention") or claim.get("canonical_intervention")))
        for entity_type, query_value, claim_value in pairs:
            match = evaluator.compare(query_value, claim_value, entity_type)
            literal = literal_gate(query_value, claim_value, evaluator.normalizer, entity_type)
            notes = [
                "query side = frozen local graph_evidence_parents parent context",
                "shadow-only; no gate, score, bucket, ranking or provenance mutation",
            ]
            if match.query_concept_id is None or match.claim_concept_id is None:
                notes.append("canonical ontology ID unavailable; registry key, when present, is local-only")
            rows.append(
                {
                    "claim_id": claim["claim_id"],
                    "entity_type": entity_type,
                    "query_value": query_value or "",
                    "claim_value": claim_value or "",
                    "query_concept_id": match.query_concept_id or "",
                    "claim_concept_id": match.claim_concept_id or "",
                    "literal_gate_result": literal,
                    "ontology_match_type": match.match_type,
                    "ontology_distance": "" if match.distance is None else match.distance,
                    "ontology_path": " -> ".join(match.path),
                    "shadow_compatible_candidate": str(match.compatible_candidate).lower(),
                    "disagreement_type": disagreement(literal, match.match_type, query_value, claim_value),
                    "confidence": match.confidence,
                    "notes": "; ".join(notes + [match.explanation]),
                }
            )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run(repo_root: Path, output_dir: Path) -> dict[str, Any]:
    registry = OntologyRegistry.from_local_assets(repo_root)
    evaluator = OntologyShadowEvaluator(registry, EntityNormalizer(registry))
    claims = load_claims(repo_root)
    parents = load_parents(repo_root)
    rows = make_rows(claims, parents, evaluator)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "ontology_shadow_results.csv", rows, FIELDS)
    disagreements = [row for row in rows if row["disagreement_type"] != "NO_DISAGREEMENT"]
    write_csv(output_dir / "ontology_disagreements.csv", disagreements, FIELDS)
    registry_rows = []
    for concept in registry.iter_concepts():
        registry_rows.append(
            {
                "registry_key": concept.registry_key,
                "canonical_id": concept.canonical_id or "",
                "label": concept.label,
                "entity_type": concept.entity_type,
                "synonyms": " | ".join(sorted(set(concept.synonyms))),
                "parents": " | ".join(concept.parents),
                "children": " | ".join(concept.children),
                "source": concept.source,
                "version": concept.version or "",
            }
        )
    write_csv(output_dir / "ontology_registry.csv", registry_rows, ["registry_key", "canonical_id", "label", "entity_type", "synonyms", "parents", "children", "source", "version"])
    match_counts = Counter(row["ontology_match_type"] for row in rows)
    disagreement_counts = Counter(row["disagreement_type"] for row in rows)
    mapped = Counter()
    local_mapped = Counter()
    totals = Counter()
    for row in rows:
        totals[row["entity_type"]] += 1
        if row["query_concept_id"] or row["claim_concept_id"]:
            mapped[row["entity_type"]] += 1
        if registry.resolve(row["entity_type"], row["query_value"]) or registry.resolve(row["entity_type"], row["claim_value"]):
            local_mapped[row["entity_type"]] += 1
    summary = {
        "mode": "ONTOLOGY_SHADOW_MODE",
        "claims_evaluated": len(claims),
        "claim_rows_evaluated": len(rows),
        "active_claims_expected": 148,
        "active_claim_count_matches_expected": len(claims) == 148,
        "local_concepts": len(registry.concepts),
        "local_relations": len(registry.relations),
        "local_registry_coverage_by_entity_type": {key: {"mapped_rows": local_mapped[key], "total_rows": totals[key], "percentage": round(100 * local_mapped[key] / totals[key], 2) if totals[key] else 0.0} for key in sorted(totals)},
        "canonical_id_coverage_by_entity_type": {key: {"mapped_rows": mapped[key], "total_rows": totals[key], "percentage": round(100 * mapped[key] / totals[key], 2) if totals[key] else 0.0} for key in sorted(totals)},
        "match_distribution": dict(sorted(match_counts.items())),
        "disagreement_distribution": dict(sorted(disagreement_counts.items())),
        "runtime_integration": "none",
        "external_ontology_service_used": False,
        "llm_used_for_normalization": False,
        "gold_read_count": 0,
    }
    (output_dir / "ontology_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    repo = Path(__file__).resolve().parents[3]
    out = repo / "docs/ontology_mvp"
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    print(json.dumps(run(repo, out), indent=2, ensure_ascii=False))
