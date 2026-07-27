"""Ricomputazione degli ID a partire dalle sole righe emesse.

L'audit non chiede al generatore di ricalcolare i propri ID: rilegge i JSONL e
riapplica la formula congelata ai campi che la riga porta. E' l'unico modo di
accorgersi che un ID sia stato scritto una volta e mai piu' verificato.

Due dettagli decidono se la ricomputazione e' possibile a partire dal file, e
sono documentati qui perche' un promotore che rigenerasse il corpus deve
riprodurli:

**La source unit di identita' non e' sempre `source_unit_ids[0]`.** I claim
migrati dal legacy non hanno un'unita' di fonte revisionata: la loro identita'
usa il token `LEGACY-NO-REVIEWED-SOURCE-UNIT:<statement>`, che resta leggibile
in `provenance.identity_source_unit_token`.

**La forma canonica dell'intervento dipende dall'origine.** I claim adjudicati
usano il letterale canonico cosi' com'e'; quelli legacy lo minuscolizzano. Non
e' una scelta di questo audit: e' cio' che l'adapter ha fatto, e ricalcolare
diversamente produrrebbe ID diversi da quelli congelati.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from backend.pipeline.evidence.shadow.identity import (
    CLAIM_ID_FORMULA_VERSION,
    CLAIM_IDENTITY_FIELDS,
    FIELD_SEPARATOR,
    ID_HEX_LENGTH,
    NON_THERAPEUTIC_CLAIM_ID_FORMULA_VERSION,
    NON_THERAPEUTIC_IDENTITY_FIELDS,
    association_id,
    canonical_regimen,
    claim_id,
    claim_identity_payload,
    non_therapeutic_claim_id,
    non_therapeutic_identity_payload,
    parent_id,
)

LEGACY_ORIGIN = "legacy_single_statement"
LEGACY_SOURCE_UNIT_PREFIX = "LEGACY-NO-REVIEWED-SOURCE-UNIT:"

# Il solo letterale che la terminology closure ha canonicalizzato. Esce
# dall'identita' — e' per questo che l'ID cambia — e resta nel record, perche'
# una identificazione del 2026 non riscrive un documento del 2013.
CANONICALIZED_SOURCE_LITERALS = frozenset({"BGJ398"})

# I cinque record che le fasi precedenti hanno nominato esplicitamente. Sono
# ricontrollati uno per uno perche' su di loro si sono concentrate tutte le
# decisioni di terminologia, di scope e di regime.
NAMED_GRAPH_EVIDENCE_IDS = (
    "evidence:1846",
    "evidence:1847",
    "evidence:1851",
    "evidence:1853",
    "evidence:11240",
)


class IdentityAuditError(RuntimeError):
    """Una riga non porta i campi che la propria formula di identita' richiede."""


def identity_source_unit(claim: Mapping[str, Any]) -> str:
    """La source unit che entra nell'hash, che non sempre e' quella dichiarata."""
    units = claim.get("source_unit_ids") or ()
    if units:
        return str(units[0])
    token = (claim.get("provenance") or {}).get("identity_source_unit_token")
    if not token:
        raise IdentityAuditError(
            f"{claim.get('claim_id')}: nessuna source unit di identita' ricostruibile"
        )
    return str(token)


def canonical_intervention_or_regimen(claim: Mapping[str, Any]) -> str:
    """Forma canonica dell'intervento come l'adapter l'ha calcolata."""
    claim_type = claim["claim_type"]
    if claim_type == "regimen_claim":
        return canonical_regimen(claim["regimen_components"])
    if claim_type == "aggregate_intervention_claim":
        return str(claim["canonical_intervention"])
    if claim_type == "atomic_intervention_claim":
        canonical = str(claim["canonical_intervention"])
        return canonical.lower() if claim.get("migration_origin") == LEGACY_ORIGIN else canonical
    raise IdentityAuditError(f"{claim.get('claim_id')}: tipo senza formula terapeutica")


