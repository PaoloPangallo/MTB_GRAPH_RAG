"""Simulazione dell'effetto di una decisione terminologica. Non applica nulla.

La simulazione risponde a una sola domanda: se il mapping verificato fosse
propagato, che cosa cambierebbe davvero. La risposta utile e' quasi sempre
"meno di quanto sembri" — un'identita' di sostanza verificata sposta la
rappresentazione canonica dell'intervento e null'altro, e in particolare non
rende separabile un risultato che la fonte riporta unito.

Le funzioni sono pure e ricevono esplicitamente i dati del repository: leggono
per contare, mai per scrivere.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from backend.pipeline.evidence.shadow.identity import canonical_regimen, claim_id

AGGREGATE_CLAIM_TYPE = "aggregate_intervention_claim"


class SimulationError(RuntimeError):
    """La formula di identita' non riproduce gli ID gia' emessi."""


def aggregate_claim_id(
    *, graph_evidence_id: str, intervention: str, biomarker: str, source_unit_id: str
) -> str:
    return claim_id(
        graph_evidence_id=graph_evidence_id,
        claim_type=AGGREGATE_CLAIM_TYPE,
        canonical_intervention_or_regimen=intervention,
        biomarker=biomarker,
        direction="sensitivity",
        polarity="supports",
        source_unit_id=source_unit_id,
    )


def claim_id_simulation(
    *,
    pair_id: str,
    current_ids: Mapping[str, str],
    biomarkers: Mapping[str, str],
    source_unit_id: str,
    current_intervention: str,
    proposed_components: Sequence[str],
    unchanged_claims: Sequence[tuple[str, str, str]],
    reason_codes: Sequence[str],
) -> list[dict[str, Any]]:
    """Effetto sugli ID di una canonicalizzazione non applicata.

    La formula viene prima usata per riprodurre gli ID gia' committed: se non li
    riproducesse, la simulazione starebbe misurando un'altra formula.
    """
    proposed_intervention = canonical_regimen(proposed_components)
    rows: list[dict[str, Any]] = []
    for graph_evidence_id, current_id in sorted(current_ids.items()):
        reproduced = aggregate_claim_id(
            graph_evidence_id=graph_evidence_id,
            intervention=current_intervention,
            biomarker=biomarkers[graph_evidence_id],
            source_unit_id=source_unit_id,
        )
        if reproduced != current_id:
            raise SimulationError(
                f"{graph_evidence_id}: la formula produce {reproduced}, "
                f"l'ID committed e' {current_id}"
            )
        new_id = aggregate_claim_id(
            graph_evidence_id=graph_evidence_id,
            intervention=proposed_intervention,
            biomarker=biomarkers[graph_evidence_id],
            source_unit_id=source_unit_id,
        )
        rows.append(
            {
                "pair_id": pair_id,
                "graph_evidence_id": graph_evidence_id,
                "current_claim_id": current_id,
                "current_canonical_intervention": current_intervention,
                "proposed_canonical_intervention": proposed_intervention,
                "potential_new_claim_id": new_id,
                "identity_field_changed": "canonical_intervention_or_regimen",
                "claim_id_changes": True,
                "retirement_required": True,
                "replacement_required": True,
                "lineage": {
                    "old_claim_id": current_id,
                    "new_claim_id": new_id,
                    "terminology_decision_id": pair_id,
                },
                "qualification_link_regeneration_required": True,
                "view_regeneration_required": False,
                "claim_type_before": AGGREGATE_CLAIM_TYPE,
                "claim_type_after": AGGREGATE_CLAIM_TYPE,
                "permits_member_specific_claims_before": False,
                "permits_member_specific_claims_after": False,
                "atomized": False,
                "regimen_separated": False,
                "documentary_support_created": False,
                "applied": False,
                "reason_codes": sorted(reason_codes),
            }
        )
    for graph_evidence_id, current_id, intervention in unchanged_claims:
        rows.append(
            {
                "pair_id": "",
                "graph_evidence_id": graph_evidence_id,
                "current_claim_id": current_id,
                "current_canonical_intervention": intervention,
                "proposed_canonical_intervention": intervention,
                "potential_new_claim_id": current_id,
                "identity_field_changed": "",
                "claim_id_changes": False,
                "retirement_required": False,
                "replacement_required": False,
                "lineage": {},
                "qualification_link_regeneration_required": False,
                "view_regeneration_required": False,
                "claim_type_before": "",
                "claim_type_after": "",
                "permits_member_specific_claims_before": False,
                "permits_member_specific_claims_after": False,
                "atomized": False,
                "regimen_separated": False,
                "documentary_support_created": False,
                "applied": False,
                "reason_codes": [],
            }
        )
    return sorted(rows, key=lambda row: row["current_claim_id"])


def collisions(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Due identita' distinte che collasserebbero sullo stesso ID."""
    seen: dict[str, set[str]] = {}
    for row in rows:
        seen.setdefault(str(row["potential_new_claim_id"]), set()).add(
            str(row["current_claim_id"])
        )
    return [
        {"claim_id": key, "colliding_sources": sorted(value)}
        for key, value in sorted(seen.items())
        if len(value) > 1
    ]


