"""Gate strutturale claim-type-aware.

Il gate decide l'eleggibilita' *prima* e *indipendentemente* dal punteggio. E'
l'inversione rispetto alla pipeline operativa, dove un candidato entra nel
ranking e poi viene penalizzato: una penalita' e' un numero, e un numero puo'
essere compensato da altri numeri. Un mapping pending, un'associazione non
sostenuta, un aggregato non separabile non sono cose "meno buone" da scontare;
sono cose che non appartengono al ranking primario, e la differenza fra le due
formulazioni si vede quando i pesi cambiano.

Le tabelle di decisione non sono ridefinite qui: vengono dal contratto congelato
nella fase precedente (`claim_type_retrieval_contract`), che resta l'unica fonte
di verita' su quali match type siano primary, warning o audit. Questo modulo le
applica agli oggetti tipizzati del modello shadow invece che ai dizionari della
simulazione.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from benchmarks.mtb_evidence.evaluation.claim_type_retrieval_contract import (
    MATCH_TYPES,
    POSITIVE_SCORE_FORBIDDEN,
    classify_query,
    structural_match,
)

GATE_VERSION = "claim_structural_gate/1.0"

PRIMARY_BUCKET = "primary_ranked_results"
WARNING_BUCKET = "retained_with_warning"
AUDIT_BUCKET = "audit_only_results"
REJECTED_BUCKET = "rejected_by_native_constraints"

BUCKETS = (PRIMARY_BUCKET, WARNING_BUCKET, AUDIT_BUCKET, REJECTED_BUCKET)


class GateError(RuntimeError):
    """Il gate e' stato aggirato o interrogato fuori ordine."""


@dataclass(frozen=True)
class StructuralMatchResult:
    """Contratto congelato, piu' l'esito di idoneita' allo scoring."""

    claim_id: str
    parent_graph_evidence_id: str
    claim_type: str
    query_intervention_type: str
    query_interventions: tuple[str, ...]
    claim_interventions: tuple[str, ...]
    intervention_match_type: str
    biomarker_match_type: str
    disease_match_type: str
    direction_match_type: str
    polarity_match_type: str
    primary_candidate_eligible: bool
    warning_eligible: bool
    audit_only: bool
    rejected_by_native_constraints: bool
    bucket: str
    score_eligibility: dict[str, Any] = field(default_factory=dict)
    exclusion_reason_codes: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()
    explanation_codes: tuple[str, ...] = ()
    gate_version: str = GATE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "parent_graph_evidence_id": self.parent_graph_evidence_id,
            "claim_type": self.claim_type,
            "query_intervention_type": self.query_intervention_type,
            "query_interventions": list(self.query_interventions),
            "claim_interventions": list(self.claim_interventions),
            "intervention_match_type": self.intervention_match_type,
            "biomarker_match_type": self.biomarker_match_type,
            "disease_match_type": self.disease_match_type,
            "direction_match_type": self.direction_match_type,
            "polarity_match_type": self.polarity_match_type,
            "primary_candidate_eligible": self.primary_candidate_eligible,
            "warning_eligible": self.warning_eligible,
            "audit_only": self.audit_only,
            "rejected_by_native_constraints": self.rejected_by_native_constraints,
            "bucket": self.bucket,
            "score_eligibility": dict(self.score_eligibility),
            "exclusion_reason_codes": list(self.exclusion_reason_codes),
            "warning_codes": list(self.warning_codes),
            "explanation_codes": list(self.explanation_codes),
            "gate_version": self.gate_version,
        }