def recompute_claim(claim: Mapping[str, Any]) -> dict[str, Any]:
    """Riga di ricomputazione per un singolo claim attivo o ritirato."""
    source_unit = identity_source_unit(claim)
    if claim["claim_type"] == "diagnostic_claim":
        payload = non_therapeutic_identity_payload(
            graph_evidence_id=claim["graph_evidence_id"],
            claim_type=claim["claim_type"],
            canonical_subject=claim["canonical_subject"],
            biomarker=claim["biomarker"],
            disease_scope=claim["disease_scope"],
            direction_or_interpretation=claim["diagnostic_interpretation"],
            polarity=claim["polarity"],
            source_unit_id=source_unit,
        )
        recomputed = non_therapeutic_claim_id(
            graph_evidence_id=claim["graph_evidence_id"],
            claim_type=claim["claim_type"],
            canonical_subject=claim["canonical_subject"],
            biomarker=claim["biomarker"],
            disease_scope=claim["disease_scope"],
            direction_or_interpretation=claim["diagnostic_interpretation"],
            polarity=claim["polarity"],
            source_unit_id=source_unit,
        )
        formula = NON_THERAPEUTIC_CLAIM_ID_FORMULA_VERSION
        fields = list(NON_THERAPEUTIC_IDENTITY_FIELDS)
    else:
        canonical = canonical_intervention_or_regimen(claim)
        payload = claim_identity_payload(
            graph_evidence_id=claim["graph_evidence_id"],
            claim_type=claim["claim_type"],
            canonical_intervention_or_regimen=canonical,
            biomarker=claim["biomarker"],
            direction=claim["direction"],
            polarity=claim["polarity"],
            source_unit_id=source_unit,
        )
        recomputed = claim_id(
            graph_evidence_id=claim["graph_evidence_id"],
            claim_type=claim["claim_type"],
            canonical_intervention_or_regimen=canonical,
            biomarker=claim["biomarker"],
            direction=claim["direction"],
            polarity=claim["polarity"],
            source_unit_id=source_unit,
        )
        formula = CLAIM_ID_FORMULA_VERSION
        fields = list(CLAIM_IDENTITY_FIELDS)

    literals = sorted(
        {
            str(item)
            for item in (
                tuple(claim.get("source_literal_members") or ())
                + tuple(claim.get("aggregate_members_literal") or ())
                + tuple((claim.get("provenance") or {}).get("source_literal_terms") or ())
            )
        }
    )
    # Un letterale che la canonicalizzazione ha sostituito non deve comparire
    # nel payload di identita' — altrimenti l'ID non sarebbe cambiato — e deve
    # restare leggibile nel record, altrimenti la fonte sarebbe stata riscritta.
    #
    # Il confronto e' case-insensitive di proposito. La forma canonica di un
    # aggregato e' minuscola, quindi cercare `BGJ398` cosi' com'e' dentro
    # `bgj398 + pd173074` non lo troverebbe: il claim *ritirato* sembrerebbe
    # aver tolto dall'identita' il letterale che invece vi e' ancora dentro.
    lowered_payload = payload.lower()
    canonicalized = sorted(
        literal
        for literal in literals
        if literal in CANONICALIZED_SOURCE_LITERALS
        and literal.lower() not in lowered_payload
    )
    return {
        "canonical_payload": payload,
        "canonicalized_literals_absent_from_identity": canonicalized,
        "declared_id": claim["claim_id"],
        "entity": "claim",
        "formula_fields": fields,
        "formula_version": formula,
        "graph_evidence_id": claim["graph_evidence_id"],
        "identity_source_unit_id": source_unit,
        "identity_source_unit_is_legacy_token": source_unit.startswith(
            LEGACY_SOURCE_UNIT_PREFIX
        ),
        "kind": claim["claim_type"],
        "matches": recomputed == claim["claim_id"],
        "recomputed_id": recomputed,
        "source_literals_preserved_in_record": literals,
    }


def recompute_parent(parent: Mapping[str, Any]) -> dict[str, Any]:
    recomputed = parent_id(parent["graph_evidence_id"])
    return {
        "canonical_payload": FIELD_SEPARATOR.join(
            ("graph_evidence_record", parent["graph_evidence_id"])
        ),
        "declared_id": parent["parent_id"],
        "entity": "parent",
        "formula_fields": ["kind", "graph_evidence_id"],
        "formula_version": CLAIM_ID_FORMULA_VERSION,
        "graph_evidence_id": parent["graph_evidence_id"],
        "kind": "graph_evidence_record",
        "matches": recomputed == parent["parent_id"],
        "recomputed_id": recomputed,
    }


def recompute_association(association: Mapping[str, Any]) -> dict[str, Any]:
    source_unit = str((association.get("source_unit_ids") or ("",))[0])
    recomputed = association_id(
        kind=association["kind"],
        graph_evidence_id=association["graph_evidence_id"],
        intervention_literal=association["intervention_literal"],
        biomarker=association["biomarker"],
        source_unit_id=source_unit,
    )
    return {
        "canonical_payload": FIELD_SEPARATOR.join(
            (
                association["kind"],
                association["graph_evidence_id"],
                association["intervention_literal"],
                association["biomarker"],
                source_unit,
            )
        ),
        "declared_id": association["association_id"],
        "entity": "association",
        "formula_fields": [
            "kind",
            "graph_evidence_id",
            "intervention_literal",
            "biomarker",
            "source_unit_id",
        ],
        "formula_version": CLAIM_ID_FORMULA_VERSION,
        "graph_evidence_id": association["graph_evidence_id"],
        "identity_source_unit_id": source_unit,
        "kind": association["kind"],
        "matches": recomputed == association["association_id"],
        "recomputed_id": recomputed,
        "source_literal_preserved_in_identity": association["intervention_literal"],
    }


