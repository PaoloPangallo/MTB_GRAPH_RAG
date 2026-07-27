"""Genera il repository shadow 1.4: correzioni richieste dall'audit pre-promozione.

La 1.4 parte dai record della 1.3 e applica soltanto cio' che l'audit ha chiesto:
schema di propagazione obbligatorio, contratto di forma dell'intervento, gate
1.1, dichiarazione sulle modalita' sconosciute e schema unico del link plan.

Non scrive nella 1.3 e non la rilegge per riscriverla: la usa come sorgente. Non
esegue nessun piano, non promuove nulla, non legge il gold. Gli hash degli
artefatti congelati vengono presi prima e dopo la generazione.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from backend.pipeline.evidence.qualified_retrieval_query import (
    MODE_QUALIFIED_SOFT,
    QualifiedRetrievalQuery,
    QueryBiomarker,
)
from backend.pipeline.evidence.qualified_retriever import QualifiedEvidenceRetriever
from backend.pipeline.evidence.shadow import formulation as FORM
from backend.pipeline.evidence.shadow import integrated_gates_v11 as GATE11
from backend.pipeline.evidence.shadow import migration_v14 as M14
from backend.pipeline.evidence.shadow import propagation as PROP
from backend.pipeline.evidence.shadow.claims import (
    AggregateInterventionClaim,
    AtomicInterventionClaim,
    RegimenClaim,
)
from benchmarks.mtb_evidence.evaluation import formulation_audit as FA
from benchmarks.mtb_evidence.evaluation import required_fixes_1_4 as FIXES
from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import scope as SCOPE

PHASE = "pre-promotion-required-fixes/1.4"
START_SHA = "29ad5250b1119ad3d70717e9a2670bd134feab16"

REPO_ROOT = SCOPE.REPO_ROOT
V3 = SCOPE.V3
SHADOW_V13 = SCOPE.SHADOW_V13
AUDIT_V13 = V3 / "pre_promotion_audit_1_3"
DEFAULT_OUTPUT = V3 / "pre_promotion_required_fixes_1_4"

CORPUS_FINGERPRINT = "99a1a575a813676bb3d2658a3ab103cf396755f4b0cdbd9a8c26f09ea6c77ffd"
OPERATIONAL_QUERY_BASELINE_SHA256 = (
    "af0389673a9a8b0566bce20bf68685b3abc04baf8542e183888d9a84cb365124"
)
SCORING_CONFIG = (
    REPO_ROOT / "backend/pipeline/evidence/qualified_retriever_scoring_config.json"
)

EXPECTED_COUNTS = {
    "active_claims_total": 148,
    "aggregate_claims": 3,
    "atomic_claims": 140,
    "diagnostic_claims": 2,
    "parents": 147,
    "parents_without_claims": 3,
    "prognostic_claims": 0,
    "regimen_claims": 3,
    "therapeutic_claims": 146,
    "unresolved_associations": 6,
    "unsupported_associations": 6,
}

# I finding dell'audit 1.3 che questa fase chiude, citati per ID.
RESOLVED_FINDINGS = {
    "PROPAGATION_POLICY_MISSING_ON_NON_ATOMIC_CLAIMS": "major",
    "SALT_FORM_TABLE_CONTRADICTS_FORMULATION_CAVEAT": "major",
    "UNKNOWN_MODE_REJECTION_NOT_DECLARED": "minor",
    "LINK_PLAN_SCHEMA_HETEROGENEOUS": "minor",
    "NO_DISTINCT_FORMULATION_OUTCOME": "minor",
}


class BuildError(RuntimeError):
    """La 1.4 ha incontrato uno stato che la 1.3 non dovrebbe poter produrre."""


# --------------------------------------------------------------------------
# sorgente
# --------------------------------------------------------------------------


def load_v13() -> dict[str, Any]:
    return SCOPE.load_repository(SHADOW_V13)


def build_repository() -> tuple[list[dict[str, Any]], list[M14.PropagationChange]]:
    source = load_v13()
    return M14.upgrade_claims(source["claims"])


def _typed_object(record: Mapping[str, Any]) -> Any:
    """L'oggetto tipizzato corrispondente al record, per la simulazione del gate."""
    common = {
        "claim_id": record["claim_id"],
        "parent_id": record["parent_id"],
        "graph_evidence_id": record["graph_evidence_id"],
        "biomarker": record["biomarker"],
        "disease_scope": record["disease_scope"],
        "direction": record["direction"],
        "polarity": record["polarity"],
        "source_unit_ids": tuple(record.get("source_unit_ids") or ()),
        "evidence_setting": record.get("evidence_setting"),
    }
    if record["claim_type"] == "atomic_intervention_claim":
        return AtomicInterventionClaim(intervention=record["intervention"], **common)
    if record["claim_type"] == "regimen_claim":
        return RegimenClaim(
            regimen_components=tuple(record["regimen_components"]), **common
        )
    if record["claim_type"] == "aggregate_intervention_claim":
        return AggregateInterventionClaim(
            aggregate_type=record["aggregate_type"],
            aggregate_label=record["aggregate_label"],
            aggregate_members_literal=tuple(
                record.get("aggregate_members_literal") or ()
            ),
            **common,
        )
    raise BuildError(f"{record['claim_id']}: tipo senza oggetto tipizzato")


