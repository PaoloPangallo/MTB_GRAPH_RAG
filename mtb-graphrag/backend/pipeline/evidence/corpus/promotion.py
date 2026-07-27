"""Assemblaggio dei diciotto artefatti del corpus promosso e loro validazione.

Il modulo compone cio' che `materialization` deriva e `links_and_views` applica,
e produce due cose: i testi da scrivere, e la funzione che li rilegge dalla
directory di staging per dire se sono scrivibili.

La validazione riceve la directory e non i testi in memoria. La differenza
sembra formale e non lo e': cio' che va validato e' il corpus come un lettore lo
trovera' — file su disco, riletti, riconteggiati — non come chi lo scrive crede
di averlo prodotto. Una validazione sulla struttura in memoria non potrebbe
accorgersi di un file scritto con l'encoding sbagliato o di un `\\r\\n` che
cambia gli hash su un'altra piattaforma.

Tre invarianti valgono a ogni esecuzione e sono verificati sui file riletti:
i conteggi coincidono con quelli attesi, ogni claim porta la propria propagation
policy, e nessun claim e' final-evaluable.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from backend.pipeline.evidence.corpus import links_and_views as LV
from backend.pipeline.evidence.corpus import materialization as MAT
from backend.pipeline.evidence.corpus import promotion_contract as CONTRACT
from backend.pipeline.evidence.corpus import prototype_registry as REGISTRY
from backend.pipeline.evidence.corpus import rollback as ROLLBACK
from backend.pipeline.evidence.shadow import propagation as PROP


class PromotionValidationError(RuntimeError):
    """Il corpus in staging non e' promuovibile."""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# generazione
# --------------------------------------------------------------------------