def recomputation_rows(repository: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Una riga per ogni identita' del repository, ritirati compresi."""
    rows = [recompute_claim(claim) for claim in repository["claims"]]
    rows += [
        recompute_claim(row) | {"entity": "retired_claim"}
        for row in repository["deprecated"]
    ]
    rows += [recompute_parent(parent) for parent in repository["parents"]]
    rows += [
        recompute_association(row)
        for row in repository["unsupported"] + repository["unresolved"]
    ]
    return sorted(rows, key=lambda row: (row["entity"], row["declared_id"]))


def _order_invariance(repository: Mapping[str, Any]) -> dict[str, Any]:
    """La ricomputazione non deve dipendere dall'ordine di lettura delle righe."""
    forward = [row["recomputed_id"] for row in recomputation_rows(repository)]
    reversed_repository = {
        key: list(reversed(value)) if isinstance(value, list) else value
        for key, value in repository.items()
    }
    backward = [row["recomputed_id"] for row in recomputation_rows(reversed_repository)]
    return {
        "identical": forward == backward,
        "ids_in_reverse_input_order": len(backward),
        "ids_in_declared_order": len(forward),
    }


def _stability(repository: Mapping[str, Any]) -> bool:
    """Ricalcolare due volte deve dare due volte lo stesso risultato."""
    first = [row["recomputed_id"] for row in recomputation_rows(repository)]
    second = [row["recomputed_id"] for row in recomputation_rows(repository)]
    return first == second


def named_record_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (
            row
            for row in rows
            if row["graph_evidence_id"] in NAMED_GRAPH_EVIDENCE_IDS
        ),
        key=lambda row: (row["graph_evidence_id"], row["entity"], row["declared_id"]),
    )


def audit(repository: Mapping[str, Any]) -> dict[str, Any]:
    rows = recomputation_rows(repository)
    mismatches = [row for row in rows if not row["matches"]]

    declared = [row["declared_id"] for row in rows]
    duplicates = sorted(
        {identifier for identifier in declared if declared.count(identifier) > 1}
    )
    # Un ID puo' comparire due volte soltanto se e' lo stesso oggetto letto da
    # due file: attivo e ritirato non condividono mai un ID.
    active_ids = {claim["claim_id"] for claim in repository["claims"]}
    retired_ids = {row["claim_id"] for row in repository["deprecated"]}
    cross_space = sorted(active_ids & retired_ids)

    prefixes = {
        row["declared_id"][:4] for row in rows if row["entity"] == "parent"
    } | {row["declared_id"][:4] for row in rows if row["entity"] == "claim"}

    named = named_record_rows(rows)
    return {
        "claim_ids_recomputable": not mismatches,
        "collisions": len(duplicates) + len(cross_space),
        "duplicate_declared_ids": duplicates,
        "formula_versions": sorted(
            {row["formula_version"] for row in rows}
        ),
        "hex_length": ID_HEX_LENGTH,
        "id_prefix_spaces_disjoint": prefixes == {"GEP-", "CLM-"},
        "identities_checked": len(rows),
        "identities_by_entity": {
            entity: sum(1 for row in rows if row["entity"] == entity)
            for entity in sorted({row["entity"] for row in rows})
        },
        "legacy_identity_tokens": sum(
            1 for row in rows if row.get("identity_source_unit_is_legacy_token")
        ),
        "mismatched_ids": [
            {
                "declared_id": row["declared_id"],
                "entity": row["entity"],
                "recomputed_id": row["recomputed_id"],
            }
            for row in mismatches
        ],
        "named_records": [
            {
                "declared_id": row["declared_id"],
                "entity": row["entity"],
                "graph_evidence_id": row["graph_evidence_id"],
                "matches": row["matches"],
                "recomputed_id": row["recomputed_id"],
            }
            for row in named
        ],
        "named_records_all_match": all(row["matches"] for row in named),
        "order_invariance": _order_invariance(repository),
        "shared_ids_between_active_and_retired": cross_space,
        "source_literal_preservation": {
            "canonicalized_literal": sorted(CANONICALIZED_SOURCE_LITERALS),
            "records_keeping_the_literal_out_of_identity": sorted(
                row["declared_id"]
                for row in rows
                if row.get("canonicalized_literals_absent_from_identity")
            ),
            "records_still_carrying_the_literal": sorted(
                row["declared_id"]
                for row in rows
                if set(row.get("source_literals_preserved_in_record") or ())
                & CANONICALIZED_SOURCE_LITERALS
            ),
        },
        "stable_across_recomputation": _stability(repository),
        "unexplained_duplications": duplicates,
    }


__all__ = [
    "NAMED_GRAPH_EVIDENCE_IDS",
    "IdentityAuditError",
    "audit",
    "canonical_intervention_or_regimen",
    "identity_source_unit",
    "recomputation_rows",
    "recompute_association",
    "recompute_claim",
    "recompute_parent",
]
