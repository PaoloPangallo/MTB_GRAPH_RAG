"""Generazione del contenuto canonico del corpus promosso a partire dalla 1.4.

Il modulo non conosce nessun percorso. Riceve i record gia' letti e restituisce
i testi da scrivere: e' la stessa divisione che l'audit pre-promozione ha usato,
e serve a che la generazione sia eseguibile su una copia del repository e
verificabile su dati sintetici senza che nulla debba essere finto.

Cosa la promozione *non* fa, ed e' la parte che conta:

**Non ricalcola nessuna proposizione.** I claim attivi sono i 148 record della
1.4, copiati. I parent, le associazioni e i registri sono quelli della 1.3 e
della terminology closure, copiati. Un corpus promosso che rigenerasse il
contenuto invece di copiarlo non sarebbe la 1.4 promossa: sarebbe una 1.5 non
revisionata che le somiglia.

**Non cambia nessun ID.** Nessuna formula di identita' viene rieseguita.

**Non trasforma prototype_only in final.** I 148 claim restano non
final-evaluable e non hard-filterable dopo la promozione come lo erano prima:
promuovere e' un fatto di versionamento, non una validazione.

L'unica normalizzazione che la promozione applica riguarda i quattro claim
deprecati. Due dei quattro non portano i campi di propagazione, perche' furono
ritirati prima che il modello 1.2 li rendesse obbligatori. Promuoverli cosi'
lascerebbe nel corpus esattamente il buco che la 1.4 ha chiuso, e costringerebbe
il loader a un'eccezione per i record storici — cioe' a un default in lettura.
I campi mancanti vengono quindi *dichiarati* con gli stessi valori che la 1.4 ha
dichiarato per i claim attivi, e l'operazione e' registrata nel diff: nessuna
proposizione cambia, nessun ID cambia, nessuna revisione viene rifatta.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from backend.pipeline.evidence.corpus import links_and_views as LV
from backend.pipeline.evidence.corpus import promotion_contract as CONTRACT
from backend.pipeline.evidence.shadow import propagation as PROP

DEPRECATED_SCHEMA_NORMALIZATION = "declared_propagation_fields_on_deprecated_claims"


class MaterializationError(RuntimeError):
    """Il contenuto promosso non corrisponde a cio' che la 1.4 dichiara."""


# --------------------------------------------------------------------------
# serializzazione canonica
# --------------------------------------------------------------------------


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def canonical_jsonl(rows: Sequence[Mapping[str, Any]], *, key: str) -> str:
    lines = [
        json.dumps(row, ensure_ascii=False, sort_keys=True)
        for row in sorted(rows, key=lambda row: str(row.get(key) or ""))
    ]
    return "\n".join(lines) + ("\n" if lines else "")


# --------------------------------------------------------------------------
# sorgenti
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Sources:
    """I record della 1.4 e della 1.3 gia' letti, senza nessun path."""

    claims: tuple[Mapping[str, Any], ...]
    parents: tuple[Mapping[str, Any], ...]
    deprecated: tuple[Mapping[str, Any], ...]
    unsupported: tuple[Mapping[str, Any], ...]
    unresolved: tuple[Mapping[str, Any], ...]
    lineage_rows: tuple[Mapping[str, Any], ...]
    diagnostic_replacements: tuple[Mapping[str, Any], ...]
    terminology_registry: Mapping[str, Any]
    formulation_registry: tuple[Mapping[str, Any], ...]
    formulation_gate_simulation: tuple[Mapping[str, Any], ...]
    salt_claims_leaving_primary: tuple[str, ...]
    disease_relation_definitions: Mapping[str, Any]
    disease_policy_modes: Mapping[str, Any]
    disease_match_contract: Mapping[str, Any]
    verified_alias_registry: Mapping[str, Any]
    link_plan: tuple[Mapping[str, Any], ...]
    view_plan: tuple[Mapping[str, Any], ...]
    source_file_sha256: Mapping[str, str]
    source_shadow_sha256: str


# --------------------------------------------------------------------------
# claim
# --------------------------------------------------------------------------


