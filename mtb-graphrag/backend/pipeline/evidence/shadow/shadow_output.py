"""Output contract tipizzato del retrieval shadow.

`intervention_representation` e' il campo che porta il peso di tutto il modello.
Il tipo dell'intervento — atomico, regime, classe, aggregato, nessuno — deve
sopravvivere fino al consumatore finale, perche' e' li' che l'errore si
ricostituirebbe: un regime reso come farmaco singolo nel dossier afferma di nuovo
quello che il modello ha smesso di affermare nei dati.

Da qui i quattro divieti espressi come controlli e non come raccomandazioni:
nessun regime appiattito su un componente, nessun aggregato appiattito sul primo
membro, nessun parent presentato come claim, nessuna associazione non sostenuta
presentata come evidenza positiva.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.pipeline.evidence.shadow.structural_gates import (
    AUDIT_BUCKET,
    PRIMARY_BUCKET,
    REJECTED_BUCKET,
    StructuralMatchResult,
    WARNING_BUCKET,
)

OUTPUT_CONTRACT_VERSION = "qualified_claim_retrieval_result/1.0"

REPRESENTATION_ATOMIC = "atomic"
REPRESENTATION_REGIMEN = "regimen"
REPRESENTATION_CLASS = "class"
REPRESENTATION_AGGREGATE = "aggregate"
REPRESENTATION_NONE = "none"

INTERVENTION_REPRESENTATIONS = (
    REPRESENTATION_ATOMIC,
    REPRESENTATION_REGIMEN,
    REPRESENTATION_CLASS,
    REPRESENTATION_AGGREGATE,
    REPRESENTATION_NONE,
)


class OutputContractError(ValueError):
    """L'output avrebbe appiattito o travisato la rappresentazione."""


def representation_for(obj: Any) -> str:
    """Il tipo di rappresentazione dell'intervento, derivato dal tipo dell'oggetto."""
    kind = getattr(obj, "kind", None) or getattr(obj, "claim_type", None)
    if kind == "atomic_intervention_claim":
        return REPRESENTATION_ATOMIC
    if kind == "regimen_claim":
        return REPRESENTATION_REGIMEN
    if kind == "aggregate_intervention_claim":
        return (
            REPRESENTATION_CLASS
            if obj.aggregate_type == "intervention_class"
            else REPRESENTATION_AGGREGATE
        )
    # Parent e associazioni non portano una terapia: `none` non e' un valore
    # mancante, e' l'affermazione che non c'e' un intervento da rappresentare.
    return REPRESENTATION_NONE


def intervention_payload(obj: Any) -> dict[str, Any]:
    """Rappresentazione tipizzata, mai una stringa singola per regimi e aggregati."""
    representation = representation_for(obj)
    if representation == REPRESENTATION_ATOMIC:
        return {
            "intervention_representation": representation,
            "atomic_intervention": obj.intervention,
            "members": [obj.intervention],
        }
    if representation == REPRESENTATION_REGIMEN:
        return {
            "intervention_representation": representation,
            "regimen_components": list(obj.canonical_component_set),
            "members": list(obj.canonical_component_set),
            "result_attributed_to": "combination",
            "propagates_to_components": False,
        }
    if representation in (REPRESENTATION_CLASS, REPRESENTATION_AGGREGATE):
        return {
            "intervention_representation": representation,
            "aggregate_label": obj.aggregate_label,
            "aggregate_type": obj.aggregate_type,
            "aggregate_members_literal": list(obj.aggregate_members_literal),
            "members": [obj.aggregate_label],
            "permits_member_specific_claims": False,
        }
    return {"intervention_representation": REPRESENTATION_NONE, "members": []}


