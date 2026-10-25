"""Reidratazione degli oggetti tipizzati dai record del corpus promosso.

Il corpus e' scritto in JSONL: sul disco un claim atomico e un aggregato sono
due dizionari, e la differenza fra loro sopravvive solo nel campo `claim_type`.
I gate congelati non lavorano su dizionari — lavorano sui tipi del modello
shadow, dove la differenza e' nella classe e non in un campo — e questo modulo
e' il punto in cui i record tornano a essere quei tipi.

La reidratazione non normalizza, non completa e non deduce. Un record che non
porta i campi obbligatori del proprio tipo solleva: e' cio' che rende il corpus
verificabile invece che interpretabile. In particolare un aggregato
canonicalizzato torna `CanonicalizedAggregateClaim` e non
`AggregateInterventionClaim`, perche' la prima classe conserva canonici e
letterali di fonte separati — ed e' quella separazione a far si' che
`evidence:1851` resti raggiungibile sia con `infigratinib` sia con `BGJ398`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from backend.pipeline.evidence.shadow.associations import (
    UnresolvedAssociation,
    UnsupportedAssociation,
)
from backend.pipeline.evidence.shadow.claims import (
    AggregateInterventionClaim,
    AtomicInterventionClaim,
    RegimenClaim,
)
from backend.pipeline.evidence.shadow.non_therapeutic_claims import (
    DiagnosticClaim,
    PrognosticClaim,
)
from backend.pipeline.evidence.shadow.parent import GraphEvidenceRecord
from backend.pipeline.evidence.shadow.terminology_v13 import CanonicalizedAggregateClaim


class ClaimRehydrationError(RuntimeError):
    """Un record del corpus non ha un oggetto tipizzato corrispondente."""


def _tuple(value: Any) -> tuple[Any, ...]:
    return tuple(value or ())


def _locators(value: Any) -> tuple[dict[str, Any], ...]:
    return tuple(dict(item) for item in (value or ()))


def _common(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "claim_id": str(record["claim_id"]),
        "parent_id": str(record["parent_id"]),
        "graph_evidence_id": str(record["graph_evidence_id"]),
        "biomarker": str(record.get("biomarker") or ""),
        "disease_scope": str(record.get("disease_scope") or ""),
        "direction": str(record.get("direction") or ""),
        "polarity": str(record.get("polarity") or ""),
        "source_unit_ids": tuple(str(item) for item in _tuple(record.get("source_unit_ids"))),
        "locators": _locators(record.get("locators")),
        "review_status": str(record.get("review_status") or "not_reviewed"),
        "provenance": dict(record.get("provenance") or {}),
        "deprecated": bool(record.get("deprecated", False)),
    }


def _therapeutic_extras(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "evidence_setting": record.get("evidence_setting"),
    }


def _non_therapeutic_common(record: Mapping[str, Any]) -> dict[str, Any]:
    # I claim non terapeutici non hanno `evidence_setting`: la loro base non
    # discende da quella terapeutica, e il campo non viene aggiunto qui.
    return _common(record) | {
        "qualification_link_ids": tuple(
            str(item) for item in _tuple(record.get("qualification_link_ids"))
        ),
        "propagation_policy": str(record.get("propagation_policy") or "prototype_only"),
        "legacy_statement_ids": tuple(
            str(item) for item in _tuple(record.get("legacy_statement_ids"))
        ),
        "limitation_codes": tuple(
            str(item) for item in _tuple(record.get("limitation_codes"))
        ),
        "hard_filterable": bool(record.get("hard_filterable", False)),
        "final_evaluable": bool(record.get("final_evaluable", False)),
    }


def claim_object(record: Mapping[str, Any]) -> Any:
    """L'oggetto tipizzato corrispondente al record, o un errore."""
    claim_type = str(record.get("claim_type") or "")

    if claim_type == "atomic_intervention_claim":
        return AtomicInterventionClaim(
            **_common(record),
            **_therapeutic_extras(record),
            intervention=str(record["intervention"]),
            qualification_link_ids=tuple(
                str(item) for item in _tuple(record.get("qualification_link_ids"))
            ),
            propagation_policy=str(record.get("propagation_policy") or "prototype_only"),
            legacy_statement_ids=tuple(
                str(item) for item in _tuple(record.get("legacy_statement_ids"))
            ),
            migration_origin=record.get("migration_origin"),
            documentary_revalidation_completed=bool(
                record.get("documentary_revalidation_completed", False)
            ),
            warnings=tuple(str(item) for item in _tuple(record.get("warnings"))),
            mapping_pending=bool(record.get("mapping_pending", False)),
        )

    if claim_type == "regimen_claim":
        return RegimenClaim(
            **_common(record),
            **_therapeutic_extras(record),
            regimen_components=tuple(str(item) for item in record["regimen_components"]),
            migration_origin=record.get("migration_origin"),
        )

    if claim_type == "aggregate_intervention_claim":
        aggregate = {
            **_common(record),
            **_therapeutic_extras(record),
            "aggregate_type": str(record["aggregate_type"]),
            "aggregate_label": str(record["aggregate_label"]),
            "aggregate_members_literal": tuple(
                str(item) for item in _tuple(record.get("aggregate_members_literal"))
            ),
            "migration_origin": record.get("migration_origin"),
        }
        canonical = _tuple(record.get("canonical_members"))
        literal = _tuple(record.get("source_literal_members"))
        if canonical and literal:
            # Aggregato canonicalizzato: i due insiemi restano separati, ed e'
            # la separazione che tiene il claim raggiungibile con il termine
            # della fonte anche dopo la canonicalizzazione.
            return CanonicalizedAggregateClaim(
                **aggregate,
                canonical_members=tuple(str(item) for item in canonical),
                source_literal_members=tuple(str(item) for item in literal),
                terminology_provenance=dict(record.get("terminology_provenance") or {}),
            )
        return AggregateInterventionClaim(**aggregate)

    if claim_type == "diagnostic_claim":
        return DiagnosticClaim(
            **_non_therapeutic_common(record),
            diagnostic_subject=str(record.get("diagnostic_subject") or ""),
            diagnostic_interpretation=str(
                record.get("diagnostic_interpretation") or "unknown"
            ),
            assay_or_method=record.get("assay_or_method"),
            population_or_sample_scope=record.get("population_or_sample_scope"),
            prevalence_attributable_to_subject=bool(
                record.get("prevalence_attributable_to_subject", False)
            ),
        )

    if claim_type == "prognostic_claim":
        return PrognosticClaim(
            **_non_therapeutic_common(record),
            prognostic_subject=str(record.get("prognostic_subject") or ""),
            outcome=str(record.get("outcome") or ""),
            population_scope=record.get("population_scope"),
        )

    raise ClaimRehydrationError(
        f"{record.get('claim_id')!r}: claim_type senza oggetto tipizzato: {claim_type!r}"
    )


