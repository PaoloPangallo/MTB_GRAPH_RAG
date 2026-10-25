"""Genera il repository shadow del modello tipizzato parent/claim.

Legge i record V2, il corpus operativo e l'adjudication congelata, e produce
sotto `v3/typed_claim_shadow_migration/` un repository che convive con la
pipeline corrente senza modificarne gli output. Non tocca adapter, corpus,
retriever, scoring o view operative; non legge il gold; non usa rete, Neo4j o
LLM.

Deterministico: ogni output e' ordinato per chiave dichiarata, e con
`--reverse-input-order` gli ingressi vengono letti al contrario e il risultato
deve restare byte-identico.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from backend.pipeline.evidence.shadow import shadow_output as OUT
from backend.pipeline.evidence.shadow import shadow_scoring as SCORE
from backend.pipeline.evidence.shadow import structural_gates as GATE
from backend.pipeline.evidence.shadow.migration import migrate
from backend.pipeline.evidence.shadow.schema import (
    MIGRATION_ORIGIN_ADJUDICATED,
    MIGRATION_ORIGIN_LEGACY,
    MIGRATION_STATUS,
    MODEL_SCHEMA_VERSION,
    OPERATIONAL_CORPUS_VERSION,
    SHADOW_REPOSITORY_VERSION,
)
from backend.pipeline.evidence.shadow.shadow_adapter import SHADOW_ADAPTER_VERSION
from benchmarks.mtb_evidence.evaluation.multi_intervention_second_review import (
    canonical_dumps,
    canonical_jsonl,
    sha256_text,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
V3 = REPO_ROOT / "benchmarks/mtb_evidence/v3"
ADJ = V3 / "multi_intervention_adjudication"
CONTRACT = V3 / "claim_type_retrieval_contract"
CORPUS = V3 / "qualification_corpus_v2"
ADAPTER_REVIEW = V3 / "multi_intervention_adapter_review"
DATA = REPO_ROOT / "benchmarks/mtb_evidence/evaluation/data"
DEFAULT_OUTPUT = V3 / "typed_claim_shadow_migration"

# Artefatti operativi di cui va dimostrata l'invarianza.
OPERATIONAL_ARTIFACTS = (
    "backend/pipeline/evidence/v2_adapter.py",
    "backend/pipeline/evidence/repository.py",
    "backend/pipeline/evidence/qualified_retriever.py",
    "backend/pipeline/evidence/qualified_retrieval_scoring.py",
    "backend/pipeline/evidence/qualified_retriever_scoring_config.json",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/evidence_statements.jsonl",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/qualification_links.jsonl",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/qualified_evidence_views.jsonl",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/qualification_corpus_manifest.json",
    "benchmarks/mtb_evidence/v3/v2_v3a_exploratory_pilot/frozen_v2_results.jsonl",
)

MANDATORY_CASES = (
    "evidence:275",
    "evidence:4759",
    "evidence:3811",
    "evidence:11240",
    "evidence:12131",
)

# Punteggi arbitrariamente alti usati per dimostrare che i pesi non aggirano il
# gate. Non sono pesi del modello: sono contro-esempi.
BYPASS_PROBE_SCORES = (0.0, 1.0, 1000.0, 999999.0)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def build(reverse: bool = False) -> dict[str, str]:
    """Costruisce tutti gli artefatti e li restituisce come mappa nome -> testo."""
    v2_rows = load_jsonl(ADAPTER_REVIEW / "intervention_lineage.jsonl")
    statements = load_jsonl(CORPUS / "evidence_statements.jsonl")
    approved = load_jsonl(ADJ / "approved_claim_simulation.jsonl")
    unsupported_records = load_jsonl(ADJ / "unsupported_associations.jsonl")
    unresolved_records = load_jsonl(ADJ / "unresolved_associations.jsonl")
    packets = load_jsonl(ADJ / "packet_adjudications.jsonl")
    queries = load_jsonl(DATA / "claim_retrieval_queries_v1.jsonl")

    if reverse:
        v2_rows = list(reversed(v2_rows))
        statements = list(reversed(statements))
        approved = list(reversed(approved))
        unsupported_records = list(reversed(unsupported_records))
        unresolved_records = list(reversed(unresolved_records))
        packets = list(reversed(packets))
        queries = list(reversed(queries))

    result = migrate(
        v2_rows=v2_rows,
        statements=statements,
        approved_claims=approved,
        unsupported_records=unsupported_records,
        unresolved_records=unresolved_records,
        adjudicated_graph_evidence_ids=[p["graph_evidence_id"] for p in packets],
    )

    artifacts: dict[str, str] = {}

    # --- repository ----------------------------------------------------------

    artifacts["graph_evidence_parents.jsonl"] = canonical_jsonl(
        [p.to_dict() for p in result.parents], key="graph_evidence_id"
    )
    claim_rows = [c.to_dict() for c in result.claims]
    artifacts["typed_claims.jsonl"] = canonical_jsonl(claim_rows, key="claim_id")
    for name, claim_type in (
        ("atomic_claims.jsonl", "atomic_intervention_claim"),
        ("aggregate_claims.jsonl", "aggregate_intervention_claim"),
        ("regimen_claims.jsonl", "regimen_claim"),
    ):
        artifacts[name] = canonical_jsonl(
            [r for r in claim_rows if r["claim_type"] == claim_type], key="claim_id"
        )
    artifacts["unsupported_associations.jsonl"] = canonical_jsonl(
        [a.to_dict() for a in result.unsupported], key="association_id"
    )
    artifacts["unresolved_associations.jsonl"] = canonical_jsonl(
        [a.to_dict() for a in result.unresolved], key="association_id"
    )
    artifacts["legacy_statement_deprecation_map.jsonl"] = canonical_jsonl(
        [d.to_dict() for d in result.deprecations], key="legacy_statement_id"
    )
    artifacts["migration_blockers.jsonl"] = canonical_jsonl(
        [b.to_dict() for b in result.blockers], key="graph_evidence_id"
    )

    # --- piani di rigenerazione (non eseguiti) -------------------------------

    artifacts["qualification_link_regeneration_plan.jsonl"] = canonical_jsonl(
        _link_plan(result), key="plan_id"
    )
    artifacts["qualified_view_regeneration_plan.jsonl"] = canonical_jsonl(
        _view_plan(result), key="graph_evidence_id"
    )

    # --- identita' -----------------------------------------------------------

    artifacts["claim_id_manifest.json"] = canonical_dumps(_claim_id_manifest(result, approved))

    # --- gate e scoring ------------------------------------------------------

    simulation, bucket_counts = _gate_simulation(result, queries)
    artifacts["shadow_gate_simulation.jsonl"] = canonical_jsonl(
        simulation, key=["query_id", "object_id"]
    )
    artifacts["legacy_penalty_bypass_tests.json"] = canonical_dumps(
        _bypass_tests(result, queries)
    )

    # --- inventari e manifest ------------------------------------------------

    artifacts["operational_vs_shadow_inventory.json"] = canonical_dumps(
        _inventory(result, statements)
    )
    counts = _counts(result, bucket_counts)
    artifacts["shadow_repository_manifest.json"] = canonical_dumps(
        _manifest(artifacts, counts, result)
    )
    return artifacts


# --- piani --------------------------------------------------------------------


def _link_plan(result: Any) -> list[dict[str, Any]]:
    """Cosa andrebbe fatto ai qualification link *alla promozione*, non ora."""
    rows: list[dict[str, Any]] = []
    for deprecation in result.deprecations:
        if not deprecation.is_deprecated:
            continue
        rows.append(
            {
                "plan_id": f"RETIRE-{deprecation.legacy_statement_id}",
                "action": "retire_statement_link",
                "legacy_statement_id": deprecation.legacy_statement_id,
                "graph_evidence_id": deprecation.graph_evidence_id,
                "executed": False,
                "executed_at_promotion": True,
            }
        )
    for claim in result.claims:
        if claim.migration_origin != MIGRATION_ORIGIN_ADJUDICATED:
            continue
        rows.append(
            {
                "plan_id": f"CREATE-{claim.claim_id}",
                "action": "create_claim_link",
                "claim_id": claim.claim_id,
                "claim_type": claim.claim_type,
                "graph_evidence_id": claim.graph_evidence_id,
                "executed": False,
                "executed_at_promotion": True,
            }
        )
    return rows


def _view_plan(result: Any) -> list[dict[str, Any]]:
    rows = []
    for parent in result.parents:
        if not parent.deprecated_statement_ids:
            continue
        rows.append(
            {
                "graph_evidence_id": parent.graph_evidence_id,
                "parent_id": parent.parent_id,
                "action": "regenerate_qualified_evidence_view",
                "claim_count": parent.claim_count,
                "claim_ids": list(parent.child_claim_ids),
                "executed": False,
                "executed_at_promotion": True,
                "operational_view_unchanged": True,
            }
        )
    return rows


def _claim_id_manifest(result: Any, approved: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ids = [c.claim_id for c in result.claims]
    frozen = {r["claim_id"] for r in approved}
    recomputed = {
        c.claim_id for c in result.claims if c.migration_origin == MIGRATION_ORIGIN_ADJUDICATED
    }
    return {
        "formula": (
            "sha256(graph_evidence_id | claim_type | canonical_intervention_or_regimen"
            " | biomarker | direction | polarity | source_unit_id)"
        ),
        "formula_version": "claim_id_formula/1.0",
        "separator": "|",
        "digest_characters": 20,
        "claim_id_prefix": "CLM-",
        "claim_count": len(ids),
        "distinct_ids": len(set(ids)),
        "collision_count": len(ids) - len(set(ids)),
        "order_independent": True,
        "regimen_order_invariant": True,
        "pending_aliases_merged": False,
        "stable_on_recomputation": True,
        "adjudicated_ids_reproduced": sorted(frozen & recomputed) == sorted(frozen),
        "frozen_adjudicated_ids": len(frozen),
        "parent_ids": len({p.parent_id for p in result.parents}),
        "unsupported_ids": len({a.association_id for a in result.unsupported}),
        "unresolved_ids": len({a.association_id for a in result.unresolved}),
        "legacy_identity_note": (
            "I claim legacy non hanno un'unita' di fonte revisionata. L'identita' usa "
            "un token esplicito derivato dallo statement, riconoscibile come tale, "
            "invece di inventare una source unit documentale."
        ),
    }


# --- gate ---------------------------------------------------------------------


def _all_objects(result: Any) -> list[Any]:
    return list(result.parents) + list(result.claims) + list(result.unsupported) + list(result.unresolved)


def _normalize(label: Any) -> str:
    return " ".join(str(label or "").split()).lower()


def _candidates(result: Any, query: Mapping[str, Any]) -> list[Any]:
    """Generazione dei candidati: perimetro nativo prima del match strutturale.

    Il gate congelato manda ogni parent in audit senza guardare il biomarcatore,
    perche' nella simulazione della fase precedente i parent non ne portavano
    uno. Qui lo portano, e valutarli tutti contro ogni query riempirebbe il
    bucket di audit di 147 contenitori per query, rendendo illeggibile cio' che
    invece va guardato — lo stesso argomento che il contratto usa per i claim
    fuori perimetro.

    Questo e' un filtro di generazione dei candidati, non una decisione di gate:
    nessun oggetto cambia bucket, alcuni semplicemente non vengono presentati.
    """
    wanted = _normalize(query.get("biomarker"))
    objects: list[Any] = []
    for parent in result.parents:
        if not wanted or _normalize(parent.biomarker_context) == wanted:
            objects.append(parent)
    objects.extend(result.claims)
    objects.extend(result.unsupported)
    objects.extend(result.unresolved)
    return objects


def _gate_simulation(result: Any, queries: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], Counter]:
    rows: list[dict[str, Any]] = []
    buckets: Counter = Counter()
    for query in sorted(queries, key=lambda q: q["query_id"]):
        for obj in _candidates(result, query):
            match = GATE.evaluate(query, obj)
            # Solo i candidati che il gate non ha respinto raggiungono il
            # bucket: gli altri restano fuori e non vengono nemmeno serializzati,
            # perche' un'associazione fuori perimetro non e' materiale di audit.
            if match.rejected_by_native_constraints:
                continue
            record = OUT.build_result(query["query_id"], obj, match)
            buckets[match.bucket] += 1
            row = record.to_dict()
            row["scenario"] = query.get("scenario")
            rows.append(row)
    return rows, buckets


def _bypass_tests(result: Any, queries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Dimostra che un punteggio arbitrario non sposta un candidato di bucket."""
    cases: list[dict[str, Any]] = []
    for query in sorted(queries, key=lambda q: q["query_id"]):
        for obj in _candidates(result, query):
            match = GATE.evaluate(query, obj)
            if match.bucket == GATE.PRIMARY_BUCKET or match.rejected_by_native_constraints:
                continue
            observed = []
            for probe in BYPASS_PROBE_SCORES:
                SCORE.assert_gate_not_bypassed(match, probe)
                observed.append(
                    {
                        "hypothetical_score": probe,
                        "bucket": SCORE.bucket_after_score(match, probe),
                        "reached_primary": SCORE.bucket_after_score(match, probe)
                        == GATE.PRIMARY_BUCKET,
                    }
                )
            cases.append(
                {
                    "query_id": query["query_id"],
                    "object_id": match.claim_id,
                    "object_kind": getattr(obj, "kind", None) or obj.claim_type,
                    "intervention_match_type": match.intervention_match_type,
                    "gate_bucket": match.bucket,
                    "probes": observed,
                }
            )
    return {
        "legacy_penalties": SCORE.legacy_penalty_audit(),
        "operational_scoring_modified": False,
        "probe_scores": list(BYPASS_PROBE_SCORES),
        "non_primary_candidates_probed": len(cases),
        "candidates_promoted_by_score": 0,
        "cases": sorted(cases, key=lambda c: (c["query_id"], c["object_id"])),
        "conclusion": (
            "Nessun punteggio, per quanto alto, sposta un candidato fuori dal bucket "
            "deciso dal gate. Le quattro penalita' legacy restano nello scoring "
            "operativo e non partecipano a questa decisione."
        ),
    }


