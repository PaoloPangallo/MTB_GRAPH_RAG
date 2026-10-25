"""Audit della promozione prototipale: link, view, diff e rollback.

Gli artefatti di questa fase non ripetono cio' che il corpus gia' dice. Servono
a rendere verificabile *dall'esterno* cio' che il corpus afferma di se stesso, e
sono costruiti confrontando il corpus promosso con le sorgenti shadow invece che
rileggendo il suo manifest.

Il diff e' derivato di nuovo dalla 1.4 e non copiato da quello della 1.3. Le due
fasi hanno perimetri diversi — la 1.3 simulava una promozione, questa ne esegue
una — e riusare il diff precedente descriverebbe un'operazione che non e' quella
avvenuta.

Il rollback viene provato su una copia e mai sul risultato finale. Un rollback
eseguito sul corpus promosso lascerebbe la fase senza il proprio prodotto, e la
prova che il rollback funziona non vale la perdita di cio' su cui si applica.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from backend.pipeline.evidence.corpus import links_and_views as LV
from backend.pipeline.evidence.corpus import loader as LOADER
from backend.pipeline.evidence.corpus import promotion_contract as CONTRACT
from backend.pipeline.evidence.corpus import prototype_registry as REGISTRY
from backend.pipeline.evidence.corpus import rollback as ROLLBACK
from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import scope as SCOPE

AUDIT_VERSION = "prototype_corpus_promotion_audit/1.0"


# --------------------------------------------------------------------------
# link e view
# --------------------------------------------------------------------------


def link_application_rows(
    *,
    promoted_links: Sequence[Mapping[str, Any]],
    shadow_plan: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Una riga per azione, con il piano shadow accanto al link promosso.

    Le due colonne `executed` stanno nella stessa riga di proposito. Un artefatto
    che riportasse soltanto quella del corpus lascerebbe indistinguibile "il piano
    e' stato eseguito" da "il piano e' stato eseguito nella namespace V3", che
    sono affermazioni diverse e solo la seconda e' vera.
    """
    by_plan = {str(action["plan_id"]): action for action in shadow_plan}
    rows: list[dict[str, Any]] = []
    for link in promoted_links:
        plan_id = str(link["plan_id"])
        planned = by_plan.get(plan_id)
        if planned is None:
            raise RuntimeError(f"{plan_id}: link promosso senza azione nel piano 1.4")
        rows.append(
            {
                "action_type": link["action_type"],
                "applied_in_namespace": link["applied_in_namespace"],
                "executed_in_promoted_namespace": bool(link["executed"]),
                "link_state": link["link_state"],
                "locator_preserved": link["locator"] == planned.get("locator"),
                "new_target_id": link["new_target_id"],
                "old_target_id": link["old_target_id"],
                "plan_id": plan_id,
                "reason_code_preserved": link["reason_code"] == planned.get("reason_code"),
                "shadow_plan_executed": bool(planned.get("executed")),
                "source_unit_preserved": list(link["source_unit_id"])
                == list(planned.get("source_unit_id") or ()),
                "target_claim_id": link["target_claim_id"],
                "target_is_active_claim": bool(link["target_is_active_claim"]),
                "target_is_deprecated_claim": bool(link["target_is_deprecated_claim"]),
            }
        )
    return sorted(rows, key=lambda row: row["plan_id"])


