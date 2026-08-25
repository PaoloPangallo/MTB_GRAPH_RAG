"""Freeze a metadata-only relation-aware evaluation sample."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from backend.research_pipeline.retrieval.relation_family import (
    CLINICAL_TRIAL, KG_ONLY, PAPER_EVIDENCE, classify_relation_family,
)

SELECTION_SEED = 20260825
CORE_COMMIT = "dd010056ae348e42e66a6f0098c9e9eb26890d6b2"
ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "benchmarks/mtb_evidence/document_grounded_claims/graph_candidate_repository/2.0/candidates.jsonl"
MANIFEST = ROOT / "benchmarks/mtb_evidence/document_grounded_claims/authorized_document_cache_pilot/document_manifest.jsonl"
OUT = Path(__file__).resolve().parent
TARGETS = {
    "predictive_sensitivity_response": 6, "resistance_reduced_adverse": 4,
    "diagnostic": 2, "prognostic": 2, "other": 2,
    "trial_drug": 5, "trial_gene": 5,
    "gene_drug_interaction": 6, "companion_diagnostic": 4,
}


def ids(items: Any, key: str) -> tuple[str, ...]:
    return tuple(sorted({str(x[key]) for x in items or [] if isinstance(x, dict) and x.get(key)}))


def labels(items: Any) -> tuple[str, ...]:
    return tuple(sorted(str(x["label"]) for x in items or [] if isinstance(x, dict) and x.get("label")))


def development_ids() -> set[str]:
    result = {"GCA-008ae3aad1a64c118318ef79"}
    pattern = re.compile(r"GCA-[0-9a-f]{24}")
    for path in (ROOT / "backend/research_pipeline/tests").glob("*.py"):
        result.update(pattern.findall(path.read_text(encoding="utf-8")))
    return result


def family_stratum(c: dict[str, Any], family: str) -> str:
    if family == PAPER_EVIDENCE:
        evidence = c.get("source_properties", {}).get("evidence", {})
        kind, direction = str(evidence.get("evidence_type") or ""), str(c.get("direction") or "")
        if kind == "Diagnostic": return "diagnostic"
        if kind == "Prognostic": return "prognostic"
        if kind == "Predictive" and direction in {"Resistance", "Reduced Sensitivity", "Adverse Response"}:
            return "resistance_reduced_adverse"
        if kind == "Predictive" and direction in {"Supports", "Sensitivity/Response"}:
            return "predictive_sensitivity_response"
        return "other"
    if family == CLINICAL_TRIAL:
        return "trial_gene" if c.get("biomarkers") else "trial_drug"
    return "companion_diagnostic" if c.get("predicate") == "has_companion_diagnostic" else "gene_drug_interaction"


def novelty(c: dict[str, Any], family: str) -> tuple[Any, ...]:
    genes, diseases, drugs = labels(c.get("biomarkers")), labels(c.get("disease")), labels(c.get("interventions"))
    variants = tuple(sorted(str(x["label"]) for x in c.get("biomarkers") or [] if isinstance(x, dict) and x.get("type") == "Variant"))
    if family == PAPER_EVIDENCE:
        return (ids(c.get("document_identifiers"), "pmid"), diseases, genes, variants, c.get("direction"))
    if family == CLINICAL_TRIAL:
        return (ids(c.get("document_identifiers"), "nct"), genes, drugs, diseases)
    props = c.get("source_properties", {})
    source = props.get("interaction", {}).get("source_db") or props.get("diagnostic", {}).get("source_db") or ""
    return (genes, drugs, str(source), tuple(c.get("graph_path") or []))


def select(pool: list[dict[str, Any]], count: int, family: str, unique_document: bool) -> list[dict[str, Any]]:
    remaining, selected = sorted(pool, key=lambda x: x["candidate_id"]), []
    seen = [set() for _ in range(len(novelty(remaining[0], family)))] if remaining else []
    while remaining and len(selected) < count:
        candidates = remaining
        if unique_document:
            key = "pmid" if family == PAPER_EVIDENCE else "nct"
            used = {ids(x.get("document_identifiers"), key) for x in selected}
            candidates = [x for x in remaining if ids(x.get("document_identifiers"), key) not in used]
        if not candidates: break
        def score(x: dict[str, Any]) -> tuple[int, int, str]:
            values = novelty(x, family)
            fresh = [v for i, v in enumerate(values) if v and v not in seen[i]]
            return (sum(100 - i * 10 for i in range(len(fresh))), len(fresh), x["candidate_id"])
        chosen = max(candidates, key=score)
        selected.append(chosen); remaining.remove(chosen)
        for i, value in enumerate(novelty(chosen, family)):
            if value: seen[i].add(value)
    return selected


def snapshot_ids() -> set[str]:
    if not MANIFEST.is_file(): return set()
    return {str(r.get("document_id")) for r in (json.loads(x) for x in MANIFEST.read_text(encoding="utf-8").splitlines() if x.strip()) if r.get("document_id")}


def source_database(c: dict[str, Any]) -> str | None:
    props = c.get("source_properties", {})
    for section in ("evidence", "interaction", "diagnostic"):
        for key in ("source_database", "source_db", "source_type"):
            if props.get(section, {}).get(key): return str(props[section][key])
    return None


def entry(c: dict[str, Any], sample_id: str, family: str, snapshots: set[str], exposed: set[str]) -> dict[str, Any]:
    pmids, ncts = ids(c.get("document_identifiers"), "pmid"), ids(c.get("document_identifiers"), "nct")
    docs = {*(f"pmid:{x}" for x in pmids), *(f"nct:{x}" for x in ncts)}
    return {"sample_id": sample_id, "candidate_id": c["candidate_id"], "relation_family": family,
            "stratum": family_stratum(c, family), "subject": c.get("subject"), "predicate": c.get("predicate"),
            "object": c.get("object"), "disease": c.get("disease") or [], "direction": c.get("direction"),
            "evidence_type": c.get("source_properties", {}).get("evidence", {}).get("evidence_type"),
            "document_identifiers": c.get("document_identifiers") or [],
            "source_type": c.get("source_properties", {}).get("evidence", {}).get("source_type"),
            "source_database": source_database(c), "materialization_rule_id": c.get("materialization_rule_id"),
            "graph_provenance": {k: c.get(k) for k in ("node_ids", "edge_ids", "graph_path", "materialization_rule_id") if c.get(k) is not None},
            "development_exposed": c["candidate_id"] in exposed, "snapshot_available": bool(docs & snapshots) if docs else False}


def validate(entries: list[dict[str, Any]]) -> None:
    assert len(entries) == 36
    assert Counter(x["relation_family"] for x in entries) == Counter({PAPER_EVIDENCE: 16, CLINICAL_TRIAL: 10, KG_ONLY: 10})
    assert Counter(x["stratum"] for x in entries) == Counter(TARGETS)
    assert not any(x["development_exposed"] for x in entries)
    assert len({ids(x["document_identifiers"], "pmid")[0] for x in entries if x["relation_family"] == PAPER_EVIDENCE}) == 16
    assert len({ids(x["document_identifiers"], "nct")[0] for x in entries if x["relation_family"] == CLINICAL_TRIAL}) == 10
    for x in entries:
        if x["relation_family"] == KG_ONLY: assert not x["document_identifiers"]
        assert classify_relation_family({"document_identifiers": x["document_identifiers"]}) == x["relation_family"]


def main() -> None:
    candidates = [json.loads(x) for x in CORPUS.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(candidates) == 46864
    exposed = development_ids()
    eligible = [x for x in candidates if x["candidate_id"] not in exposed]
    pools = {s: [] for s in TARGETS}
    for c in eligible: pools[family_stratum(c, classify_relation_family(c))].append(c)
    chosen: list[tuple[dict[str, Any], str]] = []
    for stratum, count in TARGETS.items():
        family = PAPER_EVIDENCE if stratum in {"predictive_sensitivity_response", "resistance_reduced_adverse", "diagnostic", "prognostic", "other"} else CLINICAL_TRIAL if stratum.startswith("trial_") else KG_ONLY
        result = select(pools[stratum], count, family, family in {PAPER_EVIDENCE, CLINICAL_TRIAL})
        assert len(result) == count, (stratum, len(result), count)
        chosen.extend((c, family) for c in result)
    chosen.sort(key=lambda item: (item[1], family_stratum(item[0], item[1]), item[0]["candidate_id"]))
    snapshots, counters, entries = snapshot_ids(), Counter(), []
    for c, family in chosen:
        counters[family] += 1
        prefix = {PAPER_EVIDENCE: "PAPER", CLINICAL_TRIAL: "TRIAL", KG_ONLY: "KGONLY"}[family]
        entries.append(entry(c, f"{prefix}-{counters[family]:02d}", family, snapshots, exposed))
    validate(entries)
    payload = {"sample_version": "relation-aware-evaluation/1.0", "core_commit": CORE_COMMIT, "selection_seed": SELECTION_SEED, "total": 36, "entries": entries}
    OUT.mkdir(parents=True, exist_ok=True)
    sample_path = OUT / "candidate_sample.json"
    sample_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = hashlib.sha256(sample_path.read_bytes()).hexdigest()
    rows = []
    for stratum in TARGETS:
        subset = [x for x in entries if x["stratum"] == stratum]
        rows.append(f"| {subset[0]['relation_family']} | {stratum} | {len(subset)} | {sum(bool(x['snapshot_available']) for x in subset)} |")
    selected_ids = {x["candidate_id"] for x in entries}
    selected_genes = {str(item["label"]) for c in candidates if c["candidate_id"] in selected_ids for item in c.get("biomarkers") or [] if isinstance(item, dict) and item.get("type") == "Gene" and item.get("label")}
    selected_diseases = {label for c in candidates if c["candidate_id"] in selected_ids for label in labels(c.get("disease"))}
    exposed_list = ", ".join(sorted(exposed)) or "none"
    report = f"""# Relation-aware evaluation sample

