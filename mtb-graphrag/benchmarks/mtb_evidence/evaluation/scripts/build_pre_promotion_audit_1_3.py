"""Genera gli artefatti dell'audit pre-promozione del repository shadow 1.3.

Il generatore legge la 1.3, non la riscrive, non esegue nessun piano e non apre
il gold. Gli hash degli artefatti congelati vengono presi prima e dopo la
generazione: e' l'unica prova che un audit dichiarato read-only lo sia stato.

Nessun artefatto operativo viene toccato. La query operativa di parita' viene
rieseguita perche' il suo hash resti un fatto misurato e non una promessa.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from backend.pipeline.evidence.qualified_retrieval_query import (
    MODE_QUALIFIED_SOFT,
    QualifiedRetrievalQuery,
    QueryBiomarker,
)
from backend.pipeline.evidence.qualified_retriever import QualifiedEvidenceRetriever
from backend.pipeline.evidence.shadow import disease_gate as DISEASE
from benchmarks.mtb_evidence.evaluation.disease_hierarchy_policy import (
    DEFAULT_MODE,
    POLICY_MODES,
)
from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import (
    findings as FINDINGS,
)
from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import gate_audit as GATES
from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import (
    identity_audit as IDENTITY,
)
from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import inventory as INVENTORY
from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import (
    lineage_audit as LINEAGE,
)
from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import novelty as NOVELTY
from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import plan_audit as PLANS
from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import promotion as PROMOTION
from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import (
    provenance_audit as PROVENANCE,
)
from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import scope as SCOPE

DEFAULT_OUTPUT = SCOPE.DEFAULT_OUTPUT

CORPUS_FINGERPRINT = "99a1a575a813676bb3d2658a3ab103cf396755f4b0cdbd9a8c26f09ea6c77ffd"
OPERATIONAL_QUERY_BASELINE_SHA256 = (
    "af0389673a9a8b0566bce20bf68685b3abc04baf8542e183888d9a84cb365124"
)

SCORING_CONFIG = (
    SCOPE.REPO_ROOT / "backend/pipeline/evidence/qualified_retriever_scoring_config.json"
)


# --------------------------------------------------------------------------
# policy di default
# --------------------------------------------------------------------------


def policy_declaration(repository: Mapping[str, Any]) -> dict[str, Any]:
    """Che cosa la 1.3 dichiara, machine-readably, sulla modalita' di default.

    La domanda non e' se il codice si comporti bene: si comporta bene. E' se un
    consumatore che leggesse i soli artefatti possa saperlo. Le due cose non
    coincidono, e la seconda e' quella che sopravvive a una promozione.
    """
    manifest = repository["manifest"]
    policy = manifest.get("policy") or {}
    readiness = manifest.get("readiness") or {}

    declared_default = policy.get("default_mode")
    declared_modes = tuple(policy.get("modes") or ())

    # Il comportamento, misurato invece che assunto.
    resolved_without_declaration = DISEASE.policy_mode({})
    try:
        DISEASE.policy_mode({"disease_policy_mode": "definitely_not_a_mode"})
        rejects_unknown = False
    except DISEASE.DiseaseGateError:
        rejects_unknown = True

    return {
        "behaviour_default_mode": resolved_without_declaration,
        "behaviour_rejects_unknown_mode": rejects_unknown,
        "declared_default_mode": declared_default,
        "declared_default_mode_field": "policy.default_mode",
        "declared_modes": list(declared_modes),
        "declared_strict_policy_default_flag": bool(
            readiness.get("strict_policy_default")
        ),
        "default_matches_behaviour": declared_default == resolved_without_declaration,
        "expected_default_mode": DEFAULT_MODE,
        "fallback_to_broader_mode_declared": "fallback_to_broader_mode" in policy,
        "modes_match_contract": list(declared_modes) == list(POLICY_MODES),
        "strict_default_explicit": bool(
            declared_default == DEFAULT_MODE
            and readiness.get("strict_policy_default") is True
        ),
        "unknown_mode_rejection_declared": "unknown_policy_mode_behaviour" in policy,
        "required_pipeline_behaviour": {
            "reject_unknown_modes": True,
            "silent_fallback_to_audit_all": False,
            "silent_fallback_to_ontology_aware_warning": False,
            "use_strict_verified_when_unspecified": True,
        },
    }


# --------------------------------------------------------------------------
# integrita'
# --------------------------------------------------------------------------


def _operational_query() -> dict[str, Any]:
    """La query operativa di parita', rieseguita senza toccare nulla."""
    retriever = QualifiedEvidenceRetriever.from_corpus(
        SCOPE.CORPUS, scoring_config_path=SCORING_CONFIG
    )
    query = QualifiedRetrievalQuery(
        query_id="scope-narrowing-operational-parity",
        disease="Non-small cell lung cancer",
        disease_aliases=("Lung Non-small Cell Carcinoma",),
        biomarkers=(QueryBiomarker(gene="ALK"),),
        top_k=20,
        mode=MODE_QUALIFIED_SOFT,
        corpus_fingerprint=CORPUS_FINGERPRINT,
    )
    output = retriever.retrieve(query)
    text = (
        json.dumps(
            output.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        + "\n"
    )
    digest = SCOPE.sha256_text(text)
    return {
        "baseline_sha256": OPERATIONAL_QUERY_BASELINE_SHA256,
        "parity": digest == OPERATIONAL_QUERY_BASELINE_SHA256,
        "query_id": "scope-narrowing-operational-parity",
        "result_count": len(output.all_results),
        "sha256": digest,
    }


def integrity(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    changed: list[dict[str, Any]] = []
    for group in ("files", "trees"):
        for role, entry in sorted(before[group].items()):
            observed = after[group][role]["sha256"]
            if observed != entry["sha256"]:
                changed.append(
                    {
                        "after": observed,
                        "before": entry["sha256"],
                        "path": entry["path"],
                        "role": role,
                    }
                )
    gold = SCOPE.gold_tree_hash()
    return {
        "all_frozen_artifacts_unchanged": not changed,
        "changed": changed,
        "frozen_after": after,
        "frozen_before": before,
        "gold": gold,
        "gold_records_read": gold["gold_records_read"],
        "operational_artifacts_modified": bool(changed),
        "operational_query": _operational_query(),
    }


# --------------------------------------------------------------------------
# artefatti
# --------------------------------------------------------------------------


def audit_scope() -> dict[str, Any]:
    return {
        "audit_version": SCOPE.AUDIT_VERSION,
        "audited_repository": SCOPE.AUDITED_REPOSITORY,
        "decisions_this_phase_does_not_take": [
            "promuovere il corpus",
            "migrare il retriever operativo",
            "rieseguire l'esplorazione completa",
            "dichiarare una readiness clinica",
        ],
        "gold_used": False,
        "llm_used": False,
        "network_used": False,
        "neo4j_used": False,
        "not_modified": {
            "operational_artifacts": list(SCOPE.OPERATIONAL_ARTIFACTS),
            "shadow_repositories": sorted(SCOPE.FROZEN_SHADOW_DIRS.values()),
        },
        "phase": SCOPE.PHASE,
        "plans_executed": False,
        "promotion_applied": False,
        "propagation_policy": SCOPE.PROPAGATION_POLICY,
        "python_version": "3.12",
        "read_only": True,
        "review_independence": SCOPE.REVIEW_INDEPENDENCE,
        "review_status": SCOPE.REVIEW_STATUS,
        "reviewer_role": SCOPE.REVIEWER_ROLE,
        "start_sha": SCOPE.START_SHA,
        "test_framework": "unittest (stdlib)",
        "verifications": [
            "integrita' del modello parent/claim",
            "correttezza dei conteggi",
            "completezza della provenance",
            "coerenza degli ID e dei lineage",
            "coerenza fra claim, link e view plan",
            "composizione dei gate",
            "gestione di unsupported e unresolved",
            "comportamento su termini e relazioni mai viste",
            "compatibilita' della futura promozione",
            "rollback e reversibilita'",
        ],
    }


def readiness(
    *,
    inventory_audit: Mapping[str, Any],
    identity: Mapping[str, Any],
    lineage: Mapping[str, Any],
    provenance: Mapping[str, Any],
    plans: Mapping[str, Any],
    gates: Mapping[str, Any],
    novelty_summary: Mapping[str, Any],
    promotion_audit: Mapping[str, Any],
    policy: Mapping[str, Any],
    decision: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "backward_compatibility_plan_complete": promotion_audit[
            "backward_compatibility"
        ]["backward_compatibility_plan_complete"],
        "claim_ids_recomputable": identity["claim_ids_recomputable"],
        # La porta si apre solo con `ready_for_prototype_promotion`. Con
        # `ready_with_required_promotion_fixes` esistono correzioni che vanno
        # applicate *prima* di scrivere il corpus promosso: dichiararla aperta
        # significherebbe promuovere e correggere dopo, che e' l'ordine
        # sbagliato per entrambe le correzioni richieste.
        "corpus_promotion_ready": decision["decision"] == FINDINGS.READY,
        "corpus_promotion_ready_after_required_fixes": decision["decision"]
        in (FINDINGS.READY, FINDINGS.READY_WITH_FIXES),
        "corpus_promotion_ready_scope": (
            "readiness per una fase separata di promozione prototipale, non per "
            "un uso operativo del corpus"
        ),
        "critical_findings": decision["counts"][FINDINGS.CRITICAL],
        "false_automatic_merges": novelty_summary["false_automatic_merges"],
        "full_exploratory_rerun_ready": False,
        "gate_bypasses": gates["gate_bypasses"],
        "integrated_gate_invariants_hold": gates["integrated_gate_invariants_hold"],
        "inventory_consistent": inventory_audit["inventory_consistent"],
        "major_findings": decision["counts"][FINDINGS.MAJOR],
        "minor_findings": decision["counts"][FINDINGS.MINOR],
        "informational_findings": decision["counts"][FINDINGS.INFORMATIONAL],
        "novelty_diagnostics_complete": novelty_summary["novelty_diagnostics_complete"],
        "operational_retriever_migration_ready": False,
        "parent_claim_lineage_complete": lineage["lineage_complete"],
        "promotion_decision": decision["decision"],
        "promotion_diff_complete": promotion_audit["promotion_diff_complete"],
        "provenance_sufficient_for_prototype": provenance[
            "provenance_sufficient_for_prototype"
        ],
        "qualification_link_plan_consistent": plans["links"][
            "qualification_link_plan_consistent"
        ],
        "qualified_view_plan_consistent": plans["views"][
            "qualified_view_plan_consistent"
        ],
        "rollback_plan_complete": promotion_audit["rollback"]["rollback_plan_complete"],
        "strict_default_explicit": policy["strict_default_explicit"],
    }


def build_data_artifacts() -> dict[str, str]:
    """Tutti gli artefatti dati dell'audit, in ordine canonico."""
    before = SCOPE.frozen_hashes()
    repository = SCOPE.load_repository()

    inventory_audit = INVENTORY.audit(repository)
    reconciliation = INVENTORY.reconciliation_rows(repository)
    identity = IDENTITY.audit(repository)
    identity_rows = IDENTITY.recomputation_rows(repository)
    lineage = LINEAGE.audit(repository)
    lineage_rows = LINEAGE.lineage_rows(repository)
    provenance = PROVENANCE.audit(repository)
    provenance_rows = PROVENANCE.claim_rows(repository)
    plans = PLANS.audit(repository)
    link_rows = PLANS.link_rows(repository)
    gates = GATES.audit(repository)
    gate_rows = GATES.case_rows(repository)
    novelty_rows = NOVELTY.case_rows()
    novelty_summary = NOVELTY.summary(novelty_rows)
    promotion_audit = PROMOTION.audit(repository)
    policy = policy_declaration(repository)

    after = SCOPE.frozen_hashes()
    integrity_report = integrity(before, after)

    collected = FINDINGS.collect(
        inventory=inventory_audit,
        identity=identity,
        lineage=lineage,
        provenance=provenance,
        plans=plans,
        gates=gates,
        novelty_summary=novelty_summary,
        promotion=promotion_audit,
        policy=policy,
        integrity=integrity_report,
    )
    decision = FINDINGS.decide(
        collected,
        {
            "claim_ids_recomputable": identity["claim_ids_recomputable"],
            "frozen_artifacts_unchanged": integrity_report[
                "all_frozen_artifacts_unchanged"
            ],
            "integrated_gate_invariants_hold": gates["integrated_gate_invariants_hold"],
            "inventory_consistent": inventory_audit["inventory_consistent"],
            "lineage_complete": lineage["lineage_complete"],
            "novelty_diagnostics_complete": novelty_summary[
                "novelty_diagnostics_complete"
            ],
            "operational_query_parity": integrity_report["operational_query"]["parity"],
            "promotion_diff_complete": promotion_audit["promotion_diff_complete"],
            "qualification_link_plan_consistent": plans["links"][
                "qualification_link_plan_consistent"
            ],
            "qualified_view_plan_consistent": plans["views"][
                "qualified_view_plan_consistent"
            ],
            "rollback_plan_complete": promotion_audit["rollback"][
                "rollback_plan_complete"
            ],
            "strict_default_explicit": policy["strict_default_explicit"],
        },
    )
    readiness_report = readiness(
        inventory_audit=inventory_audit,
        identity=identity,
        lineage=lineage,
        provenance=provenance,
        plans=plans,
        gates=gates,
        novelty_summary=novelty_summary,
        promotion_audit=promotion_audit,
        policy=policy,
        decision=decision,
    )

    artifacts = {
        "audit_scope.json": SCOPE.canonical_dumps(
            audit_scope() | {"default_policy": policy}
        ),
        "repository_inventory_audit.json": SCOPE.canonical_dumps(
            inventory_audit
            | {"reconciliation_totals": INVENTORY.reconciliation_totals(reconciliation)}
        ),
        "parent_claim_reconciliation.jsonl": SCOPE.canonical_jsonl(
            reconciliation, key="graph_evidence_id"
        ),
        "claim_id_recomputation.jsonl": SCOPE.canonical_jsonl(
            identity_rows, key=["entity", "declared_id"]
        ),
        "lineage_audit.jsonl": SCOPE.canonical_jsonl(
            lineage_rows, key=["lineage_kind", "graph_evidence_id"]
        ),
        "provenance_completeness_audit.jsonl": SCOPE.canonical_jsonl(
            provenance_rows, key="claim_id"
        ),
        "qualification_link_plan_audit.json": SCOPE.canonical_dumps(
            plans["links"] | {"actions": link_rows}
        ),
        "qualified_view_plan_audit.json": SCOPE.canonical_dumps(plans["views"]),
        "integrated_gate_audit.jsonl": SCOPE.canonical_jsonl(
            gate_rows, key=["case_id", "policy_mode"]
        ),
        "novelty_handling_cases.jsonl": SCOPE.canonical_jsonl(
            novelty_rows, key=["domain", "case_id"]
        ),
        "novelty_handling_summary.json": SCOPE.canonical_dumps(novelty_summary),
        "promotion_diff_simulation.json": SCOPE.canonical_dumps(
            promotion_audit["promotion_diff"]
            | {"promotion_diff_complete": promotion_audit["promotion_diff_complete"]}
        ),
        "backward_compatibility_audit.json": SCOPE.canonical_dumps(
            promotion_audit["backward_compatibility"]
        ),
        "rollback_plan.json": SCOPE.canonical_dumps(promotion_audit["rollback"]),
        "findings.jsonl": SCOPE.canonical_jsonl(collected, key="finding_id"),
        "readiness_decision.json": SCOPE.canonical_dumps(
            decision | {"readiness": readiness_report}
        ),
    }
    manifest = {
        "artifact_sha256": {
            name: SCOPE.sha256_text(text) for name, text in sorted(artifacts.items())
        },
        "audit_version": SCOPE.AUDIT_VERSION,
        "audited_repository": SCOPE.AUDITED_REPOSITORY,
        "counts": inventory_audit["audit_derived_counts"],
        "findings": decision["counts"],
        "gold": integrity_report["gold"],
        "integrity": {
            "all_frozen_artifacts_unchanged": integrity_report[
                "all_frozen_artifacts_unchanged"
            ],
            "changed": integrity_report["changed"],
            "frozen_sha256": {
                role: entry["sha256"]
                for role, entry in sorted(integrity_report["frozen_after"]["files"].items())
            },
            "frozen_tree_sha256": {
                role: entry["sha256"]
                for role, entry in sorted(integrity_report["frozen_after"]["trees"].items())
            },
            "operational_query": integrity_report["operational_query"],
        },
        "invariants": {
            "false_automatic_merges": novelty_summary["false_automatic_merges"],
            "gate_bypasses": gates["gate_bypasses"],
            "gold_artifacts_read": 0,
            "operational_artifacts_modified": integrity_report[
                "operational_artifacts_modified"
            ],
            "plans_executed": False,
            "promotion_applied": False,
            "score_flags_leaked_outside_rankable_buckets": gates[
                "score_flags_leaked_outside_rankable_buckets"
            ],
            "shadow_1_3_modified": False,
        },
        "phase": SCOPE.PHASE,
        "policy": policy,
        "python_version": "3.12",
        "readiness": readiness_report,
        "review_independence": SCOPE.REVIEW_INDEPENDENCE,
        "review_status": SCOPE.REVIEW_STATUS,
        "reviewer_role": SCOPE.REVIEWER_ROLE,
        "start_sha": SCOPE.START_SHA,
        "test_framework": "unittest (stdlib)",
    }
    artifacts["audit_manifest.json"] = SCOPE.canonical_dumps(manifest)
    return dict(sorted(artifacts.items()))


def build() -> dict[str, str]:
    artifacts = build_data_artifacts()
    try:
        from benchmarks.mtb_evidence.evaluation.pre_promotion_audit_reports import (
            build_reports,
        )
    except ImportError:  # pragma: no cover - i report arrivano con il commit docs
        return artifacts
    return dict(sorted((artifacts | build_reports(artifacts)).items()))


def write(output: Path, artifacts: Mapping[str, str]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    unexpected = {path.name for path in output.iterdir() if path.is_file()} - set(
        artifacts
    )
    if unexpected:
        raise RuntimeError(
            f"output contiene artefatti non controllati: {sorted(unexpected)}"
        )
    for name, text in sorted(artifacts.items()):
        (output / name).write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    artifacts = build()
    write(args.output, artifacts)
    manifest = json.loads(artifacts["audit_manifest.json"])
    print(
        SCOPE.canonical_dumps(
            {
                "artifacts": len(artifacts),
                "decision": manifest["readiness"]["promotion_decision"],
                "findings": manifest["findings"],
                "output": args.output.as_posix(),
            }
        ),
        end="",
    )


if __name__ == "__main__":
    main()