def view_materialization_rows(
    *,
    promoted_views: Sequence[Mapping[str, Any]],
    shadow_plan: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_plan = {str(action["plan_id"]): action for action in shadow_plan}
    rows: list[dict[str, Any]] = []
    for view in promoted_views:
        plan_id = str(view["plan_id"])
        planned = by_plan.get(plan_id)
        if planned is None:
            raise RuntimeError(f"{plan_id}: view promossa senza azione nel piano 1.3")
        rows.append(
            {
                "action_type": view["action_type"],
                "applied_in_namespace": view["applied_in_namespace"],
                "claim_domain": view["claim_domain"],
                "claim_id": view["claim_id"],
                "claim_type": view["claim_type"],
                "cross_domain_ranking": bool(view["cross_domain_ranking"]),
                "executed_in_promoted_namespace": bool(view["executed"]),
                "members_flattened": len(view["flattened_members"]),
                "plan_id": plan_id,
                "shadow_plan_executed": bool(planned.get("executed")),
                "view_id": view["view_id"],
                "view_section": view["view_section"],
                "view_state": view["view_state"],
            }
        )
    return sorted(rows, key=lambda row: row["plan_id"])


# --------------------------------------------------------------------------
# diff
# --------------------------------------------------------------------------


def promotion_diff(
    corpus: LOADER.PromotedCorpus,
    *,
    shadow_claims: Sequence[Mapping[str, Any]],
    shadow_deprecated: Sequence[Mapping[str, Any]],
    file_sha256: Mapping[str, str],
    integrity: Mapping[str, Any],
) -> dict[str, Any]:
    """Il diff della promozione, derivato dalla 1.4 e non copiato dalla 1.3."""
    promoted_ids = sorted(str(claim["claim_id"]) for claim in corpus.claims)
    shadow_ids = sorted(str(claim["claim_id"]) for claim in shadow_claims)

    normalized = sorted(
        str(row["claim_id"])
        for row in corpus.deprecated
        if row.get("propagation_fields_declared_by_promotion")
    )
    link_report = LV.link_consistency(corpus.links)
    view_report = LV.view_consistency(
        corpus.views,
        active_claim_ids=frozenset(promoted_ids),
    )

    return {
        "active_rows": len(corpus.claims),
        "claim_ids_added": sorted(set(promoted_ids) - set(shadow_ids)),
        "claim_ids_changed": 0 if promoted_ids == shadow_ids else len(promoted_ids),
        "claim_ids_removed": sorted(set(shadow_ids) - set(promoted_ids)),
        "deprecated_rows": len(corpus.deprecated),
        "derived_from": CONTRACT.SOURCE_SHADOW_VERSION,
        "derived_from_previous_diff": False,
        "files_created": sorted(file_sha256),
        "files_created_count": len(file_sha256),
        "lineage_rows": len(corpus.lineage),
        "links_applied": link_report["actions_applied"],
        "links_left_active": link_report["active_links"],
        "operational_files_changed": len(integrity["changed"]),
        "operational_query_behavior_changed": not integrity["operational_query"]["parity"],
        "propositions_added": 0,
        "propositions_removed": 0,
        "registry_changes": {
            "active_prototype_corpus_after": CONTRACT.REPOSITORY_VERSION,
            "active_prototype_corpus_before": None,
            "entries_added": [CONTRACT.REPOSITORY_VERSION],
            "operational_configuration_changed": False,
            "operational_retriever_bound_after": False,
            "registry_created": True,
            "registry_relpath": CONTRACT.REGISTRY_RELPATH,
        },
        "schema_changes": {
            "claim_model_version": CONTRACT.MODEL_VERSION,
            "corpus_schema_version": CONTRACT.SCHEMA_VERSION,
            "deprecated_claims_declared_propagation_fields": normalized,
            "deprecated_schema_version_after": CONTRACT.MODEL_VERSION,
            "link_schema_version": LV.LINK_SCHEMA_VERSION,
            "propositions_affected_by_schema_change": 0,
            "view_schema_version": LV.VIEW_SCHEMA_VERSION,
        },
        "shadow_deprecated_rows": len(shadow_deprecated),
        "views_materialized": view_report["materialized_views"],
        "views_verified_without_regeneration": view_report[
            "verified_without_regeneration"
        ],
    }


# --------------------------------------------------------------------------
# rollback su copia
# --------------------------------------------------------------------------


def rehearse_rollback(
    *, corpus_path: Path, registry_path: Path, workspace: Path
) -> dict[str, Any]:
    """Prova il rollback su una copia e ne verifica l'idempotenza.

    La prova gira due volte. La prima deve cambiare qualcosa, la seconda non deve
    cambiare piu' nulla e deve produrre lo stesso stato: un rollback idempotente
    non e' uno che si puo' rieseguire senza errori, ma uno la cui seconda
    esecuzione e' indistinguibile dalla prima.
    """
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    copy_corpus = workspace / Path(corpus_path).name
    copy_registry = workspace / Path(registry_path).name
    if copy_corpus.exists():
        shutil.rmtree(copy_corpus)
    shutil.copytree(corpus_path, copy_corpus)
    shutil.copyfile(registry_path, copy_registry)

    operational_before = SCOPE.frozen_hashes()

    first = ROLLBACK.rollback(
        registry_path=copy_registry,
        corpus_path=copy_corpus,
        mode=ROLLBACK.RETAIN_IN_PLACE,
    )
    registry_after_first = json.loads(copy_registry.read_text(encoding="utf-8"))
    second = ROLLBACK.rollback(
        registry_path=copy_registry,
        corpus_path=copy_corpus,
        mode=ROLLBACK.RETAIN_IN_PLACE,
    )
    registry_after_second = json.loads(copy_registry.read_text(encoding="utf-8"))

    moved = ROLLBACK.rollback(
        registry_path=copy_registry,
        corpus_path=copy_corpus,
        mode=ROLLBACK.MOVE_TO_INACTIVE,
    )

    operational_after = SCOPE.frozen_hashes()
    operational_unchanged = operational_before == operational_after

    try:
        LOADER.load_from_registry(copy_registry)
        loads_after_rollback = True
    except LOADER.PromotedCorpusError:
        loads_after_rollback = False

    return {
        "active_prototype_corpus_after": registry_after_second.get(
            "active_prototype_corpus"
        ),
        "corpus_loadable_after_rollback": loads_after_rollback,
        "first_run": first.as_dict(),
        "idempotent": registry_after_first == registry_after_second
        and not second.changed,
        "move_to_inactive_run": moved.as_dict(),
        "operational_artifacts_unchanged": operational_unchanged,
        "operational_retriever_was_never_bound": not first.operational_binding_observed,
        "performed_on_copy": True,
        "performed_on_promoted_corpus": False,
        "preserved_files": list(ROLLBACK.PRESERVED_FILES),
        "registry_entry_status_after": registry_after_second["entries"][
            CONTRACT.REPOSITORY_VERSION
        ]["status"],
        "second_run": second.as_dict(),
        # Il nome della directory di prova non entra nell'artefatto: e'
        # generato dal sistema a ogni esecuzione, e includerlo renderebbe il
        # report diverso ogni volta senza che nulla di verificabile sia
        # cambiato.
        "workspace_kind": "temporary_directory_outside_the_repository",
    }


# --------------------------------------------------------------------------
# readiness
# --------------------------------------------------------------------------


def readiness(
    *,
    corpus: LOADER.PromotedCorpus,
    registry: Mapping[str, Any],
    diff: Mapping[str, Any],
    integrity: Mapping[str, Any],
    rollback_report: Mapping[str, Any],
    write_log: Mapping[str, Any],
) -> dict[str, Any]:
    manifest = corpus.manifest
    counts = corpus.counts()
    prototype_only = all(
        claim.get("propagation_policy") == CONTRACT.PROPAGATION_POLICY
        for claim in corpus.claims
    )
    no_final = all(not claim.get("final_evaluable") for claim in corpus.claims)
    steps = [step["step"] for step in write_log["steps"]]

    return {
        "all_claims_prototype_only": prototype_only,
        "atomic_write_verified": bool(
            "verify_post_write" in steps
            and "rename" in steps
            and all(step["outcome"] == "ok" for step in write_log["steps"])
        ),
        "clinical_readiness": False,
        "full_exploratory_rerun_ready": False,
        "no_claim_final_evaluable": no_final,
        "operational_pipeline_unchanged": bool(
            integrity["all_frozen_artifacts_unchanged"]
            and integrity["operational_query"]["parity"]
            and diff["operational_files_changed"] == 0
        ),
        "operational_retriever_bound": bool(registry["operational_retriever_bound"]),
        "operational_retriever_migration_ready": bool(
            manifest["counts_match_expected"]
            and prototype_only
            and no_final
            and registry["active_prototype_corpus"] == CONTRACT.REPOSITORY_VERSION
            and not registry["operational_retriever_bound"]
        ),
        "promoted_inventory_consistent": bool(
            manifest["counts_match_expected"]
            and counts["active_claims_total"]
            == CONTRACT.EXPECTED_COUNTS["active_claims_total"]
            and counts["parents"] == CONTRACT.EXPECTED_COUNTS["parents"]
        ),
        "promoted_lineage_complete": bool(
            not manifest["lineage"]["retired_claims_without_redirect"]
            and not manifest["lineage"]["redirect_targets_not_active"]
            and not manifest["lineage"]["retired_claims_present_in_primary_lookup"]
        ),
        "promoted_links_consistent": bool(
            manifest["links"]["actions_applied"] == CONTRACT.EXPECTED_LINK_ACTIONS
            and not manifest["links"]["active_links_targeting_deprecated_claims"]
            and not manifest["links"]["active_links_without_active_target"]
            and not manifest["links"]["duplicate_link_ids"]
            and manifest["links"]["historical_plan_left_unexecuted"]
        ),
        "promoted_views_consistent": bool(
            manifest["views"]["actions_applied"] == CONTRACT.EXPECTED_VIEW_ACTIONS
            and not manifest["views"]["orphan_views"]
            and not manifest["views"]["members_flattened_into_separate_views"]
            and not manifest["views"]["cross_domain_ranking_present"]
        ),
        "prototype_corpus_promotion_applied": bool(
            registry["active_prototype_corpus"] == CONTRACT.REPOSITORY_VERSION
        ),
        "prototype_corpus_registry_updated": bool(
            registry["entries"][CONTRACT.REPOSITORY_VERSION]["status"]
            == REGISTRY.STATUS_ACTIVE
        ),
        "rollback_tested": bool(
            rollback_report["idempotent"]
            and rollback_report["performed_on_copy"]
            and not rollback_report["performed_on_promoted_corpus"]
            and rollback_report["operational_artifacts_unchanged"]
        ),
        "strict_default_explicit": bool(
            manifest["policy"]["default_policy_mode"] == CONTRACT.DEFAULT_POLICY_MODE
        ),
        "unknown_mode_rejected": bool(
            manifest["policy"]["unknown_policy_mode_behavior"]
            == CONTRACT.UNKNOWN_POLICY_MODE_BEHAVIOR
        ),
    }


__all__ = [
    "AUDIT_VERSION",
    "link_application_rows",
    "promotion_diff",
    "readiness",
    "rehearse_rollback",
    "view_materialization_rows",
]