def promoted_claims(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """I 148 claim della 1.4, copiati e rivalidati contro il contratto 1.2."""
    promoted: list[dict[str, Any]] = []
    for record in records:
        PROP.validate_record(record)
        if record.get("propagation_policy") != CONTRACT.PROPAGATION_POLICY:
            raise MaterializationError(
                f"{record['claim_id']}: propagation_policy "
                f"{record.get('propagation_policy')!r} invece di "
                f"{CONTRACT.PROPAGATION_POLICY!r}"
            )
        if record.get("final_evaluable") or record.get("hard_filterable"):
            raise MaterializationError(
                f"{record['claim_id']}: la promozione non rende un claim "
                "final-evaluable ne' hard-filterable"
            )
        promoted.append(dict(record))

    ids = [record["claim_id"] for record in promoted]
    if len(set(ids)) != len(ids):
        raise MaterializationError("collisione fra claim ID nel corpus promosso")
    if sorted(ids) != sorted(str(record["claim_id"]) for record in records):
        raise MaterializationError("l'insieme dei claim ID e' cambiato nella promozione")
    return sorted(promoted, key=lambda record: record["claim_id"])


def promoted_deprecated(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """I quattro ritirati, con i campi di propagazione dichiarati dove mancavano."""
    rows: list[dict[str, Any]] = []
    for record in records:
        declared = PROP.propagation_fields_for(str(record.get("claim_type") or ""))
        filled = {
            field: value
            for field, value in declared.items()
            if record.get(field) is None
        }
        upgraded = dict(record) | filled
        upgraded["schema_version"] = PROP.MODEL_SCHEMA_VERSION_V12
        upgraded["propagation_fields_declared_by_promotion"] = sorted(filled)
        if upgraded["claim_id"] != record["claim_id"]:
            raise MaterializationError(
                f"{record['claim_id']}: la normalizzazione ha cambiato l'ID"
            )
        if not upgraded.get("deprecated"):
            raise MaterializationError(
                f"{record['claim_id']}: un ritirato deve dichiararsi deprecated"
            )
        PROP.validate_record(upgraded)
        rows.append(upgraded)
    return sorted(rows, key=lambda row: row["claim_id"])


def domain_projection(
    claims: Sequence[Mapping[str, Any]], domain: str
) -> list[dict[str, Any]]:
    """I claim di un dominio, proiettati dal file attivo e non ricopiati dalla 1.3.

    Proiettare invece di copiare e' cio' che impedisce ai file di dominio di
    divergere dal file dei claim: se un giorno divergessero, non ci sarebbe modo
    di sapere quale dei due sia il repository.
    """
    return [dict(claim) for claim in claims if claim.get("claim_domain") == domain]


# --------------------------------------------------------------------------
# lineage
# --------------------------------------------------------------------------


def promoted_lineage(
    *,
    deprecated: Sequence[Mapping[str, Any]],
    lineage_rows: Sequence[Mapping[str, Any]],
    diagnostic_replacements: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Una riga per claim ritirato, con il redirect verso il sostituto attivo.

    Il lineage della shadow e' diviso in due artefatti di due fasi diverse: la
    canonicalizzazione terminologica nella 1.3, il restringimento diagnostico
    nella 1.2. Un corpus promosso che ne portasse uno solo avrebbe un redirect
    su due dei quattro ritirati, e la meta' mancante non sarebbe visibile da
    nessuna parte.
    """
    by_old = {str(row["old_claim_id"]): row for row in lineage_rows}
    diagnostic = {
        str(row["legacy_or_shadow_claim_id"]): row for row in diagnostic_replacements
    }

    rows: list[dict[str, Any]] = []
    for record in deprecated:
        old_id = str(record["claim_id"])
        new_id = str(record.get("replacement_claim_id") or "")
        if not new_id:
            raise MaterializationError(f"{old_id}: ritirato senza claim sostitutivo")
        terminology = by_old.get(old_id)
        narrowing = diagnostic.get(old_id)
        if terminology is None and narrowing is None:
            raise MaterializationError(f"{old_id}: nessuna riga di lineage lo copre")
        source = terminology or narrowing
        rows.append(
            {
                "claim_type_after": (source or {}).get("claim_type_after")
                or record["claim_type"],
                "claim_type_before": (source or {}).get("claim_type_before")
                or record["claim_type"],
                "deprecation_origin": record.get("deprecation_origin"),
                "deprecation_status": record.get("deprecation_status"),
                "effective_repository_version": record.get(
                    "effective_repository_version"
                ),
                "graph_evidence_id": record["graph_evidence_id"],
                "lineage_source": (
                    CONTRACT.SOURCE_SHADOW_BASE_DIRNAME
                    if terminology is not None
                    else "diagnostic_disease_scope_narrowing_shadow"
                ),
                "new_claim_id": new_id,
                "old_claim_id": old_id,
                "parent_id": record["parent_id"],
                "propagation_policy": CONTRACT.PROPAGATION_POLICY,
                "reason_code": record.get("reason_code"),
                "reason_codes": list((source or {}).get("reason_codes") or ()),
                "reversible": bool(record.get("reversible")),
                "review_independence": (source or {}).get("review_independence")
                or "non_independent",
                "review_status": record.get("review_status"),
                "source_literals": list((source or {}).get("source_literals") or ()),
                "terminology_decision_id": (source or {}).get("terminology_decision_id"),
            }
        )
    return sorted(rows, key=lambda row: row["old_claim_id"])


# --------------------------------------------------------------------------
# registri
# --------------------------------------------------------------------------


def disease_relation_registry(
    *,
    definitions: Mapping[str, Any],
    policy_modes: Mapping[str, Any],
    match_contract: Mapping[str, Any],
    alias_registry: Mapping[str, Any],
    source_sha256: Mapping[str, str],
) -> dict[str, Any]:
    """Le quattro parti della politica di malattia in un registro unico.

    Vengono composte e non riscritte: ogni parte porta l'hash dell'artefatto da
    cui viene, cosi' che il registro promosso resti confrontabile con la fase
    che l'ha deciso.
    """
    return {
        "allowed_policy_modes": list(CONTRACT.ALLOWED_POLICY_MODES),
        "default_policy_mode": CONTRACT.DEFAULT_POLICY_MODE,
        "match_contract": dict(match_contract),
        "policy_modes": dict(policy_modes),
        "registry_version": "promoted_disease_relation_registry/1.0",
        "relation_definitions": dict(definitions),
        "source_artifact_sha256": dict(sorted(source_sha256.items())),
        "source_phase": "disease-hierarchy-policy/1.0",
        "unknown_policy_mode_behavior": CONTRACT.UNKNOWN_POLICY_MODE_BEHAVIOR,
        "verified_alias_registry": dict(alias_registry),
    }


def terminology_preservation(registry: Mapping[str, Any]) -> dict[str, Any]:
    """Cosa la promozione ha lasciato esattamente dov'era, e cosa e' rimasto aperto."""
    applied = list(registry.get("applied_mappings") or ())
    unresolved = list(registry.get("unresolved_mappings") or ())
    verified = [
        row
        for row in applied
        if row.get("terminology_decision_id") == CONTRACT.VERIFIED_TERMINOLOGY_DECISION
    ]
    pending = [
        row
        for row in unresolved
        if row.get("terminology_decision_id")
        == CONTRACT.UNRESOLVED_TERMINOLOGY_DECISION
    ]
    if not verified:
        raise MaterializationError("la decisione BGJ398 verificata non e' nel registro")
    if not pending:
        raise MaterializationError("AUY922 non risulta piu' irrisolto")
    return {
        "auy922_unresolved": True,
        "auy922_recommendation": pending[0].get("recommendation"),
        "bgj398_source_literal_preserved": bool(verified[0].get("source_literal_preserved")),
        "bgj398_verified_mapping": verified[0].get("canonical_label"),
        "collisions": registry.get("collisions"),
        "deduplications": registry.get("deduplications"),
        "external_terminology_review_pending": True,
        "new_mappings_introduced_by_promotion": 0,
        "queue_fully_resolved": bool(registry.get("queue_fully_resolved")),
        "registry_version": registry.get("registry_version"),
        "source_literals_preserved": True,
        "suffix_normalization_used": False,
    }


def _form_buckets(simulation: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Bucket di ciascuna forma, letto dalla simulazione del gate della 1.4.

    La forma e' il letterale con piu' token fra i due della coppia. I casi in
    cui i due ne hanno lo stesso numero — sale contro sale, moiety contro
    moiety — non nominano una forma rispetto a una moiety e vengono lasciati
    fuori invece di essere assegnati per convenzione.
    """
    buckets: dict[str, str] = {}
    for row in simulation:
        query = str(row["query_literal"]).strip()
        claim = str(row["claim_literal"]).strip()
        if len(query.split()) == len(claim.split()):
            continue
        form = query if len(query.split()) > len(claim.split()) else claim
        buckets[form] = str(row["bucket"])
    return buckets


def formulation_preservation(
    registry: Sequence[Mapping[str, Any]],
    *,
    claims_leaving_primary: Sequence[str],
    gate_simulation: Sequence[Mapping[str, Any]],
    active_claim_ids: frozenset[str],
) -> dict[str, Any]:
    """Il registro delle forme e il costo di copertura che la promozione non rilassa.

    I dodici claim salini restano fuori dal bucket primario per una query sulla
    moiety nuda. L'elenco viene dalla 1.4 e non viene ricalcolato qui: dedurlo
    dal numero di token di `canonical_intervention` produrrebbe un numero
    diverso — un intervento a due parole non e' per questo una forma salina — e
    quel numero sostituirebbe in silenzio una decisione gia' presa.

    La promozione li registra e non li aggiusta: non esiste una fonte che leghi
    quelle forme alla propria moiety, e allargare il gate qui rimetterebbe la
    copertura che la tabella dei suffissi produceva senza averne il titolo.
    """
    verified = [row for row in registry if row.get("relation_status") == "verified"]
    leaving = sorted(str(claim_id) for claim_id in claims_leaving_primary)
    unknown = [claim_id for claim_id in leaving if claim_id not in active_claim_ids]
    if unknown:
        raise MaterializationError(
            f"claim salini fuori dal corpus promosso: {unknown}"
        )
    buckets = _form_buckets(gate_simulation)
    return {
        "audit_only_forms": sorted(
            form for form, bucket in buckets.items() if bucket == "audit_only_results"
        ),
        "contract": "intervention_formulation_contract/1.0",
        "external_terminology_review_pending": True,
        "new_forms_resolved_by_promotion": 0,
        "registry_entries": len(registry),
        "registry_version": "verified_formulation_registry/1.0",
        "retained_with_warning_forms": sorted(
            form for form, bucket in buckets.items() if bucket == "retained_with_warning"
        ),
        "salt_form_claim_ids": leaving,
        "salt_form_claims_outside_primary_for_bare_moiety_query": len(leaving),
        "salt_gate_relaxed_by_promotion": False,
        "suffix_normalization_used": False,
        "verified_relations": len(verified),
    }


# --------------------------------------------------------------------------
# inventario derivato
# --------------------------------------------------------------------------


def derived_counts(
    *,
    claims: Sequence[Mapping[str, Any]],
    parents: Sequence[Mapping[str, Any]],
    deprecated: Sequence[Mapping[str, Any]],
    unsupported: Sequence[Mapping[str, Any]],
    unresolved: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """I conteggi ricavati dai record promossi, non letti dal manifest della 1.4."""
    by_type = Counter(str(claim["claim_type"]) for claim in claims)
    by_domain = Counter(str(claim["claim_domain"]) for claim in claims)

    active_ids = {str(claim["claim_id"]) for claim in claims}
    parent_ids = {str(parent["parent_id"]) for parent in parents}
    child_ids = {
        str(child)
        for parent in parents
        for child in (parent.get("child_claim_ids") or ())
    }
    claim_ids = [str(claim["claim_id"]) for claim in claims]

    return {
        "active_claims_total": len(claims),
        "aggregate_claims": by_type["aggregate_intervention_claim"],
        "atomic_claims": by_type["atomic_intervention_claim"],
        "by_claim_type": dict(sorted(by_type.items())),
        "deduplications": 0,
        "deprecated_claims": len(deprecated),
        "deprecated_claims_present_among_active": len(
            active_ids & {str(row["claim_id"]) for row in deprecated}
        ),
        "diagnostic_claims": by_domain["diagnostic"],
        "id_collisions": len(claim_ids) - len(set(claim_ids)),
        "orphan_claims": len(
            {claim_id for claim_id in active_ids if claim_id not in child_ids}
            | {
                str(claim["claim_id"])
                for claim in claims
                if str(claim["parent_id"]) not in parent_ids
            }
        ),
        "parents": len(parents),
        "parents_without_claims": sum(
            1 for parent in parents if not parent.get("child_claim_ids")
        ),
        "prognostic_claims": by_domain["prognostic"],
        "regimen_claims": by_type["regimen_claim"],
        "therapeutic_claims": by_domain["therapeutic"],
        "unresolved_associations": len(unresolved),
        "unsupported_associations": len(unsupported),
    }


def lineage_index(
    *,
    claims: Sequence[Mapping[str, Any]],
    parents: Sequence[Mapping[str, Any]],
    deprecated: Sequence[Mapping[str, Any]],
    lineage: Sequence[Mapping[str, Any]],
    unsupported: Sequence[Mapping[str, Any]],
    unresolved: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Copertura dei lookup che il corpus promosso deve garantire."""
    active_ids = {str(claim["claim_id"]) for claim in claims}
    retired_ids = {str(row["claim_id"]) for row in deprecated}
    redirects = {str(row["old_claim_id"]): str(row["new_claim_id"]) for row in lineage}
    legacy = {
        str(statement): str(claim["claim_id"])
        for claim in claims
        for statement in (claim.get("legacy_statement_ids") or ())
    }
    by_evidence: dict[str, list[str]] = {}
    for claim in claims:
        by_evidence.setdefault(str(claim["graph_evidence_id"]), []).append(
            str(claim["claim_id"])
        )

    probes = {
        evidence_id: {
            "active_claim_ids": sorted(by_evidence.get(evidence_id, ())),
            "parent_ids": sorted(
                str(parent["parent_id"])
                for parent in parents
                if str(parent["graph_evidence_id"]) == evidence_id
            ),
            "retired_claim_ids": sorted(
                str(row["claim_id"])
                for row in deprecated
                if str(row["graph_evidence_id"]) == evidence_id
            ),
            "unresolved_association_ids": sorted(
                str(row["association_id"])
                for row in unresolved
                if str(row["graph_evidence_id"]) == evidence_id
            ),
            "unsupported_association_ids": sorted(
                str(row["association_id"])
                for row in unsupported
                if str(row["graph_evidence_id"]) == evidence_id
            ),
        }
        for evidence_id in CONTRACT.LINEAGE_PROBE_IDS
    }

    return {
        "graph_evidence_ids": len(by_evidence),
        "legacy_statement_ids": len(legacy),
        "parents_without_claims": sorted(
            str(parent["parent_id"]) for parent in parents if not parent.get("child_claim_ids")
        ),
        "probes": dict(sorted(probes.items())),
        "redirects": dict(sorted(redirects.items())),
        "retired_claims_present_in_primary_lookup": sorted(retired_ids & active_ids),
        "retired_claims_without_redirect": sorted(retired_ids - set(redirects)),
        "redirect_targets_not_active": sorted(set(redirects.values()) - active_ids),
        "unresolved_association_ids": sorted(
            str(row["association_id"]) for row in unresolved
        ),
        "unsupported_association_ids": sorted(
            str(row["association_id"]) for row in unsupported
        ),
    }


__all__ = [
    "DEPRECATED_SCHEMA_NORMALIZATION",
    "MaterializationError",
    "Sources",
    "canonical_json",
    "canonical_jsonl",
    "derived_counts",
    "disease_relation_registry",
    "domain_projection",
    "formulation_preservation",
    "lineage_index",
    "promoted_claims",
    "promoted_deprecated",
    "promoted_lineage",
    "sha256_text",
    "terminology_preservation",
]
