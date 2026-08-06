"""RQ1 ripetuto su v3 + shadow comparison v2 vs v3 (§18-§19).

Uso::

    python -m evaluation.run_gca_v3_audit

La verifica strutturale è **indipendente**: i path eleggibili sono riderivati
dai CSV (``evaluation/rq1/kg_source.py``), non rieseguendo il materializzatore
v3. Le metriche semantiche confrontano ogni candidate v3 con la riga sorgente da
cui deriva.

Gli artefatti dell'audit RQ1 precedente (``evaluation/rq1_graph_candidate_fidelity/``)
non vengono toccati.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from evaluation.rq1.kg_source import EligiblePathBuilder, FrozenKnowledgeGraph, _clean
from gca_v3.alterations import ast_from_dict
from gca_v3.contract import GraphCandidateAssertionV3
from gca_v3.materialize import RULE_EVIDENCE_STATEMENT, RULE_EVIDENCE_TO_DRUG

REPO_ROOT = Path(__file__).resolve().parents[1]
KG_ROOT = REPO_ROOT.parent / "data_expl" / "DatasetTESI" / "Dataset TESI" / "Clean_Graph_Data"
BASE = REPO_ROOT / "benchmarks" / "mtb_evidence" / "document_grounded_claims" / "graph_candidate_repository"
OUT = REPO_ROOT / "evaluation" / "gca_v3"


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()

    graph = FrozenKnowledgeGraph(KG_ROOT)
    evidence = graph.node_index("node_evidence.csv")
    profiles = graph.node_index("node_molecular_profile.csv")
    drug_edges: dict[str, list[dict]] = defaultdict(list)
    for _, row in graph.edge_rows("edge_targets_drug.csv"):
        drug_edges[_clean(row.get("source_evidence_id"))].append(row)
    profile_variants: dict[str, list[str]] = defaultdict(list)
    for _, row in graph.edge_rows("edge_in_molecular_profile.csv"):
        profile_variants[_clean(row.get("target_molecular_profile_id"))].append(
            _clean(row.get("source_variant_id")))

    v3 = _load(BASE / "3.0" / "candidates.jsonl")
    v2 = _load(BASE / "2.0" / "candidates.jsonl")
    print(f"[v3-audit] candidate v2={len(v2)} v3={len(v3)}")

    # ------------------------------------------------- struttura (indipendente)
    eligible = EligiblePathBuilder(graph).build()
    eligible_ids = {p.path_id for p in eligible}
    v3_path_ids: set[str] = set()
    for candidate in v3:
        for path_id in candidate["source_path_ids"]:
            v3_path_ids.add(path_id.replace("gca/3.0/evidence-to-intervention#",
                                            "gca/2.0/evidence-to-drug#").replace("gca/3.0/", "gca/2.0/"))
    covered = eligible_ids & v3_path_ids
    spurious_paths = v3_path_ids - eligible_ids
    missing_paths = eligible_ids - v3_path_ids

    # ------------------------------------------------------- lineage e identità
    lineage_broken = 0
    identity_broken = 0
    invariant_violations: Counter = Counter()
    for record in v3:
        candidate = GraphCandidateAssertionV3(**record)
        violations = candidate.validate()
        for violation in violations:
            invariant_violations[violation] += 1
        if "INV6_NON_DETERMINISTIC_IDENTITY" in violations:
            identity_broken += 1
        if not record["source_path_ids"]:
            lineage_broken += 1

    # ------------------------------------------------------- polarità semantica
    polarity_rows: list[dict] = []
    polarity_lost = 0
    promoted_unsupported = 0
    auto_inversions = 0
    for record in v3:
        if record["materialization_rule_id"] not in {RULE_EVIDENCE_STATEMENT, RULE_EVIDENCE_TO_DRUG}:
            continue
        evidence_id = (record["evidence_record_ids"] or ["evidence:"])[0].split(":", 1)[1]
        erow = evidence.get(evidence_id) or {}
        source_direction = _clean(erow.get("evidence_direction"))
        source_significance = _clean(erow.get("significance"))

        raw = record["source_polarity_raw"]
        if (raw.get("evidence_direction") or "") != (source_direction or None or ""):
            if not (raw.get("evidence_direction") is None and source_direction == ""):
                polarity_lost += 1
        if source_direction == "Does Not Support":
            if record["source_alignment_status"] == "SOURCE_ALIGNED":
                promoted_unsupported += 1
            if record["source_supported_direction"] is not None:
                auto_inversions += 1
        polarity_rows.append({
            "candidate_id": record["candidate_id"],
            "rule": record["materialization_rule_id"],
            "source_evidence_direction": source_direction,
            "source_significance": source_significance,
            "graph_direction": record["graph_direction"],
            "source_support_polarity": record["source_support_polarity"],
            "source_supported_direction": record["source_supported_direction"] or "",
            "source_alignment_status": record["source_alignment_status"],
            "predicate": record["predicate"],
        })
    _write_csv(OUT / "polarity_audit.csv", list(polarity_rows[0].keys()) if polarity_rows else
               ["candidate_id"], polarity_rows)

    # ----------------------------------------------------- alterazioni composte
    compound_rows: list[dict] = []
    parse_failures: list[dict] = []
    terms_lost = 0
    operators_lost = 0
    for record in v3:
        status = record["alteration_parse_status"]
        if status in {"MALFORMED_EXPRESSION", "UNSUPPORTED_EXPRESSION", "AMBIGUOUS_OPERATOR"}:
            parse_failures.append({
                "candidate_id": record["candidate_id"],
                "raw": record["alteration_expression_raw"],
                "status": status,
                "warnings": "|".join(record["alteration_parse_warnings"]),
            })
            continue
        if status not in {"PARSED_EXACT", "PARSED_WITH_WARNINGS"}:
            continue
        raw = record["alteration_expression_raw"] or ""
        node = ast_from_dict(record["alteration_expression_ast"])
        terms = node.terms()
        # Ogni termine dev'essere una sottostringa del raw: nessun termine inventato.
        for term in terms:
            if term.raw and term.raw not in raw:
                terms_lost += 1
        # Ogni operatore presente nel raw dev'essere presente nell'AST.
        node_types = {n for n in _walk_types(node)}
        for operator in ("AND", "OR", "NOT"):
            if f" {operator} " in f" {raw} " and operator not in node_types:
                operators_lost += 1
        compound_rows.append({
            "candidate_id": record["candidate_id"],
            "raw": raw,
            "canonical": record.get("alteration_canonical_expression") or "",
            "term_count": len(terms),
            "operators": "|".join(sorted(node_types - {"TERM"})),
            "status": status,
        })
    _write_csv(OUT / "compound_alterations.csv",
               ["candidate_id", "raw", "canonical", "term_count", "operators", "status"],
               compound_rows)
    _write_csv(OUT / "alteration_parse_failures.csv",
               ["candidate_id", "raw", "status", "warnings"], parse_failures)

    # ------------------------------------------------------------------ regimi
    regimen_rows: list[dict] = []
    unresolved_rows: list[dict] = []
    invented_semantics = 0
    unresolved_split = 0
    for record in v3:
        structure = record["intervention_structure"]
        if structure == "UNKNOWN":
            continue
        components = record["intervention_components"]
        regimen_rows.append({
            "candidate_id": record["candidate_id"],
            "structure": structure,
            "semantics_status": record["regimen_semantics_status"],
            "component_count": len(components),
            "components": "|".join(str(c.get("name")) for c in components),
            "regimen_id": record["regimen_id"] or "",
            "roles": "|".join(sorted({str(c.get("component_role")) for c in components})),
        })
        if structure in {"COMBINATION_CONFIRMED", "ALTERNATIVE_CONFIRMED", "SEQUENTIAL_CONFIRMED"}:
            invented_semantics += 1  # l'export non consente di confermarli
        if structure == "MULTI_COMPONENT_UNRESOLVED":
            unresolved_rows.append({
                "candidate_id": record["candidate_id"],
                "regimen_id": record["regimen_id"] or "",
                "component_count": len(components),
                "components": "|".join(str(c.get("name")) for c in components),
                "semantics_status": record["regimen_semantics_status"],
                "limitations": "|".join(record["regimen_limitations"]),
            })
            if len(components) < 2:
                unresolved_split += 1
    _write_csv(OUT / "regimen_audit.csv",
               ["candidate_id", "structure", "semantics_status", "component_count",
                "components", "regimen_id", "roles"], regimen_rows)
    _write_csv(OUT / "unresolved_regimens.csv",
               ["candidate_id", "regimen_id", "component_count", "components",
                "semantics_status", "limitations"], unresolved_rows)

    # v2: quanti record multi-farmaco erano spezzati in candidate positive?
    v2_evidence_drug = [c for c in v2 if c["materialization_rule_id"] == "gca/2.0/evidence-to-drug"]
    v2_by_evidence: dict[str, int] = Counter()
    for candidate in v2_evidence_drug:
        if candidate["evidence_record_ids"]:
            v2_by_evidence[candidate["evidence_record_ids"][0]] += 1
    v2_split = sum(n for n in v2_by_evidence.values() if n > 1)

    # ------------------------------------------------------- shadow comparison
    v3_compound = sum(1 for c in v3 if c["alteration_parse_status"] in {"PARSED_EXACT", "PARSED_WITH_WARNINGS"})
    v2_alteration_lost = 1091  # misurato nell'audit RQ1 su v2
    shadow = {
        "candidates_v2": len(v2),
        "candidates_v3": len(v3),
        "delta": len(v3) - len(v2),
        "delta_explained": (
            "3370 archi farmaco v2 -> 2648 record Evidence v3 = -722; "
            "nessun'altra regola cambia cardinalita'"
        ),
        "eligible_paths": len(eligible_ids),
        "paths_covered_by_v3": len(covered),
        "paths_missing_in_v3": len(missing_paths),
        "spurious_paths_in_v3": len(spurious_paths),
        "polarity_now_explicit": sum(
            1 for c in v3 if c["source_support_polarity"] != "NOT_REPORTED"),
        "polarity_explicit_in_v2": 0,
        "does_not_support_now_visible": sum(
            1 for c in v3 if c["source_alignment_status"] == "SOURCE_DOES_NOT_SUPPORT"),
        "compound_alterations_recovered": v3_compound,
        "alterations_lost_in_v2": v2_alteration_lost,
        "regimens_split_in_v2": v2_split,
        "regimens_preserved_as_units_in_v3": len(unresolved_rows),
        "candidates_removed_from_positive_path": sum(
            1 for c in v3 if c["source_alignment_status"] in
            {"SOURCE_DOES_NOT_SUPPORT", "SOURCE_CONTRADICTS", "SOURCE_NEUTRAL"}),
        "candidates_not_eligible_for_intervention_exact_match": len(unresolved_rows),
        "candidates_not_eligible_for_alteration_exact_match": len(parse_failures),
        "note": (
            "v3 non e' migliore perche' produce meno candidate: produce meno "
            "candidate perche' smette di affermare N relazioni positive dove la "
            "sorgente ne descriveva una sola, non separabile."
        ),
    }
    _write_json(OUT / "v2_v3_shadow_comparison.json", shadow)

    # ------------------------------------------------------------- full results
    with (OUT / "full_fidelity_results.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for record in v3:
            handle.write(json.dumps({
                "candidate_id": record["candidate_id"],
                "rule": record["materialization_rule_id"],
                "source_path_ids": record["source_path_ids"],
                "graph_direction": record["graph_direction"],
                "source_support_polarity": record["source_support_polarity"],
                "source_alignment_status": record["source_alignment_status"],
                "alteration_parse_status": record["alteration_parse_status"],
                "alteration_term_count": len(record["alteration_terms"]),
                "intervention_structure": record["intervention_structure"],
                "component_count": len(record["intervention_components"]),
                "invariants_ok": not GraphCandidateAssertionV3(**record).validate(),
            }, ensure_ascii=False, sort_keys=True) + "\n")

    # ----------------------------------------------------------------- failures
    failures = []
    for violation, count in invariant_violations.items():
        failures.append({"kind": "INVARIANT", "detail": violation, "count": count})
    for name, count in (("polarity_lost", polarity_lost),
                        ("unsupported_promoted", promoted_unsupported),
                        ("automatic_direction_inversions", auto_inversions),
                        ("compound_terms_lost", terms_lost),
                        ("compound_operators_lost", operators_lost),
                        ("unresolved_regimens_split", unresolved_split),
                        ("invented_regimen_semantics", invented_semantics),
                        ("lineage_broken", lineage_broken),
                        ("missing_paths", len(missing_paths)),
                        ("spurious_paths", len(spurious_paths))):
        if count:
            failures.append({"kind": "SEMANTIC", "detail": name, "count": count})
    _write_csv(OUT / "failures.csv", ["kind", "detail", "count"], failures)

    metrics = {
        "generated_at": started,
        "repository_v3": "graph_candidate_repository/3.0",
        "repository_v2_unchanged": True,
        "structural": {
            "eligible_source_paths": len(eligible_ids),
            "candidates_materialized": len(v3),
            "paths_covered": len(covered),
            "structural_precision": round(1 - len(spurious_paths) / max(len(v3_path_ids), 1), 6),
            "structural_recall": round(len(covered) / max(len(eligible_ids), 1), 6),
            "payload_reproducibility": round(1 - identity_broken / max(len(v3), 1), 6),
            "duplicate_rate": round(
                1 - len({c["candidate_id"] for c in v3}) / max(len(v3), 1), 6),
            "lineage_integrity": round(1 - lineage_broken / max(len(v3), 1), 6),
        },
        "semantic": {
            "source_polarity_lost": polarity_lost,
            "unsupported_candidates_promoted_as_supported": promoted_unsupported,
            "automatic_direction_inversions": auto_inversions,
            "compound_alteration_terms_lost": terms_lost,
            "compound_operator_lost": operators_lost,
            "compound_expression_parse_failures": len(parse_failures),
            "compound_alterations_preserved": len(compound_rows),
            "single_agent_count": sum(1 for r in regimen_rows if r["structure"] == "SINGLE_AGENT"),
            "confirmed_regimen_count": sum(
                1 for r in regimen_rows if r["structure"].endswith("_CONFIRMED")),
            "unresolved_regimen_count": len(unresolved_rows),
            "unresolved_regimens_split_into_positive_components": unresolved_split,
            "invented_regimen_semantics": invented_semantics,
            "broken_lineage": lineage_broken,
        },
        "invariant_violations": dict(invariant_violations),
        "shadow_comparison": shadow,
    }
    _write_json(OUT / "aggregate_metrics.json", metrics)

    print("\n=== STRUTTURA ===")
    for key, value in metrics["structural"].items():
        print(f"  {key:34} = {value}")
    print("\n=== SEMANTICA (i criteri di §19 devono valere 0) ===")
    for key, value in metrics["semantic"].items():
        flag = ""
        if key in {"source_polarity_lost", "unsupported_candidates_promoted_as_supported",
                   "automatic_direction_inversions", "compound_alteration_terms_lost",
                   "compound_operator_lost",
                   "unresolved_regimens_split_into_positive_components",
                   "invented_regimen_semantics", "broken_lineage"}:
            flag = "  OK" if value == 0 else "  *** VIOLAZIONE ***"
        print(f"  {key:52} = {value}{flag}")
    print("\n=== SHADOW v2 vs v3 ===")
    for key in ("candidates_v2", "candidates_v3", "delta", "polarity_now_explicit",
                "does_not_support_now_visible", "compound_alterations_recovered",
                "regimens_split_in_v2", "regimens_preserved_as_units_in_v3",
                "candidates_removed_from_positive_path"):
        print(f"  {key:48} = {shadow[key]}")
    print(f"\ninvariant violations: {dict(invariant_violations) or 'NONE'}")
    return 0


def _walk_types(node):
    yield node.node_type
    for operand in node.operands:
        yield from _walk_types(operand)


if __name__ == "__main__":
    sys.exit(main())