This sample is frozen from GCA 2.0 metadata only. No parser, reader, provider, document API, or runtime output was used.

- Core commit: `{CORE_COMMIT}`
- Selection seed: `{SELECTION_SEED}`
- Total: **36** (`PAPER_EVIDENCE=16`, `CLINICAL_TRIAL=10`, `KG_ONLY=10`)
- Candidate sample SHA256: `{digest}`

## Deterministic selection rules

Strata and counts were fixed before selection. Candidates were classified from actual PMID/NCT identifiers. Within each stratum, stable candidate IDs and deterministic novelty over document, disease, gene, variant, direction, intervention, source database, and graph path metadata were used. Paper and trial documents are unique within the sample. No output-aware criterion was used.

CASE-1 (`GCA-008ae3aad1a64c118318ef79`, PMID 19223544) and every valid 24-character GCA ID explicitly present in the research-pipeline semantic/development tests were excluded. The excluded development-exposure inventory was: `{exposed_list}`. Selected development-exposed candidates: 0.

## Frozen strata

| Family | Stratum | N | Snapshot available |
|---|---|---:|---:|
{chr(10).join(rows)}

## Inventory and limitations

- Unique selected PMIDs: {len({ids(x['document_identifiers'], 'pmid')[0] for x in entries if x['relation_family'] == PAPER_EVIDENCE})}.
- Unique selected NCTs: {len({ids(x['document_identifiers'], 'nct')[0] for x in entries if x['relation_family'] == CLINICAL_TRIAL})}.
- Unique selected genes: {len(selected_genes)}.
- Unique selected diseases: {len(selected_diseases)}.
- Development-exposed selected candidates: 0.
- Snapshot availability is an offline inventory only; missing snapshots are not an exclusion criterion for the next phase.
- No gold, expected support, expected quote, or trial outcome was created.
"""
    (OUT / "sample_selection_report.md").write_text(report, encoding="utf-8")
    print(json.dumps({"total": 36, "sha256": digest, "development_exposed": 0,
                      "snapshots_available": sum(bool(x["snapshot_available"]) for x in entries),
                      "snapshots_missing": sum(not x["snapshot_available"] for x in entries)}, sort_keys=True))


if __name__ == "__main__":
    main()