def build_artifacts(sources: MAT.Sources) -> dict[str, str]:
    """I diciotto file del corpus promosso, come testo canonico."""
    claims = MAT.promoted_claims(sources.claims)
    deprecated = MAT.promoted_deprecated(sources.deprecated)
    parents = [dict(parent) for parent in sources.parents]
    unsupported = [dict(row) for row in sources.unsupported]
    unresolved = [dict(row) for row in sources.unresolved]

    lineage = MAT.promoted_lineage(
        deprecated=deprecated,
        lineage_rows=sources.lineage_rows,
        diagnostic_replacements=sources.diagnostic_replacements,
    )

    active_ids = frozenset(str(claim["claim_id"]) for claim in claims)
    deprecated_ids = frozenset(str(row["claim_id"]) for row in deprecated)
    claims_by_id = {str(claim["claim_id"]): claim for claim in claims}

    links = LV.apply_link_plan(
        sources.link_plan,
        active_claim_ids=active_ids,
        deprecated_claim_ids=deprecated_ids,
        namespace=CONTRACT.PROMOTED_CORPUS_RELPATH,
    )
    views = LV.apply_view_plan(
        sources.view_plan,
        claims_by_id=claims_by_id,
        namespace=CONTRACT.PROMOTED_CORPUS_RELPATH,
    )

    counts = MAT.derived_counts(
        claims=claims,
        parents=parents,
        deprecated=deprecated,
        unsupported=unsupported,
        unresolved=unresolved,
    )
    lineage_report = MAT.lineage_index(
        claims=claims,
        parents=parents,
        deprecated=deprecated,
        lineage=lineage,
        unsupported=unsupported,
        unresolved=unresolved,
    )
    link_report = LV.link_consistency(links)
    view_report = LV.view_consistency(views, active_claim_ids=active_ids)

    terminology = MAT.terminology_preservation(sources.terminology_registry)
    formulation = MAT.formulation_preservation(
        sources.formulation_registry,
        claims_leaving_primary=sources.salt_claims_leaving_primary,
        gate_simulation=sources.formulation_gate_simulation,
        active_claim_ids=active_ids,
    )

    content: dict[str, str] = {
        "graph_evidence_parents.jsonl": MAT.canonical_jsonl(parents, key="parent_id"),
        "evidence_claims.jsonl": MAT.canonical_jsonl(claims, key="claim_id"),
        "therapeutic_claims.jsonl": MAT.canonical_jsonl(
            MAT.domain_projection(claims, "therapeutic"), key="claim_id"
        ),
        "diagnostic_claims.jsonl": MAT.canonical_jsonl(
            MAT.domain_projection(claims, "diagnostic"), key="claim_id"
        ),
        "prognostic_claims.jsonl": MAT.canonical_jsonl(
            MAT.domain_projection(claims, "prognostic"), key="claim_id"
        ),
        "deprecated_claims.jsonl": MAT.canonical_jsonl(deprecated, key="claim_id"),
        "unsupported_associations.jsonl": MAT.canonical_jsonl(
            unsupported, key="association_id"
        ),
        "unresolved_associations.jsonl": MAT.canonical_jsonl(
            unresolved, key="association_id"
        ),
        "claim_replacement_lineage.jsonl": MAT.canonical_jsonl(
            lineage, key="old_claim_id"
        ),
        "terminology_registry.json": MAT.canonical_json(sources.terminology_registry),
        "disease_relation_registry.json": MAT.canonical_json(
            MAT.disease_relation_registry(
                definitions=sources.disease_relation_definitions,
                policy_modes=sources.disease_policy_modes,
                match_contract=sources.disease_match_contract,
                alias_registry=sources.verified_alias_registry,
                source_sha256=sources.source_file_sha256,
            )
        ),
        "formulation_registry.jsonl": MAT.canonical_jsonl(
            [dict(row) for row in sources.formulation_registry], key="form_label"
        ),
        "qualification_links.jsonl": MAT.canonical_jsonl(links, key="link_id"),
        "qualified_evidence_views.jsonl": MAT.canonical_jsonl(views, key="plan_id"),
    }

    file_sha256 = {name: MAT.sha256_text(text) for name, text in sorted(content.items())}
    counts_ok = all(
        counts[key] == value for key, value in CONTRACT.EXPECTED_COUNTS.items()
    )

    entry = REGISTRY.build_entry(
        source_shadow_sha256=sources.source_shadow_sha256,
        corpus_sha256=MAT.sha256_text(
            "\n".join(f"{name}:{digest}" for name, digest in sorted(file_sha256.items()))
        ),
    )

    manifest = {
        "artifact_sha256": file_sha256,
        "clinical_readiness": CONTRACT.CLINICAL_READINESS,
        "corpus_path": CONTRACT.PROMOTED_CORPUS_RELPATH,
        "counts": counts,
        "counts_match_expected": counts_ok,
        "expected_counts": dict(sorted(CONTRACT.EXPECTED_COUNTS.items())),
        "final_evaluable": CONTRACT.FINAL_EVALUABLE,
        "formulation": formulation,
        "gold_used": False,
        "lineage": lineage_report,
        "links": link_report,
        "llm_used": False,
        "model_version": CONTRACT.MODEL_VERSION,
        "neo4j_used": False,
        "network_used": False,
        "operational_retriever_bound": CONTRACT.OPERATIONAL_RETRIEVER_BOUND,
        "phase": CONTRACT.PHASE,
        "policy": {
            "allowed_policy_modes": list(CONTRACT.ALLOWED_POLICY_MODES),
            "default_policy_mode": CONTRACT.DEFAULT_POLICY_MODE,
            "silent_fallback_permitted": False,
            "unknown_policy_mode_behavior": CONTRACT.UNKNOWN_POLICY_MODE_BEHAVIOR,
            "unspecified_mode_resolves_to": CONTRACT.DEFAULT_POLICY_MODE,
        },
        "promoted_at": CONTRACT.PROMOTED_AT,
        "promotion_commit": CONTRACT.PROMOTION_COMMIT,
        "promotion_status": CONTRACT.PROMOTION_STATUS,
        "propagation": PROP.propagation_contract(),
        "prototype_promoted": CONTRACT.PROTOTYPE_PROMOTED,
        "repository_version": CONTRACT.REPOSITORY_VERSION,
        "schema_version": CONTRACT.SCHEMA_VERSION,
        "source_artifact_sha256": dict(sorted(sources.source_file_sha256.items())),
        "source_shadow_sha256": sources.source_shadow_sha256,
        "source_shadow_version": CONTRACT.SOURCE_SHADOW_VERSION,
        "terminology": terminology,
        "views": view_report,
    }

    promotion_log = {
        "claims_promoted": len(claims),
        "deprecated_schema_normalization": {
            "changed_claim_ids": 0,
            "changed_propositions": 0,
            "claims_normalized": sum(
                1
                for row in deprecated
                if row.get("propagation_fields_declared_by_promotion")
            ),
            "declared_values": PROP.propagation_fields_for("atomic_intervention_claim"),
            "operation": MAT.DEPRECATED_SCHEMA_NORMALIZATION,
            "reason": (
                "Due dei quattro ritirati furono deprecati prima che il modello "
                "1.2 rendesse obbligatori i campi di propagazione. Promuoverli "
                "senza lascerebbe nel corpus il buco che la 1.4 ha chiuso e "
                "costringerebbe il loader a un default in lettura."
            ),
        },
        "file_sha256": file_sha256,
        "gold_artifacts_read": 0,
        "links_applied": link_report["actions_applied"],
        "phase": CONTRACT.PHASE,
        "promoted_at": CONTRACT.PROMOTED_AT,
        "promotion_commit": CONTRACT.PROMOTION_COMMIT,
        "sequence": [
            "snapshot degli hash correnti",
            "generazione in directory temporanea",
            "validazione completa sui file riletti",
            "confronto con la shadow 1.4",
            "scrittura del manifest",
            "rename atomico nella directory definitiva",
            "verifica post-write",
            "aggiornamento atomico del solo registro prototipale V3",
        ],
        "source_artifact_sha256": dict(sorted(sources.source_file_sha256.items())),
        "source_shadow_sha256": sources.source_shadow_sha256,
        "views_materialized": view_report["materialized_views"],
    }

    content["corpus_manifest.json"] = MAT.canonical_json(manifest)
    content["corpus_registry_entry.json"] = MAT.canonical_json(entry)
    content["promotion_log.json"] = MAT.canonical_json(promotion_log)
    content["rollback_metadata.json"] = MAT.canonical_json(
        ROLLBACK.rollback_metadata(
            corpus_sha256=file_sha256,
            source_shadow_sha256=sources.source_shadow_sha256,
        )
    )

    missing = sorted(set(CONTRACT.CORPUS_FILES) - set(content))
    unexpected = sorted(set(content) - set(CONTRACT.CORPUS_FILES))
    if missing or unexpected:
        raise PromotionValidationError(
            f"contenuto non conforme al contratto: mancano {missing}, "
            f"in piu' {unexpected}"
        )
    return dict(sorted(content.items()))


