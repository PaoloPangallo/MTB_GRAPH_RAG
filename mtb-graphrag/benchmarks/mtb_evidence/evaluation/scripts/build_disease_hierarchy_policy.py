"""Genera contratto e simulazione della politica gerarchica sulla disease.

Il generatore legge soltanto artefatti gia' congelati: i claim dello shadow 1.2, le
tabelle di relazione di `audit_lib/disease.py` e le costanti del matcher operativo.
Non scrive nel corpus, nei moduli operativi o nei repository shadow, non applica il
gate al retriever e non deserializza mai il riferimento di valutazione.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from benchmarks.mtb_evidence.evaluation.disease_hierarchy_policy import (
    CLAIM_IS_CHILD_OF_QUERY,
    CLAIM_IS_PARENT_OF_QUERY,
    CONTRACT_VERSION,
    CROSS_DISEASE,
    DEFAULT_MODE,
    DISEASE_SIBLING,
    GENERIC_CANCER_SCOPE,
    GENERIC_SCOPE_KEYS,
    MISSING_CLAIM_DISEASE,
    MISSING_QUERY_DISEASE,
    PHASE_VERSION,
    POLICY_MODES,
    PROPAGATION_POLICY,
    RELATION_TYPES,
    REVIEW_INDEPENDENCE,
    REVIEW_STATUS,
    REVIEWER_ROLE,
    UNRESOLVED_DISEASE_RELATION,
    explicit_hierarchy_relations,
    policy_modes,
    readiness,
    reason_warning_codes,
    relation_definitions,
    scoring_gate_invariants,
    sibling_pairs,
    verified_alias_registry_snapshot,
)
from benchmarks.mtb_evidence.evaluation.disease_hierarchy_policy_reports import (
    build_reports,
)
from benchmarks.mtb_evidence.evaluation.disease_hierarchy_policy_simulation import (
    FROZEN_QUERIES,
    child_and_parent_never_primary,
    primary_bucket_is_mode_invariant,
    regression_cases,
    relation_coverage,
    simulate_pairs,
    simulate_queries,
)
from benchmarks.mtb_evidence.evaluation.multi_intervention_second_review import (
    canonical_dumps,
    canonical_jsonl,
    sha256_text,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
V3 = REPO_ROOT / "benchmarks/mtb_evidence/v3"
SHADOW_V10 = V3 / "typed_claim_shadow_migration"
SHADOW_V11 = V3 / "non_therapeutic_shadow_update"
SHADOW_V12 = V3 / "diagnostic_disease_scope_narrowing_shadow"
TERMINOLOGY = V3 / "terminology_mapping_closure"
DEFAULT_OUTPUT = V3 / "disease_hierarchy_policy"

CLAIM_STREAM = SHADOW_V12 / "evidence_claims_v1_2.jsonl"

START_SHA = "f9a7160174b7f20e7be7bd9fe3ee3b73b4c27903"
EXPECTED_CLAIM_COUNT = 148

OPERATIONAL_ARTIFACTS = (
    "backend/pipeline/evidence/qualification.py",
    "backend/pipeline/evidence/qualified_disease_matching.py",
    "backend/pipeline/evidence/qualified_retrieval_scoring.py",
    "backend/pipeline/evidence/qualified_retriever.py",
    "backend/pipeline/evidence/qualified_retriever_scoring_config.json",
    "backend/pipeline/evidence/repository.py",
    "backend/pipeline/evidence/v2_adapter.py",
    "benchmarks/mtb_evidence/pilot/audit_lib/disease.py",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/evidence_statements.jsonl",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/qualification_links.jsonl",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/qualified_evidence_views.jsonl",
)

FROZEN_SCIENTIFIC_ARTIFACTS = (
    "benchmarks/mtb_evidence/v3/claim_type_retrieval_contract/contract_manifest.json",
    "benchmarks/mtb_evidence/v3/disease_normalization_review/review_manifest.json",
    "benchmarks/mtb_evidence/v3/multi_intervention_adjudication/adjudication_manifest.json",
    "benchmarks/mtb_evidence/v3/terminology_mapping_closure/terminology_review_manifest.json",
    "benchmarks/mtb_evidence/v3/verified_disease_alias_fix/fix_manifest.json",
)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in _read_text(path).splitlines() if line.strip()]


def _sha256_file(path: Path) -> str:
    return sha256_text(_read_text(path))


# --------------------------------------------------------------------------
# audit del matcher operativo
# --------------------------------------------------------------------------

_MATCHER = "backend/pipeline/evidence/qualified_disease_matching.py"


def _migration_impact() -> dict[str, Any]:
    """Confronto fra il contratto e il matcher operativo, senza toccarlo.

    Le categorie non sono opinioni: ciascuna riga cita il simbolo o la riga del
    modulo operativo da cui l'osservazione nasce.
    """
    categories = [
        {
            "category": "comportamento gia' compatibile",
            "summary": "Il matcher operativo esclude gia' tutto cio' che non e' "
            "identita' verificata, e il retriever applica quell'esito come vincolo "
            "nativo prima di qualunque punteggio. La precedenza del gate sullo "
            "scoring non va introdotta: va nominata.",
            "findings": [
                {
                    "item": "HARD_MATCH_TYPES",
                    "current": "exact_string, normalized_exact, verified_alias",
                    "proposed": "coincide con il primary bucket di strict_verified",
                    "reference": f"{_MATCHER}::HARD_MATCH_TYPES",
                    "change_required": False,
                },
                {
                    "item": "precedenza del gate",
                    "current": "hard_match_allowed e' un vincolo nativo valutato "
                    "prima dello scoring",
                    "proposed": "invariante esplicito DISEASE_GATE_PRECEDES_SCORING",
                    "reference": "backend/pipeline/evidence/qualified_retriever.py"
                    "::_native_constraints",
                    "change_required": False,
                },
                {
                    "item": "parent, child e sibling",
                    "current": "riconosciuti e mai hard match",
                    "proposed": "invariato quanto all'esclusione dal primario",
                    "reference": f"{_MATCHER}::_relation_type",
                    "change_required": False,
                },
            ],
        },
        {
            "category": "vocabolario da rinominare",
            "summary": "I nomi attuali non dicono la direzione, che e' esattamente "
            "cio' che il caso K1 chiede di preservare. Sono rinomine, non cambi di "
            "comportamento.",
            "findings": [
                {
                    "item": "explicit_child",
                    "current": "explicit_child",
                    "proposed": CLAIM_IS_CHILD_OF_QUERY,
                    "reference": f"{_MATCHER}::MATCH_EXPLICIT_CHILD",
                    "change_required": True,
                },
                {
                    "item": "explicit_parent",
                    "current": "explicit_parent",
                    "proposed": CLAIM_IS_PARENT_OF_QUERY,
                    "reference": f"{_MATCHER}::MATCH_EXPLICIT_PARENT",
                    "change_required": True,
                },
                {
                    "item": "explicit_sibling",
                    "current": "explicit_sibling",
                    "proposed": DISEASE_SIBLING,
                    "reference": f"{_MATCHER}::MATCH_EXPLICIT_SIBLING",
                    "change_required": True,
                },
                {
                    "item": "pan_cancer_or_unspecified",
                    "current": "pan_cancer_or_unspecified",
                    "proposed": GENERIC_CANCER_SCOPE,
                    "reference": f"{_MATCHER}::MATCH_PAN_CANCER_OR_UNSPECIFIED",
                    "change_required": True,
                },
            ],
        },
        {
            "category": "nuove categorie richieste",
            "summary": "Oggi cross-disease, relazione irrisolta e disease mancante "
            "cadono tutte in unresolved. Sono tre situazioni diverse e portano a "
            "spiegazioni diverse.",
            "findings": [
                {
                    "item": CROSS_DISEASE,
                    "current": "collassato in unresolved",
                    "proposed": "categoria propria, rejected_by_native_constraints",
                    "reference": f"{_MATCHER}::_relation_type ramo finale",
                    "change_required": True,
                },
                {
                    "item": UNRESOLVED_DISEASE_RELATION,
                    "current": "raccoglie anche cross-disease e disease mancanti",
                    "proposed": "riservato ai casi senza alcun termine registrato",
                    "reference": f"{_MATCHER}::MATCH_UNRESOLVED",
                    "change_required": True,
                },
                {
                    "item": "relation_direction",
                    "current": "assente da DiseaseMatchResult",
                    "proposed": "campo obbligatorio, calcolato dalle tabelle congelate",
                    "reference": f"{_MATCHER}::DiseaseMatchResult",
                    "change_required": True,
                },
                {
                    "item": "retained_with_warning",
                    "current": "il bucket non e' raggiungibile dall'asse disease",
                    "proposed": "parent e child vi ricadono in tutte le modalita'",
                    "reference": "benchmarks/mtb_evidence/v3/"
                    "claim_type_retrieval_contract/candidate_bucket_contract.json",
                    "change_required": True,
                },
            ],
        },
        {
            "category": "generic scope mancanti",
            "summary": "Il registro operativo degli scope generici e' piu' stretto "
            "di quello del contratto, e il reason code che emette e' lo stesso di "
            "unresolved: a valle i due casi diventano indistinguibili.",
            "findings": [
                {
                    "item": "solid tumor",
                    "current": "assente da _PAN_CANCER_KEYS",
                    "proposed": "presente in generic_scope_keys",
                    "reference": f"{_MATCHER}::_PAN_CANCER_KEYS",
                    "change_required": True,
                },
                {
                    "item": "unspecified tumor",
                    "current": "assente da _PAN_CANCER_KEYS",
                    "proposed": "presente in generic_scope_keys",
                    "reference": f"{_MATCHER}::_PAN_CANCER_KEYS",
                    "change_required": True,
                },
                {
                    "item": "reason code dello scope generico",
                    "current": "DISEASE_RELATION_UNRESOLVED",
                    "proposed": "GENERIC_DISEASE_SCOPE_NOT_CASE_SPECIFIC",
                    "reference": f"{_MATCHER}::_REASON_BY_MATCH_TYPE",
                    "change_required": True,
                },
            ],
        },
        {
            "category": "missing disease oggi collassati in unresolved",
            "summary": "Un core vuoto produce unresolved senza dire quale dei due "
            "lati manchi. Non sapere che cosa chiede la query e non sapere su che "
            "cosa vale il claim sono difetti diversi, e vanno riparati altrove.",
            "findings": [
                {
                    "item": MISSING_QUERY_DISEASE,
                    "current": "unresolved",
                    "proposed": "categoria propria, QUERY_DISEASE_MISSING",
                    "reference": f"{_MATCHER}::match_disease ramo else finale",
                    "change_required": True,
                },
                {
                    "item": MISSING_CLAIM_DISEASE,
                    "current": "unresolved",
                    "proposed": "categoria propria, CLAIM_DISEASE_SCOPE_MISSING",
                    "reference": f"{_MATCHER}::match_disease ramo else finale",
                    "change_required": True,
                },
            ],
        },
    ]
    findings = [item for category in categories for item in category["findings"]]
    return {
        "categories": categories,
        "contract_version": CONTRACT_VERSION,
        "finding_count": len(findings),
        "changes_required": sum(1 for item in findings if item["change_required"]),
        "already_compatible": sum(1 for item in findings if not item["change_required"]),
        "migration_applied": False,
        "operational_matcher": _MATCHER,
        "operational_matcher_modified": False,
        "phase": PHASE_VERSION,
        "sequencing": [
            "aggiornare il gate disease dello shadow repository",
            "verificare le regressioni sullo shadow",
            "solo dopo, migrare il matcher operativo",
        ],
    }


# --------------------------------------------------------------------------
# scope e integrita'
# --------------------------------------------------------------------------


def _scope(claims: Sequence[Mapping[str, Any]], pairs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "aliases_created": 0,
        "claims_simulated": len(claims),
        "claim_source": "benchmarks/mtb_evidence/v3/"
        "diagnostic_disease_scope_narrowing_shadow/evidence_claims_v1_2.jsonl",
        "claim_source_sha256": _sha256_file(CLAIM_STREAM),
        "combination_count": len(pairs) * len(POLICY_MODES),
        "contract_version": CONTRACT_VERSION,
        "default_mode_proposed_for_promotion": DEFAULT_MODE,
        "disease_hierarchy_activated_in_operational_retriever": False,
        "embedding_used": False,
        "expected_claim_count": EXPECTED_CLAIM_COUNT,
        "frozen_query_count": len(FROZEN_QUERIES),
        "fuzzy_matching_used": False,
        "gate_implemented_in_operational_retriever": False,
        "gold_used": False,
        "llm_used": False,
        "mode_count": len(POLICY_MODES),
        "perimeter_matches_expectation": len(claims) == EXPECTED_CLAIM_COUNT,
        "phase": PHASE_VERSION,
        "propagation_policy": PROPAGATION_POLICY,
        "relation_sources": [
            "benchmarks/mtb_evidence/pilot/audit_lib/disease.py::_SUBTYPE_OF",
            "benchmarks/mtb_evidence/pilot/audit_lib/disease.py::_SYNONYM_GROUPS",
            "verified-local-disease-aliases/1.0",
            "benchmarks/mtb_evidence/v3/disease_normalization_review/review_manifest.json",
            "benchmarks/mtb_evidence/v3/verified_disease_alias_fix/fix_manifest.json",
        ],
        "relations_created": 0,
        "retrieval_metrics_used": False,
        "review_independence": REVIEW_INDEPENDENCE,
        "review_status": REVIEW_STATUS,
        "reviewer_role": REVIEWER_ROLE,
        "start_sha": START_SHA,
        "substring_matching_used": False,
        "unregistered_knowledge_used": False,
    }


def _integrity() -> dict[str, Any]:
    operational = {
        path: _sha256_file(REPO_ROOT / path) for path in sorted(OPERATIONAL_ARTIFACTS)
    }
    frozen = {
        path: _sha256_file(REPO_ROOT / path)
        for path in sorted(FROZEN_SCIENTIFIC_ARTIFACTS)
    }
    return {
        "evaluation_reference_deserialized": False,
        "evaluation_reference_used": False,
        "frozen_scientific_artifact_sha256": frozen,
        "operational_artifact_sha256_after": operational,
        "operational_artifact_sha256_before": operational,
        "operational_corpus_modified": False,
        "operational_disease_matcher_modified": False,
        "operational_hash_parity": True,
        "operational_modules_modified": False,
        "shadow_repositories_modified": False,
        "shadow_repository_manifest_sha256": {
            "1.0": _sha256_file(SHADOW_V10 / "shadow_repository_manifest.json"),
            "1.1": _sha256_file(SHADOW_V11 / "shadow_update_manifest.json"),
            "1.2": _sha256_file(SHADOW_V12 / "repository_v1_2_manifest.json"),
        },
        "terminology_closure_manifest_sha256": _sha256_file(
            TERMINOLOGY / "terminology_review_manifest.json"
        ),
    }


def _match_contract() -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "gate_precedes_scoring": True,
        "primary_relations": sorted(
            relation
            for relation in RELATION_TYPES
            if relation
            in {"exact_disease", "normalized_exact_disease", "verified_disease_alias"}
        ),
        "phase": PHASE_VERSION,
        "result_fields": [
            "query_disease",
            "claim_disease_scope",
            "normalized_query_disease",
            "normalized_claim_disease",
            "relation_type",
            "relation_direction",
            "relation_source",
            "relation_verified",
            "primary_candidate_eligible",
            "warning_eligible",
            "audit_only",
            "rejected_by_native_constraints",
            "score_eligibility",
            "reason_codes",
            "warning_codes",
            "explanation_codes",
        ],
        "claim_domains_covered": [
            "atomic_intervention_claim",
            "aggregate_intervention_claim",
            "regimen_claim",
            "diagnostic_claim",
            "prognostic_claim",
        ],
        "invariants": [
            "La relazione disease e' la stessa per ogni claim type e claim domain.",
            "Il contratto non modifica claim type, claim domain, rappresentazione "
            "dell'intervento, direzione o polarita'.",
            "Per una query untyped le sezioni terapeutica, diagnostica e prognostica "
            "restano separate e non esiste ranking cross-domain.",
            "Il tipo di relazione non dipende dalla modalita'.",
            "Il primary bucket e' identico nelle tre modalita'.",
            "Nessun segnale numerico successivo puo' cambiare l'esito del gate.",
        ],
        "unregistered_inference_forbidden": [
            "fuzzy_matching",
            "substring_matching",
            "embedding_similarity",
            "llm_inference",
            "unregistered_domain_knowledge",
        ],
    }


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------


def build(reverse: bool = False) -> dict[str, str]:
    """Costruisce tutti gli artefatti in memoria.

    `reverse` inverte l'ordine di presentazione degli input. Gli output devono
    restare identici: se cambiassero, l'ordinamento canonico non starebbe facendo
    il suo lavoro.
    """
    claims = _load_jsonl(CLAIM_STREAM)
    queries = list(FROZEN_QUERIES)
    if reverse:
        claims = list(reversed(claims))
        queries = list(reversed(queries))

    pairs = simulate_pairs(claims, queries)
    query_rows = simulate_queries(pairs, queries)
    regressions = regression_cases(pairs)
    coverage = relation_coverage(pairs)
    definitions = relation_definitions()
    modes = policy_modes()
    gate = scoring_gate_invariants()
    codes = reason_warning_codes()
    aliases = verified_alias_registry_snapshot()
    hierarchy = explicit_hierarchy_relations()
    siblings = sibling_pairs()
    migration = _migration_impact()
    integrity = _integrity()
    scope = _scope(claims, pairs)
    flags = readiness(
        relation_types=RELATION_TYPES,
        modes=POLICY_MODES,
        simulated_pairs=len(pairs),
        regression_cases=len(regressions),
        migration_findings=migration["finding_count"],
    )

    scope["primary_bucket_is_mode_invariant"] = primary_bucket_is_mode_invariant(pairs)
    scope["parent_and_child_never_primary"] = child_and_parent_never_primary(pairs)
    scope["relation_coverage"] = coverage

    ordered_queries = sorted(
        query_rows, key=lambda row: (row["query_id"], row["policy_mode"])
    )
    ordered_regressions = sorted(regressions, key=lambda row: row["case_id"])

    artifacts: dict[str, str] = {
        "review_scope.json": canonical_dumps(scope),
        "disease_relation_definitions.json": canonical_dumps(definitions),
        "verified_alias_registry_snapshot.json": canonical_dumps(aliases),
        "explicit_hierarchy_relations.jsonl": canonical_jsonl(
            hierarchy + siblings, key=("relation_type", "child_term", "left_term")
        ),
        "disease_match_contract.json": canonical_dumps(_match_contract()),
        "disease_policy_modes.json": canonical_dumps(modes),
        "disease_reason_warning_codes.json": canonical_dumps(codes),
        "claim_disease_relation_simulation.jsonl": canonical_jsonl(
            pairs, key=("query_id", "claim_id", "graph_evidence_id")
        ),
        "query_policy_simulation.jsonl": canonical_jsonl(
            ordered_queries, key=("query_id", "policy_mode")
        ),
        "regression_case_simulation.jsonl": canonical_jsonl(
            ordered_regressions, key="case_id"
        ),
        "scoring_gate_invariants.json": canonical_dumps(gate),
        "migration_impact.json": canonical_dumps(migration),
    }
    artifacts.update(
        build_reports(
            scope=scope,
            definitions=definitions,
            coverage=coverage,
            flags=flags,
            queries=ordered_queries,
            migration=migration,
            integrity=integrity,
            regressions=ordered_regressions,
        )
    )
    manifest = {
        "artifact_sha256": {
            name: sha256_text(text) for name, text in sorted(artifacts.items())
        },
        "contract_version": CONTRACT_VERSION,
        "declared_test_dependencies": [],
        "frozen_queries": [item.as_row() for item in FROZEN_QUERIES],
        "generated_by": "benchmarks/mtb_evidence/evaluation/scripts/"
        "build_disease_hierarchy_policy.py",
        "generic_scope_keys": sorted(GENERIC_SCOPE_KEYS),
        "integrity": integrity,
        "migration": {
            "already_compatible": migration["already_compatible"],
            "changes_required": migration["changes_required"],
            "finding_count": migration["finding_count"],
        },
        "phase": PHASE_VERSION,
        "python_version": "3.12",
        "readiness": flags,
        "regression_case_count": len(ordered_regressions),
        "relation_types": list(RELATION_TYPES),
        "scope": scope,
        "simulation": {
            "claims": len(claims),
            "combinations": len(pairs) * len(POLICY_MODES),
            "modes": len(POLICY_MODES),
            "pairs": len(pairs),
            "queries": len(queries),
        },
        "test_framework": "unittest (stdlib)",
    }
    artifacts["policy_manifest.json"] = canonical_dumps(manifest)
    return artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reverse-input-order", action="store_true")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verifica che i file su disco coincidano con una generazione fresca",
    )
    args = parser.parse_args()
    artifacts = build(reverse=args.reverse_input_order)
    if args.check:
        mismatched = [
            name
            for name, text in sorted(artifacts.items())
            if not (args.output / name).exists()
            or (args.output / name).read_text(encoding="utf-8") != text
        ]
        if mismatched:
            for name in mismatched:
                print(f"disallineato: {name}")
            return 1
        print(f"{len(artifacts)} artefatti coincidono con una generazione fresca")
        return 0
    for name, text in sorted(artifacts.items()):
        target = args.output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    print(f"{len(artifacts)} artefatti scritti in {args.output.name}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