@dataclass(frozen=True)
class QualifiedClaimRetrievalResult:
    """Un candidato valutato, con il proprio tipo e il proprio bucket."""

    query_id: str
    object_id: str
    object_kind: str
    parent_graph_evidence_id: str
    bucket: str
    intervention_representation: str
    intervention: dict[str, Any]
    biomarker: str
    disease_scope: str
    direction: str
    polarity: str
    structural_match: dict[str, Any]
    score_eligibility: dict[str, Any]
    is_positive_evidence: bool
    warning_codes: tuple[str, ...] = ()
    exclusion_reason_codes: tuple[str, ...] = ()
    explanation_codes: tuple[str, ...] = ()
    contract_version: str = OUTPUT_CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "object_id": self.object_id,
            "object_kind": self.object_kind,
            "parent_graph_evidence_id": self.parent_graph_evidence_id,
            "bucket": self.bucket,
            "intervention_representation": self.intervention_representation,
            "intervention": dict(self.intervention),
            "biomarker": self.biomarker,
            "disease_scope": self.disease_scope,
            "direction": self.direction,
            "polarity": self.polarity,
            "structural_match": dict(self.structural_match),
            "score_eligibility": dict(self.score_eligibility),
            "is_positive_evidence": self.is_positive_evidence,
            "warning_codes": list(self.warning_codes),
            "exclusion_reason_codes": list(self.exclusion_reason_codes),
            "explanation_codes": list(self.explanation_codes),
            "contract_version": self.contract_version,
        }


def build_result(
    query_id: str, obj: Any, match: StructuralMatchResult
) -> QualifiedClaimRetrievalResult:
    kind = getattr(obj, "kind", None) or obj.claim_type
    payload = intervention_payload(obj)
    representation = payload["intervention_representation"]

    # Evidenza positiva significa: e' un claim, e' nel bucket primario o warning,
    # e non e' un'associazione. Un'associazione non sostenuta non diventa mai
    # positiva, per nessun punteggio e per nessuna query.
    is_positive = bool(
        getattr(obj, "is_claim", False)
        and match.bucket in (PRIMARY_BUCKET, WARNING_BUCKET)
        and not match.score_eligibility.get("positive_score_forbidden", False)
    )

    result = QualifiedClaimRetrievalResult(
        query_id=query_id,
        object_id=match.claim_id,
        object_kind=kind,
        parent_graph_evidence_id=match.parent_graph_evidence_id,
        bucket=match.bucket,
        intervention_representation=representation,
        intervention=payload,
        biomarker=getattr(obj, "biomarker", "") or getattr(obj, "biomarker_context", "") or "",
        disease_scope=getattr(obj, "disease_scope", "") or getattr(obj, "disease_context", "") or "",
        direction=getattr(obj, "direction", "unknown"),
        polarity=getattr(obj, "polarity", "unknown"),
        structural_match=match.to_dict(),
        score_eligibility=dict(match.score_eligibility),
        is_positive_evidence=is_positive,
        warning_codes=match.warning_codes,
        exclusion_reason_codes=match.exclusion_reason_codes,
        explanation_codes=match.explanation_codes,
    )
    check_output_invariants(result)
    return result


def check_output_invariants(result: QualifiedClaimRetrievalResult) -> None:
    """I quattro divieti, verificati invece che raccomandati."""
    payload = result.intervention
    representation = result.intervention_representation

    if representation not in INTERVENTION_REPRESENTATIONS:
        raise OutputContractError(
            f"{result.object_id}: rappresentazione sconosciuta {representation!r}"
        )

    if representation == REPRESENTATION_REGIMEN and len(payload.get("members", ())) < 2:
        raise OutputContractError(
            f"{result.object_id}: regime appiattito a un singolo intervento"
        )

    if representation in (REPRESENTATION_CLASS, REPRESENTATION_AGGREGATE):
        members = payload.get("members", ())
        if members and members != [payload.get("aggregate_label")]:
            raise OutputContractError(
                f"{result.object_id}: aggregato appiattito su un membro"
            )

    if result.object_kind == "graph_evidence_record":
        if result.bucket != AUDIT_BUCKET and result.bucket != REJECTED_BUCKET:
            raise OutputContractError(
                f"{result.object_id}: contenitore di provenienza presentato come claim"
            )
        if result.is_positive_evidence:
            raise OutputContractError(
                f"{result.object_id}: contenitore di provenienza dato come evidenza"
            )

    if result.object_kind in ("unsupported_association", "unresolved_association"):
        if result.is_positive_evidence:
            raise OutputContractError(
                f"{result.object_id}: associazione {result.object_kind} presentata "
                "come evidenza positiva"
            )
        if result.bucket == PRIMARY_BUCKET:
            raise OutputContractError(
                f"{result.object_id}: associazione nel bucket primario"
            )