def gate_payload(obj: Any) -> dict[str, Any]:
    """Rappresentazione dell'oggetto tipizzato nel vocabolario del contratto.

    E' l'unico punto di traduzione fra il modello shadow e le tabelle congelate.
    Il parent e le due associazioni entrano con il proprio kind, non travestiti da
    claim: e' quello che li manda in audit invece che nel ranking.
    """
    kind = getattr(obj, "kind", None) or obj.claim_type

    if kind == "graph_evidence_record":
        return {
            "claim_id": obj.parent_id,
            "graph_evidence_parent": obj.graph_evidence_id,
            "claim_type": "graph_evidence_record",
            "intervention_members": list(obj.original_intervention_associations),
            "biomarker": obj.biomarker_context or "",
            "disease_scope": obj.disease_context or "",
            "direction": "unknown",
            "polarity": "unknown",
        }

    if kind in ("unsupported_association", "unresolved_association"):
        return {
            "claim_id": obj.association_id,
            "graph_evidence_parent": obj.graph_evidence_id,
            "claim_type": kind,
            "intervention_members": [obj.intervention_literal],
            "biomarker": obj.biomarker,
            "disease_scope": "",
            "direction": "unknown",
            "polarity": "unknown",
        }

    payload = {
        "claim_id": obj.claim_id,
        "graph_evidence_parent": obj.graph_evidence_id,
        "claim_type": obj.claim_type,
        "intervention_members": list(obj.intervention_members),
        "biomarker": obj.biomarker,
        "disease_scope": obj.disease_scope,
        "direction": obj.direction,
        "polarity": obj.polarity,
        "evidence_setting": obj.evidence_setting,
    }
    if obj.claim_type == "aggregate_intervention_claim":
        # `drug_class` e' il vocabolario del contratto congelato; il modello usa
        # `intervention_class`. La traduzione avviene qui e in nessun altro punto.
        payload["aggregate_kind"] = (
            "drug_class" if obj.aggregate_type == "intervention_class" else obj.aggregate_type
        )
    return payload


def evaluate(query: Mapping[str, Any], obj: Any) -> StructuralMatchResult:
    """Applica il gate a un oggetto tipizzato. Nessun punteggio entra qui."""
    payload = gate_payload(obj)
    base = structural_match(query, payload)
    spec = MATCH_TYPES[base.intervention_match_type]
    rejected = base.bucket == REJECTED_BUCKET

    eligibility = {
        "structural_score_eligible": bool(spec["structural_score_eligible"] and not rejected),
        "qualified_score_eligible": bool(spec["qualified_score_eligible"] and not rejected),
        "final_ranking_eligible": base.primary_candidate_eligible,
        "positive_score_forbidden": base.intervention_match_type in POSITIVE_SCORE_FORBIDDEN,
        "ranks_within_bucket_only": base.bucket == WARNING_BUCKET,
        "bucket": base.bucket,
    }

    # Un claim deprecato non e' un candidato, qualunque sia il suo match type.
    # E' una condizione dell'oggetto, non della query, e va applicata dopo il
    # match ma sempre prima di qualunque punteggio.
    deprecated = bool(getattr(obj, "deprecated", False))
    primary = base.primary_candidate_eligible and not deprecated
    warning_eligible = base.warning_eligible and not deprecated
    audit_only = base.audit_only or (deprecated and not rejected)
    bucket = base.bucket
    exclusions = base.exclusion_reason_codes
    if deprecated and not rejected:
        bucket = AUDIT_BUCKET
        exclusions = exclusions + ("CLAIM_DEPRECATED",)
        eligibility.update(
            {
                "structural_score_eligible": False,
                "qualified_score_eligible": False,
                "final_ranking_eligible": False,
                "positive_score_forbidden": True,
                "ranks_within_bucket_only": False,
                "bucket": AUDIT_BUCKET,
            }
        )

    return StructuralMatchResult(
        claim_id=base.claim_id,
        parent_graph_evidence_id=base.parent_graph_evidence_id,
        claim_type=base.claim_type,
        query_intervention_type=base.query_intervention_type,
        query_interventions=base.query_interventions,
        claim_interventions=base.claim_interventions,
        intervention_match_type=base.intervention_match_type,
        biomarker_match_type=base.biomarker_match_type,
        disease_match_type=base.disease_match_type,
        direction_match_type=base.direction_match_type,
        polarity_match_type=base.polarity_match_type,
        primary_candidate_eligible=primary,
        warning_eligible=warning_eligible,
        audit_only=audit_only,
        rejected_by_native_constraints=rejected,
        bucket=bucket,
        score_eligibility=eligibility,
        exclusion_reason_codes=exclusions,
        warning_codes=base.warning_codes,
        explanation_codes=base.explanation_codes,
    )


def classify(query: Mapping[str, Any]) -> str:
    """Tipo della query secondo il contratto congelato."""
    return classify_query(query)