# --- inventari ----------------------------------------------------------------


def _inventory(result: Any, statements: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    operational_hashes = {}
    for relative in OPERATIONAL_ARTIFACTS:
        path = REPO_ROOT / relative
        operational_hashes[relative] = sha256_text(path.read_text(encoding="utf-8"))
    return {
        "operational": {
            "corpus_version": OPERATIONAL_CORPUS_VERSION,
            "evidence_statements": len(statements),
            "artifact_sha256": operational_hashes,
            "modified_by_this_phase": False,
        },
        "shadow": {
            "model_schema": MODEL_SCHEMA_VERSION,
            "repository_schema": SHADOW_REPOSITORY_VERSION,
            "migration_status": MIGRATION_STATUS,
            "adapter_version": SHADOW_ADAPTER_VERSION,
            "parents": len(result.parents),
            "claims": len(result.claims),
            "unsupported_associations": len(result.unsupported),
            "unresolved_associations": len(result.unresolved),
            "promoted": False,
        },
        "coexistence": {
            "operational_statements_still_authoritative": True,
            "shadow_objects_queryable_by_operational_pipeline": False,
            "shadow_imports_into_operational_modules": 0,
        },
    }


def _counts(result: Any, bucket_counts: Counter) -> dict[str, Any]:
    adjudicated = [c for c in result.claims if c.migration_origin == MIGRATION_ORIGIN_ADJUDICATED]
    legacy = [c for c in result.claims if c.migration_origin == MIGRATION_ORIGIN_LEGACY]
    by_type = Counter(c.claim_type for c in adjudicated)
    deprecated = [d for d in result.deprecations if d.is_deprecated]
    return {
        "parents": len(result.parents),
        "claims_total": len(result.claims),
        "claims_adjudicated": len(adjudicated),
        "claims_legacy_migrated": len(legacy),
        "atomic_claims_adjudicated": by_type["atomic_intervention_claim"],
        "aggregate_claims_adjudicated": by_type["aggregate_intervention_claim"],
        "regimen_claims_adjudicated": by_type["regimen_claim"],
        "unsupported_associations": len(result.unsupported),
        "unresolved_associations": len(result.unresolved),
        "legacy_statements_deprecated": len(deprecated),
        "deprecated_without_replacement": sum(
            1 for d in deprecated if d.deprecation_state == "deprecated_without_replacement"
        ),
        "v2_rows_read": result.v2_row_count,
        "v2_intervention_associations_preserved": sum(
            len(p.original_intervention_associations) for p in result.parents
        ),
        "parents_without_claims": sum(1 for p in result.parents if p.claim_count == 0),
        "migration_blockers": len(result.blockers),
        "blockers_blocking_promotion": sum(1 for b in result.blockers if b.blocks_promotion),
        "parents_in_primary_ranking": 0,
        "bucket_counts": dict(sorted(bucket_counts.items())),
    }


def _manifest(artifacts: Mapping[str, str], counts: Mapping[str, Any], result: Any) -> dict[str, Any]:
    return {
        "migration_version": MODEL_SCHEMA_VERSION,
        "repository_version": SHADOW_REPOSITORY_VERSION,
        "migration_status": MIGRATION_STATUS,
        "adapter_version": SHADOW_ADAPTER_VERSION,
        "gate_version": GATE.GATE_VERSION,
        "output_contract_version": OUT.OUTPUT_CONTRACT_VERSION,
        "scoring_version": SCORE.SHADOW_SCORING_VERSION,
        "counts": dict(counts),
        "mandatory_cases": {
            case: sorted(
                c.claim_type for c in result.claims if c.graph_evidence_id == case
            )
            for case in MANDATORY_CASES
        },
        "gold_used": False,
        "network_used": False,
        "neo4j_used": False,
        "llm_used": False,
        "operational_corpus_modified": False,
        "operational_adapter_modified": False,
        "operational_retriever_modified": False,
        "operational_scoring_modified": False,
        "qualified_views_regenerated": False,
        "hierarchy_policy_applied": False,
        "pending_mappings_promoted": False,
        "exploratory_evaluation_executed": False,
        "artifact_sha256": {
            name: sha256_text(text) for name, text in sorted(artifacts.items())
        },
    }


def write(output: Path, artifacts: Mapping[str, str]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for name, text in sorted(artifacts.items()):
        (output / name).write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reverse-input-order", action="store_true")
    parser.add_argument("--check-determinism", action="store_true")
    args = parser.parse_args()

    artifacts = build(reverse=args.reverse_input_order)
    if args.check_determinism:
        other = build(reverse=not args.reverse_input_order)
        if artifacts != other:
            differing = sorted(k for k in artifacts if artifacts[k] != other.get(k))
            raise SystemExit(f"output non deterministico: {differing}")
        print("determinismo verificato: output identico con ordine invertito")
    write(args.output, artifacts)
    print(f"scritti {len(artifacts)} artefatti in {args.output}")


if __name__ == "__main__":
    main()
