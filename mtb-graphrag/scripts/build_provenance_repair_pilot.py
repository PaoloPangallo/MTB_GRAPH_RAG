"""Materialize the non-default qualified-claim provenance repair pilot."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from backend.pipeline.evidence.corpus.provenance_repair_pilot import (
    apply_decision,
    decide_propagation,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend/pipeline/evidence/corpus/v3/qualified_claim_repository_1_4"
DESTINATION = ROOT / (
    "backend/pipeline/evidence/corpus/v3/"
    "qualified_claim_repository_1_5_provenance_pilot"
)
EXPLICIT_MAPPING = ROOT / (
    "benchmarks/mtb_evidence/v3/integrated_shadow_repository_1_3/"
    "qualification_link_regeneration_plan_v1_3.jsonl"
)

PILOT_CLAIM_IDS = (
    "CLM-1d3ba8b6ae49232969c7",  # primary FGFR2
    "CLM-0f234bc9c53847910521",  # primary ALK G1202R, multiple publications
    "CLM-1ee5f9a16a678cebf993",  # EGFR L858R/osimertinib
    "CLM-382985ec558808784e70",  # EGFR L858R/or osimertinib
    "CLM-d4bee44e07efb6ccca9f",  # EGFR L858R/or osimertinib
    "CLM-e565f65d73cb1d4aa67b",  # audit pilot claim
    "CLM-0269a5c7db107cd8a893",  # EGFR/osimertinib parent-only
    "CLM-6016e0878e055658200e",  # DOI available at parent
    "CLM-0e59264facd7b2df0e67",  # resistance, existing direct mapping
    "CLM-5ce532268b4aa1661311",  # resistance, two existing source units
    "CLM-4ffe85304f3ef5533b58",  # aggregate, existing direct mapping
    "CLM-5071bb2d8657ac0fbed0",  # aggregate/preclinical mapping
    "CLM-90e863f00f134fc3cd3d",  # rejected aggregate
    "CLM-8941c177da91f66ff93a",  # diagnostic
    "CLM-1fc4af943701d57d45ad",  # EGFR direct mapping
    "CLM-89ea67ee7946d9ccd552",  # EGFR direct mapping
    "CLM-091cf6602db85e2a2d41",  # FGFR2 resistance/sensitivity mapping
    "CLM-4a89bb28592af7ebaccf",  # regimen source-unit mapping
)


def jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def canonical_jsonl(rows: list[dict[str, Any]]) -> str:
    return "\n".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows
    ) + "\n"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mapping_index() -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in jsonl(EXPLICIT_MAPPING):
        claim_id = str(row.get("claim_id") or "")
        if not claim_id:
            continue
        units = row.get("source_unit_ids") or ()
        if not units and row.get("source_unit_id"):
            units = [row["source_unit_id"]]
        normalized = dict(row)
        normalized["source_unit_ids"] = list(units)
        previous = index.get(claim_id)
        if previous is not None and previous != normalized:
            raise RuntimeError(f"conflicting explicit mapping for {claim_id}")
        index[claim_id] = normalized
    return index


def materialize() -> dict[str, Any]:
    if DESTINATION.exists():
        raise RuntimeError(f"refusing to overwrite existing pilot: {DESTINATION}")
    claims = jsonl(SOURCE / "evidence_claims.jsonl")
    parents = {row["parent_id"]: row for row in jsonl(SOURCE / "graph_evidence_parents.jsonl")}
    mappings = mapping_index()
    pilot_ids = set(PILOT_CLAIM_IDS)
    if len(pilot_ids) != len(PILOT_CLAIM_IDS):
        raise RuntimeError("duplicate pilot claim id")
    missing = pilot_ids - {str(row["claim_id"]) for row in claims}
    if missing:
        raise RuntimeError(f"pilot claims missing from 1.4: {sorted(missing)}")

    repaired: list[dict[str, Any]] = []
    decisions: dict[str, dict[str, Any]] = {}
    for row in claims:
        claim_id = str(row["claim_id"])
        if claim_id not in pilot_ids:
            repaired.append(dict(row))
            continue
        parent = parents[str(row["parent_id"])]
        decision = decide_propagation(
            row,
            parent,
            explicit_mapping=mappings.get(claim_id),
        )
        repaired_row = apply_decision(row, decision)
        repaired.append(repaired_row)
        decisions[claim_id] = {
            "status": decision.status,
            "rule": decision.rule,
            "reason": decision.reason,
            "confidence": decision.confidence,
            "source_unit_ids": list(decision.source_unit_ids),
            "source_ids": list(decision.source_ids),
            "locators": [dict(item) for item in decision.locators],
        }

    DESTINATION.mkdir(parents=True)
    (DESTINATION / "evidence_claims.jsonl").write_text(
        canonical_jsonl(repaired), encoding="utf-8"
    )
    (DESTINATION / "therapeutic_claims.jsonl").write_text(
        canonical_jsonl([row for row in repaired if row.get("claim_domain") == "therapeutic"]),
        encoding="utf-8",
    )
    (DESTINATION / "diagnostic_claims.jsonl").write_text(
        canonical_jsonl([row for row in repaired if row.get("claim_domain") == "diagnostic"]),
        encoding="utf-8",
    )
    shutil.copy2(SOURCE / "graph_evidence_parents.jsonl", DESTINATION / "graph_evidence_parents.jsonl")
    manifest = {
        "repository_version": "qualified_claim_repository/1.5-provenance-pilot",
        "source_repository_version": "qualified_claim_repository/1.4",
        "materialization_status": "pilot_overlay_not_default",
        "operational_retriever_bound": False,
        "gate_semantics_modified": False,
        "scoring_semantics_modified": False,
        "bucket_semantics_modified": False,
        "knowledge_graph_modified": False,
        "pilot_claim_ids": list(PILOT_CLAIM_IDS),
        "explicit_mapping_source": str(EXPLICIT_MAPPING.relative_to(ROOT)),
        "decisions": decisions,
    }
    (DESTINATION / "provenance_repair_manifest.json").write_text(
        canonical_json(manifest), encoding="utf-8"
    )
    manifest["sha256"] = {
        name: sha256(DESTINATION / name)
        for name in (
            "evidence_claims.jsonl",
            "therapeutic_claims.jsonl",
            "diagnostic_claims.jsonl",
            "graph_evidence_parents.jsonl",
        )
    }
    (DESTINATION / "provenance_repair_manifest.json").write_text(
        canonical_json(manifest), encoding="utf-8"
    )
    return manifest


if __name__ == "__main__":
    print(json.dumps(materialize(), ensure_ascii=False, indent=2, sort_keys=True))