def _association_common(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "association_id": str(record["association_id"]),
        "parent_id": str(record["parent_id"]),
        "graph_evidence_id": str(record["graph_evidence_id"]),
        "intervention_literal": str(record.get("intervention_literal") or ""),
        "biomarker": str(record.get("biomarker") or ""),
        "source_unit_ids": tuple(str(item) for item in _tuple(record.get("source_unit_ids"))),
        "locators": _locators(record.get("locators")),
        "review_status": str(record.get("review_status") or "not_reviewed"),
        "provenance": dict(record.get("provenance") or {}),
    }


def unsupported_object(record: Mapping[str, Any]) -> UnsupportedAssociation:
    return UnsupportedAssociation(
        **_association_common(record),
        reason_codes=tuple(str(item) for item in _tuple(record.get("reason_codes"))),
    )


def unresolved_object(record: Mapping[str, Any]) -> UnresolvedAssociation:
    return UnresolvedAssociation(
        **_association_common(record),
        unresolved_reason_codes=tuple(
            str(item)
            for item in _tuple(
                record.get("unresolved_reason_codes") or record.get("reason_codes")
            )
        ),
        terminology_status=record.get("terminology_status"),
    )


def parent_object(record: Mapping[str, Any]) -> GraphEvidenceRecord:
    return GraphEvidenceRecord(
        parent_id=str(record["parent_id"]),
        graph_evidence_id=str(record["graph_evidence_id"]),
        source_ids=tuple(str(item) for item in _tuple(record.get("source_ids"))),
        source_record_ids=tuple(
            str(item) for item in _tuple(record.get("source_record_ids"))
        ),
        raw_v2_records=tuple(dict(item) for item in _tuple(record.get("raw_v2_records"))),
        biomarker_context=record.get("biomarker_context"),
        disease_context=record.get("disease_context"),
        original_intervention_associations=tuple(
            str(item) for item in _tuple(record.get("original_intervention_associations"))
        ),
        adapter_lineage=tuple(str(item) for item in _tuple(record.get("adapter_lineage"))),
        review_status=str(record.get("review_status") or "not_reviewed"),
        deprecated_statement_ids=tuple(
            str(item) for item in _tuple(record.get("deprecated_statement_ids"))
        ),
        child_claim_ids=tuple(str(item) for item in _tuple(record.get("child_claim_ids"))),
        unsupported_association_ids=tuple(
            str(item) for item in _tuple(record.get("unsupported_association_ids"))
        ),
        unresolved_association_ids=tuple(
            str(item) for item in _tuple(record.get("unresolved_association_ids"))
        ),
        provenance=dict(record.get("provenance") or {}),
    )


def claim_objects(records: Sequence[Mapping[str, Any]]) -> tuple[Any, ...]:
    """Tutti i claim reidratati, nell'ordine in cui il corpus li elenca."""
    return tuple(claim_object(record) for record in records)


__all__ = [
    "ClaimRehydrationError",
    "claim_object",
    "claim_objects",
    "parent_object",
    "unresolved_object",
    "unsupported_object",
]