def _regression_objects(records: list[dict[str, Any]]) -> dict[str, Any]:
    def first(**match: Any) -> dict[str, Any]:
        for record in records:
            if all(record.get(key) == value for key, value in match.items()):
                return record
        raise BuildError(f"nessun claim soddisfa {match}")

    salt = first(
        claim_type="atomic_intervention_claim",
        canonical_intervention="alectinib hydrochloride",
    )
    infigratinib = first(
        claim_type="atomic_intervention_claim", canonical_intervention="infigratinib"
    )
    regimen = first(claim_type="regimen_claim")
    aggregate = first(
        claim_type="aggregate_intervention_claim",
        aggregate_type="non_separable_intervention_set",
    )
    return {
        "aggregate": (_typed_object(aggregate), aggregate),
        "atomic_infigratinib": (_typed_object(infigratinib), infigratinib),
        "atomic_salt": (_typed_object(salt), salt),
        "regimen": (_typed_object(regimen), regimen),
    }


# --------------------------------------------------------------------------
# conteggi e identita'
# --------------------------------------------------------------------------


def derived_counts(records: list[dict[str, Any]], source: Mapping[str, Any]) -> dict[str, Any]:
    by_type = Counter(record["claim_type"] for record in records)
    by_domain = Counter(record["claim_domain"] for record in records)
    return {
        "active_claims_total": len(records),
        "aggregate_claims": by_type["aggregate_intervention_claim"],
        "atomic_claims": by_type["atomic_intervention_claim"],
        "by_claim_type": dict(sorted(by_type.items())),
        "diagnostic_claims": by_domain["diagnostic"],
        "parents": len(source["parents"]),
        "parents_without_claims": sum(
            1 for parent in source["parents"] if not parent.get("child_claim_ids")
        ),
        "prognostic_claims": by_domain["prognostic"],
        "regimen_claims": by_type["regimen_claim"],
        "therapeutic_claims": by_domain["therapeutic"],
        "unresolved_associations": len(source["unresolved"]),
        "unsupported_associations": len(source["unsupported"]),
    }