# --------------------------------------------------------------------------
# validazione sui file scritti
# --------------------------------------------------------------------------


def validate_written_corpus(directory: Path) -> dict[str, Any]:
    """Rilegge il corpus dalla directory e verifica che sia promuovibile."""
    directory = Path(directory)
    present = {item.name for item in directory.iterdir() if item.is_file()}
    missing = sorted(set(CONTRACT.CORPUS_FILES) - present)
    if missing:
        raise PromotionValidationError(f"file assenti dal corpus: {missing}")

    manifest = _read_json(directory / CONTRACT.MANIFEST_FILE)
    if manifest.get("repository_version") != CONTRACT.REPOSITORY_VERSION:
        raise PromotionValidationError(
            f"repository_version {manifest.get('repository_version')!r} invece di "
            f"{CONTRACT.REPOSITORY_VERSION!r}"
        )
    if manifest.get("schema_version") != CONTRACT.SCHEMA_VERSION:
        raise PromotionValidationError("schema_version incompatibile")

    recomputed = {
        name: MAT.sha256_text((directory / name).read_text(encoding="utf-8"))
        for name in manifest["artifact_sha256"]
    }
    mismatched = sorted(
        name
        for name, digest in manifest["artifact_sha256"].items()
        if recomputed.get(name) != digest
    )
    if mismatched:
        raise PromotionValidationError(f"hash non coincidenti: {mismatched}")

    claims = _read_jsonl(directory / "evidence_claims.jsonl")
    parents = _read_jsonl(directory / "graph_evidence_parents.jsonl")
    deprecated = _read_jsonl(directory / "deprecated_claims.jsonl")
    unsupported = _read_jsonl(directory / "unsupported_associations.jsonl")
    unresolved = _read_jsonl(directory / "unresolved_associations.jsonl")
    lineage = _read_jsonl(directory / "claim_replacement_lineage.jsonl")
    links = _read_jsonl(directory / "qualification_links.jsonl")
    views = _read_jsonl(directory / "qualified_evidence_views.jsonl")

    for record in claims + deprecated:
        PROP.validate_record(record)

    final_evaluable = sorted(
        str(claim["claim_id"]) for claim in claims if claim.get("final_evaluable")
    )
    if final_evaluable:
        raise PromotionValidationError(
            f"la promozione ha reso final-evaluable {final_evaluable}"
        )
    hard_filterable = sorted(
        str(claim["claim_id"]) for claim in claims if claim.get("hard_filterable")
    )
    if hard_filterable:
        raise PromotionValidationError(
            f"la promozione ha reso hard-filterable {hard_filterable}"
        )
    not_prototype = sorted(
        str(claim["claim_id"])
        for claim in claims
        if claim.get("propagation_policy") != CONTRACT.PROPAGATION_POLICY
    )
    if not_prototype:
        raise PromotionValidationError(
            f"claim non piu' prototype_only: {not_prototype}"
        )

    counts = MAT.derived_counts(
        claims=claims,
        parents=parents,
        deprecated=deprecated,
        unsupported=unsupported,
        unresolved=unresolved,
    )
    wrong = {
        key: {"expected": value, "derived": counts[key]}
        for key, value in CONTRACT.EXPECTED_COUNTS.items()
        if counts[key] != value
    }
    if wrong:
        raise PromotionValidationError(f"conteggi non attesi: {wrong}")

    active_ids = frozenset(str(claim["claim_id"]) for claim in claims)
    link_report = LV.link_consistency(links)
    if link_report["actions_applied"] != CONTRACT.EXPECTED_LINK_ACTIONS:
        raise PromotionValidationError(
            f"link applicati {link_report['actions_applied']} invece di "
            f"{CONTRACT.EXPECTED_LINK_ACTIONS}"
        )
    if link_report["active_links_targeting_deprecated_claims"]:
        raise PromotionValidationError("un link attivo punta a un claim ritirato")
    if link_report["active_links_without_active_target"]:
        raise PromotionValidationError("un link attivo non ha un bersaglio attivo")
    if link_report["duplicate_link_ids"]:
        raise PromotionValidationError(
            f"link duplicati: {link_report['duplicate_link_ids']}"
        )

    view_report = LV.view_consistency(views, active_claim_ids=active_ids)
    if view_report["actions_applied"] != CONTRACT.EXPECTED_VIEW_ACTIONS:
        raise PromotionValidationError(
            f"view applicate {view_report['actions_applied']} invece di "
            f"{CONTRACT.EXPECTED_VIEW_ACTIONS}"
        )
    if view_report["orphan_views"]:
        raise PromotionValidationError(f"view orfane: {view_report['orphan_views']}")
    if view_report["members_flattened_into_separate_views"]:
        raise PromotionValidationError("un aggregato o un regime e' stato appiattito")
    if view_report["cross_domain_ranking_present"]:
        raise PromotionValidationError("una view dichiara ranking cross-domain")

    retired = {str(row["claim_id"]) for row in deprecated}
    if retired & active_ids:
        raise PromotionValidationError(
            f"claim ritirati presenti fra gli attivi: {sorted(retired & active_ids)}"
        )
    redirect_sources = {str(row["old_claim_id"]) for row in lineage}
    if retired - redirect_sources:
        raise PromotionValidationError(
            f"ritirati senza redirect: {sorted(retired - redirect_sources)}"
        )

    entry = _read_json(directory / "corpus_registry_entry.json")
    REGISTRY.validate_entry(entry)

    return {
        "active_claims": len(claims),
        "counts_match_expected": True,
        "deprecated_claims": len(deprecated),
        "files": len(present),
        "hashes_verified": len(recomputed),
        "links_applied": link_report["actions_applied"],
        "parents": len(parents),
        "views_applied": view_report["actions_applied"],
    }


__all__ = [
    "PromotionValidationError",
    "build_artifacts",
    "validate_written_corpus",
]