def qualification_link_impact(
    simulation: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in simulation:
        if not row["claim_id_changes"]:
            continue
        rows.append(
            {
                "action": "regenerate_claim_link",
                "graph_evidence_id": row["graph_evidence_id"],
                "current_claim_id": row["current_claim_id"],
                "potential_new_claim_id": row["potential_new_claim_id"],
                "clinical_qualifiers_invented": False,
                "qualifiers_changed": False,
                "executed": False,
                "executed_at_promotion": True,
                "plan_only": True,
                "note": "Il legame va riancorato al nuovo ID; i qualificatori "
                "clinici restano quelli gia' approvati.",
            }
        )
        rows.append(
            {
                "action": "retire_statement_link",
                "graph_evidence_id": row["graph_evidence_id"],
                "current_claim_id": row["current_claim_id"],
                "potential_new_claim_id": "",
                "clinical_qualifiers_invented": False,
                "qualifiers_changed": False,
                "executed": False,
                "executed_at_promotion": True,
                "plan_only": True,
                "note": "Il legame legacy resta ritirato come in 1.2: la "
                "terminologia non lo riapre.",
            }
        )
    return sorted(rows, key=lambda row: (row["graph_evidence_id"], row["action"]))


def view_impact(groups: Sequence[str]) -> list[dict[str, Any]]:
    return [
        {
            "graph_evidence_id": group,
            "views_affected": 0,
            "view_regeneration_required": False,
            "executed": False,
            "reason": "Il piano di rigenerazione delle view della 1.2 non "
            "ancora alcuna view a questi claim.",
        }
        for group in sorted(groups)
    ]


def shadow_update_simulation(
    *,
    phase_version: str,
    verified_pairs: Sequence[str],
    unresolved_pairs: Sequence[str],
    simulation: Sequence[Mapping[str, Any]],
    found_collisions: Sequence[Mapping[str, Any]],
    counts: Mapping[str, int],
    regimen_claim_ids: Sequence[str],
) -> dict[str, Any]:
    changed = [row for row in simulation if row["claim_id_changes"]]
    return {
        "simulation_version": phase_version,
        "applied": False,
        "shadow_repository_1_2_modified": False,
        "source_repository": "qualified_claim_repository/1.2",
        "suggested_repository_version": "qualified_claim_repository/1.3",
        "suggested_model_version": "qualified_claim_model/1.1",
        "verified_mappings": sorted(verified_pairs),
        "unresolved_mappings": sorted(unresolved_pairs),
        "claims_affected": sorted(row["current_claim_id"] for row in changed),
        "claim_ids_to_replace": [
            {
                "old_claim_id": row["current_claim_id"],
                "new_claim_id": row["potential_new_claim_id"],
            }
            for row in changed
        ],
        "claims_unchanged": sorted(
            row["current_claim_id"] for row in simulation if not row["claim_id_changes"]
        ),
        "aggregate_claims_remaining_aggregate": sorted(
            row["current_claim_id"] for row in changed
        ),
        "regimen_claims_remaining_regimen": sorted(regimen_claim_ids),
        "aggregates_atomized": 0,
        "regimens_separated": 0,
        "unsupported_associations_unchanged": True,
        "unresolved_associations_unchanged": True,
        "deduplications": [],
        "collisions": list(found_collisions),
        "counts_before": dict(counts),
        "counts_after": dict(counts),
        "therapeutic_proposition_count_changed": False,
        "documentary_support_created": False,
        "note": "Il mapping cambia una rappresentazione canonica. Non crea, non "
        "fonde e non scompone proposizioni, quindi i conteggi terapeutici "
        "restano quelli della 1.2.",
    }


__all__ = [
    "AGGREGATE_CLAIM_TYPE",
    "SimulationError",
    "aggregate_claim_id",
    "claim_id_simulation",
    "collisions",
    "qualification_link_impact",
    "view_impact",
    "shadow_update_simulation",
]