def claim_id_impact(
    source: Mapping[str, Any], records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Un ID per riga, con la ragione per cui non e' cambiato.

    La riga esiste anche quando non c'e' niente da segnalare. Un artefatto che
    elencasse i soli ID cambiati non distinguerebbe "nessuno e' cambiato" da
    "nessuno e' stato controllato".
    """
    before = {record["claim_id"]: record for record in source["claims"]}
    rows: list[dict[str, Any]] = []
    for record in records:
        previous = before[record["claim_id"]]
        semantic_unchanged = all(
            previous.get(field) == record.get(field)
            for field in (
                "graph_evidence_id",
                "claim_type",
                "biomarker",
                "direction",
                "polarity",
                "source_unit_ids",
                "canonical_intervention",
                "disease_scope",
            )
        )
        rows.append(
            {
                "claim_id_after": record["claim_id"],
                "claim_id_before": previous["claim_id"],
                "claim_type": record["claim_type"],
                "changed": record["claim_id"] != previous["claim_id"],
                "fields_added": sorted(set(record) - set(previous)),
                "graph_evidence_id": record["graph_evidence_id"],
                "identity_fields_unchanged": semantic_unchanged,
                "lineage_required": False,
                "reason": (
                    "i campi di propagazione e il comportamento del gate non "
                    "appartengono alla formula di identita'"
                ),
            }
        )
    return sorted(rows, key=lambda row: row["claim_id_after"])


# --------------------------------------------------------------------------
# integrita'
# --------------------------------------------------------------------------


def _frozen() -> dict[str, Any]:
    frozen = SCOPE.frozen_hashes()
    frozen["trees"]["pre-promotion audit 1.3"] = {
        "path": "benchmarks/mtb_evidence/v3/pre_promotion_audit_1_3",
        "sha256": SCOPE.sha256_tree(AUDIT_V13),
    }
    return frozen


def _operational_query() -> dict[str, Any]:
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
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "baseline_sha256": OPERATIONAL_QUERY_BASELINE_SHA256,
        "parity": digest == OPERATIONAL_QUERY_BASELINE_SHA256,
        "query_id": "scope-narrowing-operational-parity",
        "result_count": len(output.all_results),
        "sha256": digest,
    }


def integrity(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    changed = [
        {
            "after": after[group][role]["sha256"],
            "before": entry["sha256"],
            "path": entry["path"],
            "role": role,
        }
        for group in ("files", "trees")
        for role, entry in sorted(before[group].items())
        if after[group][role]["sha256"] != entry["sha256"]
    ]
    gold = SCOPE.gold_tree_hash()
    return {
        "all_frozen_artifacts_unchanged": not changed,
        "changed": changed,
        "frozen_sha256": {
            role: entry["sha256"] for role, entry in sorted(after["files"].items())
        },
        "frozen_tree_sha256": {
            role: entry["sha256"] for role, entry in sorted(after["trees"].items())
        },
        "gold": gold,
        "operational_query": _operational_query(),
    }


# --------------------------------------------------------------------------
# finding e readiness
# --------------------------------------------------------------------------


def post_fix_findings(
    *,
    propagation_complete: bool,
    formulation_resolved: bool,
    policy_declared: bool,
    link_plan_normalized: bool,
    ids_stable: bool,
    form_audit: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows = [
        {
            "detail": (
                "I 148 claim attivi dichiarano propagation_policy, hard_filterable "
                "e final_evaluable. La deserializzazione rifiuta un record che non "
                "li porta."
            ),
            "finding_id": "PROPAGATION_POLICY_MISSING_ON_NON_ATOMIC_CLAIMS",
            "outcome": "resolved" if propagation_complete else "open",
            "resolved_by": "qualified_claim_model/1.2",
            "severity_before": "major",
            "severity_now": "none" if propagation_complete else "major",
        },
        {
            "detail": (
                "La tabella dei suffissi non decide piu' nessuna relazione di "
                "forma. Il registro contiene la sola coppia per cui esiste una "
                "fonte, e nessuna forma diventa exact rispetto alla propria "
                "moiety."
            ),
            "finding_id": "SALT_FORM_TABLE_CONTRADICTS_FORMULATION_CAVEAT",
            "outcome": "resolved" if formulation_resolved else "open",
            "resolved_by": FORM.CONTRACT_VERSION,
            "severity_before": "major",
            "severity_now": "none" if formulation_resolved else "major",
        },
        {
            "detail": (
                "Il manifest dichiara default_policy_mode, "
                "unknown_policy_mode_behavior e allowed_policy_modes."
            ),
            "finding_id": "UNKNOWN_MODE_REJECTION_NOT_DECLARED",
            "outcome": "resolved" if policy_declared else "open",
            "resolved_by": "policy_mode_contract.json",
            "severity_before": "minor",
            "severity_now": "none" if policy_declared else "minor",
        },
        {
            "detail": (
                "Le 37 azioni sono espresse su un solo schema di sette campi. I "
                "campi legacy restano nell'artefatto originale e sono mappati "
                "nella backward compatibility."
            ),
            "finding_id": "LINK_PLAN_SCHEMA_HETEROGENEOUS",
            "outcome": "resolved" if link_plan_normalized else "open",
            "resolved_by": FIXES.LINK_PLAN_SCHEMA_VERSION,
            "severity_before": "minor",
            "severity_now": "none" if link_plan_normalized else "minor",
        },
        {
            "detail": (
                "Una forma diversa non e' piu' indistinguibile da un farmaco non "
                "correlato: le relazioni verificate, quelle irrisolte e "
                "l'incompatibilita' di moiety hanno codici e bucket distinti."
            ),
            "finding_id": "NO_DISTINCT_FORMULATION_OUTCOME",
            "outcome": "resolved" if formulation_resolved else "open",
            "resolved_by": FORM.CONTRACT_VERSION,
            "severity_before": "minor",
            "severity_now": "none" if formulation_resolved else "minor",
        },
        {
            "detail": (
                "Nessun claim ha cambiato identita': i campi aggiunti non "
                "appartengono alla formula, e il comportamento del gate non e' un "
                "campo del claim."
            ),
            "finding_id": "CLAIM_IDENTITIES_STABLE",
            "outcome": "verified" if ids_stable else "open",
            "resolved_by": "claim_id_formula/1.0",
            "severity_before": "informational",
            "severity_now": "none" if ids_stable else "critical",
        },
    ]

    leaving = form_audit["salt_form_claims_leaving_primary"]
    rows.append(
        {
            "detail": (
                f"{len(leaving)} claim atomici in forma salina smettono di essere "
                "raggiunti nel bucket primario da una query sulla moiety nuda e "
                "diventano audit-only. Nessuna fonte lega quelle forme alla "
                "propria moiety: la copertura che si perde e' quella che la "
                "tabella dei suffissi produceva senza averne il titolo. "
                "Registrarla come informational e non come regressione e' una "
                "scelta esplicita di questa fase, e la voce resta aperta per una "
                "revisione terminologica esterna."
            ),
            "finding_id": "SALT_FORM_CLAIMS_LEAVE_PRIMARY_BUCKET",
            "outcome": "accepted_and_recorded",
            "resolved_by": None,
            "severity_before": "none",
            "severity_now": "informational",
        }
    )
    return sorted(rows, key=lambda row: row["finding_id"])


def readiness(
    *,
    findings: list[dict[str, Any]],
    counts_ok: bool,
    propagation_complete: bool,
    non_atomic_blocked: bool,
    formulation_resolved: bool,
    policy_declared: bool,
    link_plan_normalized: bool,
    ids_stable: bool,
    gate_regressions_green: bool,
    integrity_report: Mapping[str, Any],
) -> dict[str, Any]:
    critical = [row for row in findings if row["severity_now"] == "critical"]
    major = [row for row in findings if row["severity_now"] == "major"]
    minor = [row for row in findings if row["severity_now"] == "minor"]
    ready = bool(
        not critical
        and not major
        and counts_ok
        and propagation_complete
        and non_atomic_blocked
        and formulation_resolved
        and policy_declared
        and link_plan_normalized
        and ids_stable
        and gate_regressions_green
        and integrity_report["all_frozen_artifacts_unchanged"]
        and integrity_report["operational_query"]["parity"]
    )
    return {
        "claim_ids_stable": ids_stable,
        "corpus_promotion_ready": ready,
        "corpus_promotion_ready_scope": (
            "readiness per una fase separata di promozione prototipale, non per "
            "un uso operativo del corpus ne' per una validita' clinica"
        ),
        "critical_findings": len(critical),
        "formulation_contract_frozen": True,
        "formulation_contradiction_resolved": formulation_resolved,
        "full_exploratory_rerun_ready": False,
        "integrated_gate_regressions_green": gate_regressions_green,
        "link_plan_schema_normalized": link_plan_normalized,
        "major_findings": len(major),
        "minor_findings": len(minor),
        "non_atomic_propagation_explicitly_blocked": non_atomic_blocked,
        "operational_retriever_migration_ready": False,
        "propagation_policy_schema_uniform": propagation_complete,
        "required_promotion_fixes_resolved": bool(
            propagation_complete
            and formulation_resolved
            and policy_declared
            and link_plan_normalized
        ),
        "shadow_repository_v1_4_ready": ready,
        "unknown_policy_mode_rejected": policy_declared,
    }


# --------------------------------------------------------------------------
# artefatti
# --------------------------------------------------------------------------


def build_data_artifacts() -> dict[str, str]:
    before = _frozen()

    source = load_v13()
    records, changes = build_repository()

    counts = derived_counts(records, source)
    counts_ok = all(counts[key] == value for key, value in EXPECTED_COUNTS.items())

    matrix = M14.propagation_matrix(records)
    aggregates = M14.aggregate_audit(records)
    regimens = M14.regimen_audit(records)

    form_rows = FA.claim_form_rows(records)
    form_audit = FA.audit(records)
    form_simulation = FIXES.formulation_simulation()
    gate_rows = FIXES.gate_regression(_regression_objects(records))
    id_rows = claim_id_impact(source, records)

    normalized_plan = FIXES.normalize_link_plan(source["link_plan"])
    plan_compat = FIXES.link_plan_backward_compatibility(
        source["link_plan"], normalized_plan
    )
    policy_contract = FIXES.policy_mode_contract()

    propagation_complete = all(
        record.get("propagation_policy") is not None
        and record.get("hard_filterable") is not None
        and record.get("final_evaluable") is not None
        for record in records
    )
    non_atomic_blocked = all(
        row["member_propagation_allowed"] is False for row in aggregates + regimens
    )
    formulation_resolved = all(row["relation_as_expected"] for row in form_simulation)
    policy_declared = bool(
        policy_contract["unknown_policy_mode_behavior"] == "reject"
        and policy_contract["measured_behaviour_rejects_unknown_mode"]
    )
    link_plan_normalized = bool(
        plan_compat["plan_ids_unchanged"] and not plan_compat["meaning_changed"]
    )
    ids_stable = all(not row["changed"] for row in id_rows)
    gate_regressions_green = all(row["primary_as_expected"] for row in gate_rows) and all(
        row["gate_bypass"] is None for row in gate_rows
    )

    after = _frozen()
    integrity_report = integrity(before, after)

    findings = post_fix_findings(
        propagation_complete=propagation_complete,
        formulation_resolved=formulation_resolved,
        policy_declared=policy_declared,
        link_plan_normalized=link_plan_normalized,
        ids_stable=ids_stable,
        form_audit=form_audit,
    )
    readiness_report = readiness(
        findings=findings,
        counts_ok=counts_ok,
        propagation_complete=propagation_complete,
        non_atomic_blocked=non_atomic_blocked,
        formulation_resolved=formulation_resolved,
        policy_declared=policy_declared,
        link_plan_normalized=link_plan_normalized,
        ids_stable=ids_stable,
        gate_regressions_green=gate_regressions_green,
        integrity_report=integrity_report,
    )

    artifacts = {
        "evidence_claims_v1_4.jsonl": SCOPE.canonical_jsonl(records, key="claim_id"),
        "propagation_policy_matrix.jsonl": SCOPE.canonical_jsonl(matrix, key="claim_id"),
        "aggregate_propagation_audit.jsonl": SCOPE.canonical_jsonl(
            aggregates, key="claim_id"
        ),
        "regimen_propagation_audit.jsonl": SCOPE.canonical_jsonl(
            regimens, key="claim_id"
        ),
        "formulation_relation_definitions.json": SCOPE.canonical_dumps(
            FORM.relation_definitions()
        ),
        "formulation_registry_snapshot.jsonl": SCOPE.canonical_jsonl(
            FORM.registry_snapshot(), key="form_label"
        ),
        "formulation_claim_audit.jsonl": SCOPE.canonical_jsonl(
            form_rows, key=["claim_id", "source_literal"]
        ),
        "formulation_gate_simulation.jsonl": SCOPE.canonical_jsonl(
            form_simulation, key="case_id"
        ),
        "integrated_gate_regression.jsonl": SCOPE.canonical_jsonl(
            gate_rows, key=["case_id", "policy_mode"]
        ),
        "claim_id_impact.jsonl": SCOPE.canonical_jsonl(id_rows, key="claim_id_after"),
        "qualification_link_plan_v1_4.jsonl": SCOPE.canonical_jsonl(
            normalized_plan, key="plan_id"
        ),
        "policy_mode_contract.json": SCOPE.canonical_dumps(policy_contract),
        "backward_compatibility_addendum.json": SCOPE.canonical_dumps(
            {
                "claim_ids_unchanged": ids_stable,
                "formulation_behaviour_change": {
                    "affects_claim_identity": False,
                    "affects_retrieval": True,
                    "claims_leaving_primary_bucket": form_audit[
                        "salt_form_claims_leaving_primary"
                    ],
                    "claims_becoming_visible": form_audit["retrieval_impacts"].get(
                        "becomes_visible_instead_of_rejected", 0
                    ),
                },
                "link_plan": plan_compat,
                "model_schema_before": "qualified_claim_model/1.1",
                "model_schema_after": PROP.MODEL_SCHEMA_VERSION_V12,
                "new_required_fields": list(PROP.REQUIRED_PROPAGATION_FIELDS),
                "readers_of_1_3_records": (
                    "un lettore della 1.3 continua a funzionare: i campi aggiunti "
                    "sono nuovi e nessun campo esistente e' cambiato di nome o di "
                    "significato"
                ),
                "readers_requiring_1_4": (
                    "un lettore che validi con qualified_claim_model/1.2 rifiuta i "
                    "record 1.3, ed e' il comportamento voluto: quei record non "
                    "dichiarano la propria propagazione"
                ),
                "repository_version_after": M14.REPOSITORY_VERSION,
                "repository_version_before": M14.SUPERSEDES,
            }
        ),
        "post_fix_findings.jsonl": SCOPE.canonical_jsonl(findings, key="finding_id"),
        "post_fix_readiness.json": SCOPE.canonical_dumps(readiness_report),
        "repository_version_lineage.json": SCOPE.canonical_dumps(M14.version_lineage()),
    }

    manifest = {
        "artifact_sha256": {
            name: SCOPE.sha256_text(text) for name, text in sorted(artifacts.items())
        },
        "counts": counts,
        "counts_match_expected": counts_ok,
        "expected_counts": dict(EXPECTED_COUNTS),
        "formulation": {
            "contract": FORM.CONTRACT_VERSION,
            "registry": FORM.REGISTRY_VERSION,
            "registry_entries": len(FORM.VERIFIED_FORMULATION_REGISTRY),
            "suffix_normalization_used": False,
        },
        "gold_used": False,
        "integrated_structural_gate": GATE11.GATE_VERSION,
        "integrity": integrity_report,
        "invariants": {
            "aggregates_atomized": 0,
            "claim_ids_changed": sum(1 for row in id_rows if row["changed"]),
            "gate_bypasses": sum(1 for row in gate_rows if row["gate_bypass"]),
            "gold_artifacts_read": 0,
            "member_propagation_allowed": sum(
                1 for row in aggregates + regimens if row["member_propagation_allowed"]
            ),
            "operational_artifacts_modified": not integrity_report[
                "all_frozen_artifacts_unchanged"
            ],
            "plans_executed": False,
            "regimens_split": 0,
            "repository_promoted": False,
            "shadow_1_3_modified": False,
        },
        "llm_used": False,
        "migration_status": M14.MIGRATION_STATUS,
        "model_schema": PROP.MODEL_SCHEMA_VERSION_V12,
        "network_used": False,
        "neo4j_used": False,
        "output_contract": GATE11.OUTPUT_CONTRACT_VERSION,
        "phase": PHASE,
        "policy": policy_contract,
        "propagation": PROP.propagation_contract(),
        "python_version": "3.12",
        "readiness": readiness_report,
        "repository_schema": M14.REPOSITORY_VERSION,
        "resolved_audit_findings": dict(sorted(RESOLVED_FINDINGS.items())),
        "review_independence": "non_independent",
        "review_status": "first_review_complete",
        "reviewer_role": "author_required_fixes_implementer",
        "start_sha": START_SHA,
        "supersedes": M14.SUPERSEDES,
        "test_framework": "unittest (stdlib)",
        "version_bump_reason": M14.VERSION_BUMP_REASON,
    }
    artifacts["repository_v1_4_manifest.json"] = SCOPE.canonical_dumps(manifest)
    return dict(sorted(artifacts.items()))


def build() -> dict[str, str]:
    artifacts = build_data_artifacts()
    try:
        from benchmarks.mtb_evidence.evaluation.required_fixes_reports import (
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
    manifest = json.loads(artifacts["repository_v1_4_manifest.json"])
    print(
        SCOPE.canonical_dumps(
            {
                "artifacts": len(artifacts),
                "output": args.output.as_posix(),
                "repository_schema": manifest["repository_schema"],
                "shadow_repository_v1_4_ready": manifest["readiness"][
                    "shadow_repository_v1_4_ready"
                ],
            }
        ),
        end="",
    )


if __name__ == "__main__":
    main()
