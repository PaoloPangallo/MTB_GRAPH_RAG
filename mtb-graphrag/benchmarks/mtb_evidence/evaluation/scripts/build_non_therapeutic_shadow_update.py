"""Genera il repository shadow 1.1 con i domini diagnostico e prognostico.

Scrive in un percorso versionato nuovo e non sovrascrive il repository 1.0, che
resta byte per byte quello emesso. Non tocca corpus, adapter, retriever o
scoring operativi; non legge il gold; non recupera full text; non risolve
mapping terminologici; non applica la disease hierarchy policy.

Deterministico: output ordinati per chiave dichiarata, e con
`--reverse-input-order` ingressi e query vengono letti al contrario e il
risultato deve restare byte-identico.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from backend.pipeline.evidence.shadow import domain_gates as GATE
from backend.pipeline.evidence.shadow import shadow_output_v11 as OUT
from backend.pipeline.evidence.shadow.domain import (
    CLAIM_DOMAINS,
    DOMAIN_DIAGNOSTIC,
    DOMAIN_PROGNOSTIC,
    DOMAIN_THERAPEUTIC,
)
from backend.pipeline.evidence.shadow.identity import (
    NON_THERAPEUTIC_CLAIM_ID_FORMULA_VERSION,
    non_therapeutic_identity_payload,
)
from backend.pipeline.evidence.shadow.migration import migrate
from backend.pipeline.evidence.shadow.migration_v11 import (
    MIGRATION_VERSION,
    NO_CLAIM_REASON,
    UNRESOLVED_REASON,
    upgrade,
)
from backend.pipeline.evidence.shadow.schema import (
    MIGRATION_STATUS,
    MODEL_SCHEMA_VERSION,
    MODEL_SCHEMA_VERSION_V11,
    OUTPUT_CONTRACT_VERSION_V11,
    SHADOW_REPOSITORY_VERSION,
    SHADOW_REPOSITORY_VERSION_V11,
    STRUCTURAL_GATE_VERSION_V11,
)
from benchmarks.mtb_evidence.evaluation.multi_intervention_second_review import (
    canonical_dumps,
    canonical_jsonl,
    sha256_text,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
V3 = REPO_ROOT / "benchmarks/mtb_evidence/v3"
ADJ = V3 / "multi_intervention_adjudication"
CORPUS = V3 / "qualification_corpus_v2"
ADAPTER_REVIEW = V3 / "multi_intervention_adapter_review"
SHADOW_V10 = V3 / "typed_claim_shadow_migration"
CONTRACT = V3 / "non_therapeutic_claim_contract_and_erratum"
DATA = REPO_ROOT / "benchmarks/mtb_evidence/evaluation/data"
DEFAULT_OUTPUT = V3 / "non_therapeutic_shadow_update"

OPERATIONAL_ARTIFACTS = (
    "backend/pipeline/evidence/v2_adapter.py",
    "backend/pipeline/evidence/repository.py",
    "backend/pipeline/evidence/qualified_retriever.py",
    "backend/pipeline/evidence/qualified_retrieval_scoring.py",
    "backend/pipeline/evidence/qualified_retriever_scoring_config.json",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/evidence_statements.jsonl",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/qualification_links.jsonl",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/qualified_evidence_views.jsonl",
    "benchmarks/mtb_evidence/v3/v2_v3a_exploratory_pilot/frozen_v2_results.jsonl",
)

FGFR2_BICC1 = "FGFR2::BICC1 Fusion"
FGFR2_AHCYL1 = "FGFR2::AHCYL1 Fusion"
CHOLANGIO = "Cholangiocarcinoma"

# Le otto query richieste dalla fase. Coprono ogni combinazione di dominio che
# deve restare separata, piu' i due casi limite: query senza intervento ma con
# dominio terapeutico, e query senza dominio.
SHADOW_QUERIES: tuple[dict[str, Any], ...] = (
    {
        "query_id": "D01",
        "scenario": "diagnostic_query_fgfr2_bicc1",
        "query_domain": "diagnostic_evidence_query",
        "disease": CHOLANGIO,
        "biomarker": FGFR2_BICC1,
        "polarity": "supports",
        "interventions": [],
    },
    {
        "query_id": "D02",
        "scenario": "diagnostic_query_fgfr2_ahcyl1",
        "query_domain": "diagnostic_evidence_query",
        "disease": CHOLANGIO,
        "biomarker": FGFR2_AHCYL1,
        "polarity": "supports",
        "interventions": [],
    },
    {
        "query_id": "T01",
        "scenario": "therapeutic_query_on_the_same_fusions",
        "query_domain": "therapeutic_evidence_query",
        "disease": CHOLANGIO,
        "biomarker": FGFR2_BICC1,
        "direction": "sensitivity",
        "polarity": "supports",
        "interventions": ["pd173074"],
    },
    {
        "query_id": "P01",
        "scenario": "prognostic_query_evidence_347",
        "query_domain": "prognostic_evidence_query",
        "disease": "Lung Non-small Cell Carcinoma",
        "biomarker": "EGFR L858R",
        "polarity": "supports",
        "interventions": [],
    },
    {
        "query_id": "U01",
        "scenario": "untyped_query_on_fgfr2_fusions",
        "query_domain": None,
        "disease": CHOLANGIO,
        "biomarker": FGFR2_BICC1,
        "polarity": "supports",
        "interventions": [],
    },
    {
        "query_id": "T02",
        "scenario": "therapeutic_query_egfr_l858r",
        "query_domain": "therapeutic_evidence_query",
        "disease": "Lung Non-small Cell Carcinoma",
        "biomarker": "EGFR L858R",
        "direction": "sensitivity",
        "polarity": "supports",
        "interventions": ["gefitinib"],
    },
    {
        "query_id": "T03",
        "scenario": "therapeutic_domain_without_intervention",
        "query_domain": "therapeutic_evidence_query",
        "disease": "Lung Non-small Cell Carcinoma",
        "biomarker": "EGFR L858R",
        "direction": "sensitivity",
        "polarity": "supports",
        "interventions": [],
    },
    {
        "query_id": "U02",
        "scenario": "query_without_domain",
        "query_domain": None,
        "disease": "Lung Non-small Cell Carcinoma",
        "biomarker": "EGFR L858R",
        "polarity": "supports",
        "interventions": [],
    },
)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def run_migration(reverse: bool = False):
    v2_rows = load_jsonl(ADAPTER_REVIEW / "intervention_lineage.jsonl")
    statements = load_jsonl(CORPUS / "evidence_statements.jsonl")
    approved = load_jsonl(ADJ / "approved_claim_simulation.jsonl")
    unsupported = load_jsonl(ADJ / "unsupported_associations.jsonl")
    unresolved = load_jsonl(ADJ / "unresolved_associations.jsonl")
    packets = load_jsonl(ADJ / "packet_adjudications.jsonl")
    audit = load_jsonl(DATA / "non_therapeutic_audit_v1.jsonl")
    if reverse:
        v2_rows, statements, approved = (
            list(reversed(v2_rows)),
            list(reversed(statements)),
            list(reversed(approved)),
        )
        unsupported, unresolved = list(reversed(unsupported)), list(reversed(unresolved))
        packets, audit = list(reversed(packets)), list(reversed(audit))

    base = migrate(
        v2_rows=v2_rows,
        statements=statements,
        approved_claims=approved,
        unsupported_records=unsupported,
        unresolved_records=unresolved,
        adjudicated_graph_evidence_ids=[p["graph_evidence_id"] for p in packets],
    )
    return upgrade(base, audit)


def _claim_row(claim: Any) -> dict[str, Any]:
    """Serializzazione 1.1 di un claim, con il dominio esplicito per tutti."""
    payload = claim.to_dict()
    payload.setdefault("claim_domain", DOMAIN_THERAPEUTIC)
    payload["schema_version"] = MODEL_SCHEMA_VERSION_V11
    return payload


def build(reverse: bool = False) -> dict[str, str]:
    result = run_migration(reverse)
    queries = list(reversed(SHADOW_QUERIES)) if reverse else list(SHADOW_QUERIES)

    artifacts: dict[str, str] = {}

    artifacts["graph_evidence_parents_v1_1.jsonl"] = canonical_jsonl(
        [p.to_dict() | {"schema_version": MODEL_SCHEMA_VERSION_V11} for p in result.parents],
        key="graph_evidence_id",
    )
    claim_rows = [_claim_row(c) for c in result.evidence_claims]
    artifacts["evidence_claims_v1_1.jsonl"] = canonical_jsonl(claim_rows, key="claim_id")
    artifacts["therapeutic_claims_v1_1.jsonl"] = canonical_jsonl(
        [r for r in claim_rows if r["claim_domain"] == DOMAIN_THERAPEUTIC], key="claim_id"
    )
    artifacts["diagnostic_claims_v1_1.jsonl"] = canonical_jsonl(
        [r for r in claim_rows if r["claim_domain"] == DOMAIN_DIAGNOSTIC], key="claim_id"
    )
    artifacts["prognostic_claims_v1_1.jsonl"] = canonical_jsonl(
        [r for r in claim_rows if r["claim_domain"] == DOMAIN_PROGNOSTIC], key="claim_id"
    )
    artifacts["parent_without_claim_v1_1.jsonl"] = canonical_jsonl(
        list(result.parents_without_claims), key="graph_evidence_id"
    )
    artifacts["legacy_statement_deprecation_map_v1_1.jsonl"] = canonical_jsonl(
        [d.to_dict(include_promotion_status=True) for d in result.deprecations],
        key="legacy_statement_id",
    )
    artifacts["qualification_link_regeneration_plan_v1_1.jsonl"] = canonical_jsonl(
        _link_plan(result), key="plan_id"
    )
    artifacts["qualified_view_regeneration_plan_v1_1.jsonl"] = canonical_jsonl(
        _view_plan(result), key="plan_id"
    )

    simulation, sectioned = _gate_simulation(result, queries)
    artifacts["claim_domain_gate_simulation.jsonl"] = canonical_jsonl(
        simulation, key=["query_id", "object_id"]
    )
    artifacts["untyped_sectioned_output_simulation.json"] = canonical_dumps(sectioned)
    artifacts["evidence_347_promotion_audit.json"] = canonical_dumps(_audit_347(result))
    artifacts["repository_version_lineage.json"] = canonical_dumps(_lineage())
    artifacts["shadow_update_manifest.json"] = canonical_dumps(
        _manifest(artifacts, result, simulation)
    )
    return artifacts


# --- piani --------------------------------------------------------------------


def _link_plan(result: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for deprecation in result.deprecations:
        if not deprecation.is_deprecated:
            continue
        rows.append(
            {
                "plan_id": f"RETIRE-LINK-{deprecation.legacy_statement_id}",
                "action": "retire_statement_link",
                "legacy_statement_id": deprecation.legacy_statement_id,
                "graph_evidence_id": deprecation.graph_evidence_id,
                "deprecation_state": deprecation.deprecation_state,
                "blocks_promotion": deprecation.blocks_promotion,
                "executed": False,
                "executed_at_promotion": True,
            }
        )
    for claim in result.evidence_claims:
        domain = getattr(claim, "claim_domain", DOMAIN_THERAPEUTIC)
        origin = getattr(claim, "migration_origin", None)
        # I link terapeutici da creare sono quelli dei claim adjudicati; i legacy
        # migrati portano avanti il proprio e non ne generano di nuovi.
        if domain == DOMAIN_THERAPEUTIC and origin != "adjudicated_review":
            continue
        rows.append(
            {
                "plan_id": f"CREATE-LINK-{claim.claim_id}",
                "action": "create_claim_link",
                "claim_id": claim.claim_id,
                "claim_domain": domain,
                "claim_type": claim.claim_type,
                "graph_evidence_id": claim.graph_evidence_id,
                "source_unit_ids": list(claim.source_unit_ids),
                "locator_count": len(claim.locators),
                # Un link diagnostico non riusa un link terapeutico: le due cose
                # qualificano affermazioni diverse.
                "reuses_therapeutic_link": False,
                "clinical_qualifiers_invented": False,
                "executed": False,
                "executed_at_promotion": True,
            }
        )
    return rows


def _view_plan(result: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for parent in result.parents:
        if not parent.deprecated_statement_ids:
            continue
        domains = sorted(
            {
                getattr(c, "claim_domain", DOMAIN_THERAPEUTIC)
                for c in result.evidence_claims
                if c.graph_evidence_id == parent.graph_evidence_id
            }
        )
        rows.append(
            {
                "plan_id": f"VIEW-{parent.graph_evidence_id}",
                "graph_evidence_id": parent.graph_evidence_id,
                "parent_id": parent.parent_id,
                "action": "regenerate_qualified_evidence_view"
                if domains
                else "retire_qualified_evidence_view",
                "claim_count": len(parent.child_claim_ids),
                "claim_domains": domains,
                "executed": False,
                "executed_at_promotion": True,
                "operational_view_unchanged": True,
            }
        )
    for record in result.parents_without_claims:
        if not record["legacy_statement_ids"]:
            continue
        if any(r["graph_evidence_id"] == record["graph_evidence_id"] for r in rows):
            continue
        rows.append(
            {
                "plan_id": f"VIEW-{record['graph_evidence_id']}",
                "graph_evidence_id": record["graph_evidence_id"],
                "parent_id": record["parent_id"],
                "action": "retire_qualified_evidence_view",
                "claim_count": 0,
                "claim_domains": [],
                "executed": False,
                "executed_at_promotion": True,
                "operational_view_unchanged": True,
            }
        )
    return rows


# --- gate ---------------------------------------------------------------------


def _all_objects(result: Any) -> list[Any]:
    return (
        list(result.parents)
        + list(result.evidence_claims)
        + list(result.unsupported)
        + list(result.unresolved)
    )


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").split()).lower()


def _candidates(result: Any, query: Mapping[str, Any]) -> list[Any]:
    """Perimetro nativo prima del match, come nella simulazione 1.0."""
    wanted = _normalize(query.get("biomarker"))
    objects: list[Any] = [
        p
        for p in result.parents
        if not wanted or _normalize(p.biomarker_context) == wanted
    ]
    objects.extend(result.evidence_claims)
    objects.extend(result.unsupported)
    objects.extend(result.unresolved)
    return objects


def _gate_simulation(
    result: Any, queries: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    sectioned: dict[str, Any] = {}
    for query in sorted(queries, key=lambda q: q["query_id"]):
        results = []
        for obj in _candidates(result, query):
            match = GATE.evaluate(query, obj)
            if match.rejected_by_native_constraints:
                continue
            record = OUT.build_result(query["query_id"], obj, match)
            results.append(record)
            row = record.to_dict()
            row["scenario"] = query.get("scenario")
            rows.append(row)
        if GATE.query_domain(query) == GATE.UNTYPED_QUERY:
            sectioned[query["query_id"]] = OUT.sectioned_output(query["query_id"], results)
    return rows, {
        "contract_version": OUTPUT_CONTRACT_VERSION_V11,
        "cross_domain_ranking": False,
        "queries": dict(sorted(sectioned.items())),
    }


def _audit_347(result: Any) -> dict[str, Any]:
    record = next(
        r for r in result.parents_without_claims if r["graph_evidence_id"] == "evidence:347"
    )
    deprecation = next(
        d for d in result.deprecations if d.graph_evidence_id == "evidence:347"
    )
    return {
        "graph_evidence_id": "evidence:347",
        "parent_id": record["parent_id"],
        "source_id": record["source_id"],
        "claims_created": 0,
        "claim_types_created": [],
        "no_claim_reason": NO_CLAIM_REASON,
        "unresolved_reason": UNRESOLVED_REASON,
        "audit_status": record["audit_status"],
        "requires_full_text": record["requires_full_text"],
        "full_text_retrieved": False,
        "legacy_statement_id": deprecation.legacy_statement_id,
        "legacy_deprecation_state_before": "preserved_as_legacy_migrated_claim",
        "legacy_deprecation_state_after": deprecation.deprecation_state,
        "legacy_statement_active_before": True,
        "legacy_statement_promotable_before": True,
        "legacy_statement_promotable_after": False,
        "blocks_promotion": deprecation.blocks_promotion,
        "operational_statement_modified": False,
        "operational_statement_still_readable": True,
        "incoherence_found_at_phase_start": (
            "Lo statement legacy era attivo come claim prognostico, preservato, non "
            "deprecato e privo di qualunque decisione: la mappa 1.0 lo dichiarava "
            "'ancora valido e leggibile', affermazione che l'audit della fase "
            "precedente aveva gia' contraddetto. In una promozione sarebbe rientrato "
            "come claim prognostico recuperabile."
        ),
        "resolution": (
            "Il piano shadow lo porta a promotion_blocked_pending_full_text. Non ha un "
            "sostituto e non ne viene inventato uno; non viene nemmeno dichiarato "
            "chiuso, perche' la questione e' aperta e serve il full text di "
            "PMID:24662454."
        ),
        "provenance": dict(record["provenance"]),
    }


# --- lineage e manifest -------------------------------------------------------


def _lineage() -> dict[str, Any]:
    def folder_hash(path: Path) -> dict[str, str]:
        return {
            f.name: sha256_text(f.read_text(encoding="utf-8"))
            for f in sorted(path.iterdir())
            if f.is_file()
        }

    return {
        "lineage_version": "repository_version_lineage/1.0",
        "versions": [
            {
                "model_schema": MODEL_SCHEMA_VERSION,
                "repository_schema": SHADOW_REPOSITORY_VERSION,
                "path": "benchmarks/mtb_evidence/v3/typed_claim_shadow_migration",
                "status": "superseded_but_preserved",
                "modified_by_this_phase": False,
                "artifact_sha256": folder_hash(SHADOW_V10),
            },
            {
                "model_schema": MODEL_SCHEMA_VERSION_V11,
                "repository_schema": SHADOW_REPOSITORY_VERSION_V11,
                "path": "benchmarks/mtb_evidence/v3/non_therapeutic_shadow_update",
                "status": "current_shadow",
                "supersedes": SHADOW_REPOSITORY_VERSION,
                "promoted": False,
            },
        ],
        "rule": (
            "Una versione shadow non viene sovrascritta. La successiva vive in un "
            "percorso proprio e dichiara quale sostituisce, cosi' che entrambe "
            "restino leggibili e confrontabili."
        ),
    }


def _manifest(
    artifacts: Mapping[str, str], result: Any, simulation: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    domains = Counter(
        getattr(c, "claim_domain", DOMAIN_THERAPEUTIC) for c in result.evidence_claims
    )
    types = Counter(c.claim_type for c in result.evidence_claims)
    deprecations = result.deprecations
    retire = [d for d in deprecations if d.is_deprecated]
    replaced = [d for d in retire if d.replacement_claim_ids]
    without = [d for d in retire if not d.replacement_claim_ids]
    blocked = [d for d in deprecations if d.blocks_promotion]

    operational = {
        relative: sha256_text((REPO_ROOT / relative).read_text(encoding="utf-8"))
        for relative in OPERATIONAL_ARTIFACTS
    }

    buckets = Counter(row["bucket"] for row in simulation)
    therapy_scored_non_therapeutic = sum(
        1
        for row in simulation
        if row["claim_domain"] in (DOMAIN_DIAGNOSTIC, DOMAIN_PROGNOSTIC)
        and row["therapy_score_allowed"]
    )

    return {
        "model_schema": MODEL_SCHEMA_VERSION_V11,
        "repository_schema": SHADOW_REPOSITORY_VERSION_V11,
        "structural_gate": STRUCTURAL_GATE_VERSION_V11,
        "output_contract": OUTPUT_CONTRACT_VERSION_V11,
        "adapter_version": MIGRATION_VERSION,
        "migration_status": MIGRATION_STATUS,
        "supersedes": SHADOW_REPOSITORY_VERSION,
        "counts": {
            "parents": len(result.parents),
            "evidence_claims_total": result.total_claims,
            "therapeutic_claims": domains[DOMAIN_THERAPEUTIC],
            "diagnostic_claims": domains[DOMAIN_DIAGNOSTIC],
            "prognostic_claims": domains[DOMAIN_PROGNOSTIC],
            "by_claim_type": dict(sorted(types.items())),
            "unsupported_associations": len(result.unsupported),
            "unresolved_associations": len(result.unresolved),
            "parents_without_claims": len(result.parents_without_claims),
            "parents_without_claims_ids": sorted(
                r["graph_evidence_id"] for r in result.parents_without_claims
            ),
            "statements_to_retire": len(retire),
            "statements_with_replacement": len(replaced),
            "statements_without_replacement": len(without),
            "statements_promotion_blocked": len(blocked),
            "gate_buckets": dict(sorted(buckets.items())),
        },
        "invariants": {
            "therapy_score_on_non_therapeutic_claims": therapy_scored_non_therapeutic,
            "cross_domain_ranking": False,
            "expected_count_forced": False,
            "shadow_1_0_modified": False,
            "operational_corpus_modified": False,
            "operational_adapter_modified": False,
            "operational_retriever_modified": False,
            "operational_scoring_modified": False,
            "qualified_views_regenerated": False,
            "full_text_retrieved": False,
            "terminology_mappings_resolved": False,
            "hierarchy_policy_applied": False,
            "promoted": False,
        },
        "claim_id_formula": {
            "therapeutic": "claim_id_formula/1.0",
            "non_therapeutic": NON_THERAPEUTIC_CLAIM_ID_FORMULA_VERSION,
            "collisions": 0,
            "distinct_claim_ids": len({c.claim_id for c in result.evidence_claims}),
        },
        "operational_artifact_sha256": operational,
        "gold_used": False,
        "network_used": False,
        "neo4j_used": False,
        "llm_used": False,
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
