"""Scoring del retriever V3, subordinato ai gate.

Nessun peso viene ritarato in questa fase. Il modulo legge la configurazione
operativa congelata — la stessa che il retriever legacy usa — e non ne aggiunge
nessuno. Cio' che cambia rispetto al percorso operativo non e' il valore dei
pesi ma il momento in cui vengono guardati: il bucket e' gia' deciso quando lo
scoring comincia, e nessuna somma puo' cambiarlo.

La regola per bucket e' asimmetrica per costruzione:

    primary   il punteggio ordina, ed e' un ranking clinico
    warning   il punteggio ordina soltanto dentro il bucket, e solo se il gate
              ha dichiarato `ranks_within_bucket_only`
    audit     le feature vengono calcolate e registrate, il punteggio non e'
              usato per nessun ordinamento clinico
    rejected  tutti gli score sono disattivati

Su un candidato respinto le feature non vengono nemmeno valutate: `eligible`
resta falso e `contribution` resta zero su ognuna. Il motivo di esclusione viene
scritto per **ogni** feature invece che una volta sola nel risultato, perche' la
domanda che si fa leggendo un audit non e' "perche' questo candidato ha zero"
ma "perche' questa feature non ha contato".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from backend.pipeline.evidence.shadow import integrated_gates_v11 as GATE
from backend.pipeline.evidence.shadow.shadow_scoring import (
    LEGACY_PENALTIES,
    PENALTY_TO_GATE_DECISION,
    load_operational_weights,
)

SCORING_VERSION = "qualified_claim_retrieval_scoring/1.0"

# Gli assi strutturali e il peso operativo che gia' esisteva per ciascuno. La
# mappa non introduce pesi: nomina quelli congelati.
AXIS_WEIGHT = {
    "biomarker": "native_biomarker",
    "disease": "native_disease",
    "intervention_identity": "native_intervention",
    "formulation": "native_intervention",
    "direction": "native_direction",
}

# Motivi per cui una feature non contribuisce. Sono esiti, non sfumature.
EXCLUDED_REJECTED = "bucket_rejected_all_scores_disabled"
EXCLUDED_AUDIT = "bucket_audit_score_not_used_for_clinical_ranking"
EXCLUDED_GATE = "gate_incompatible_on_this_axis"
EXCLUDED_NOT_CONSTRAINED = "axis_not_constrained_by_query"
EXCLUDED_NOT_ELIGIBLE = "structural_score_not_eligible_in_this_bucket"


class RetrievalScoringError(RuntimeError):
    """Lo scoring e' stato chiamato al posto del gate, o prima di esso."""


@dataclass(frozen=True)
class ScoredFeature:
    """Una feature: valore grezzo, idoneita', contributo, motivo di esclusione."""

    name: str
    raw_value: Any
    weight: float
    eligible: bool
    contribution: float
    exclusion_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "contribution": self.contribution,
            "eligible": self.eligible,
            "exclusion_reason": self.exclusion_reason,
            "name": self.name,
            "raw_value": self.raw_value,
            "weight": self.weight,
        }


@dataclass(frozen=True)
class ClaimScore:
    """Il punteggio di un candidato, e cio' che dice di poterne fare."""

    claim_id: str
    bucket: str
    total: float
    features: tuple[ScoredFeature, ...] = ()
    ranking_score_allowed: bool = False
    ranks_within_bucket_only: bool = False
    used_for_clinical_ranking: bool = False
    all_scores_disabled: bool = False
    eligibility: dict[str, Any] = field(default_factory=dict)
    scoring_version: str = SCORING_VERSION
    weights_retuned_in_this_phase: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "all_scores_disabled": self.all_scores_disabled,
            "bucket": self.bucket,
            "claim_id": self.claim_id,
            "eligibility": dict(self.eligibility),
            "features": [item.to_dict() for item in self.features],
            "ranking_score_allowed": self.ranking_score_allowed,
            "ranks_within_bucket_only": self.ranks_within_bucket_only,
            "scoring_version": self.scoring_version,
            "total": self.total,
            "used_for_clinical_ranking": self.used_for_clinical_ranking,
            "weights_retuned_in_this_phase": False,
        }


def _axis_state(
    gate_result: GATE.IntegratedStructuralMatchResultV11,
) -> dict[str, tuple[bool, Any]]:
    """Compatibilita' e valore grezzo di ogni asse, letti dal solo gate."""
    blocking = set(gate_result.blocking_gates)
    formulation = gate_result.formulation_match_result
    disease = gate_result.disease_match_result
    return {
        "biomarker": (
            "biomarker" not in blocking,
            gate_result.biomarker_match_result.get("match_type", "not_evaluated"),
        ),
        "disease": (
            "disease" not in blocking,
            disease.get("relation_type", "not_evaluated"),
        ),
        "intervention_identity": (
            "intervention_identity" not in blocking,
            gate_result.intervention_match_result.get("match_type", "not_evaluated"),
        ),
        "formulation": (
            "formulation" not in blocking,
            formulation.get("relation_type", GATE.FORMULATION_NOT_APPLICABLE),
        ),
        "direction": (
            "direction" not in blocking,
            gate_result.direction_match_result.get(
                "direction_match_type", "not_evaluated"
            ),
        ),
    }


def score(
    gate_result: GATE.IntegratedStructuralMatchResultV11,
    *,
    weights: Mapping[str, Any] | None = None,
) -> ClaimScore:
    """Il punteggio di un candidato gia' passato dal gate.

    La firma richiede il risultato del gate e non un claim: chiamare lo scoring
    su un oggetto che il gate non ha visto e' impossibile, non sconsigliato.
    """
    table = dict((weights or load_operational_weights()).get("weights") or {})
    eligibility = dict(gate_result.score_eligibility)
    bucket = gate_result.final_bucket

    rejected = bucket == GATE.REJECTED_BUCKET
    audit = bucket == GATE.AUDIT_BUCKET
    structural_eligible = bool(eligibility.get("structural_score_eligible"))
    within_bucket_only = bool(eligibility.get("ranks_within_bucket_only"))

    features: list[ScoredFeature] = []
    for axis, (compatible, raw) in sorted(_axis_state(gate_result).items()):
        weight = float(table.get(AXIS_WEIGHT[axis], 0))
        not_constrained = raw in (
            "not_evaluated",
            "not_applicable",
            GATE.FORMULATION_NOT_APPLICABLE,
        )
        if rejected:
            reason = EXCLUDED_REJECTED
        elif audit:
            reason = EXCLUDED_AUDIT
        elif not compatible:
            reason = EXCLUDED_GATE
        elif not_constrained:
            reason = EXCLUDED_NOT_CONSTRAINED
        elif not (structural_eligible or within_bucket_only):
            reason = EXCLUDED_NOT_ELIGIBLE
        else:
            reason = ""
        eligible = not reason
        features.append(
            ScoredFeature(
                name=axis,
                raw_value=raw,
                weight=weight,
                eligible=eligible,
                contribution=weight if eligible else 0.0,
                exclusion_reason=reason,
            )
        )

    # Le quattro penalita' legacy restano registrate e non applicate: ognuna
    # codificava come sconto numerico una condizione che nel modello e' una
    # decisione di bucket, e uno sconto si compensa mentre un bucket no.
    for name in LEGACY_PENALTIES:
        features.append(
            ScoredFeature(
                name=name,
                raw_value=table.get(name),
                weight=float(table.get(name, 0)),
                eligible=False,
                contribution=0.0,
                exclusion_reason=f"gate_decision_supersedes_penalty:{PENALTY_TO_GATE_DECISION[name]}",
            )
        )

    total = sum(item.contribution for item in features)
    return ClaimScore(
        claim_id=gate_result.claim_id,
        bucket=bucket,
        total=total,
        features=tuple(features),
        ranking_score_allowed=structural_eligible and not (rejected or audit),
        ranks_within_bucket_only=within_bucket_only and not (rejected or audit),
        used_for_clinical_ranking=bucket == GATE.PRIMARY_BUCKET and structural_eligible,
        all_scores_disabled=rejected,
        eligibility=eligibility,
    )


def check_score_cannot_change_bucket(
    gate_result: GATE.IntegratedStructuralMatchResultV11, hypothetical_score: float
) -> None:
    """Solleva se un punteggio arbitrario riuscisse a spostare un candidato."""
    GATE.check_no_score_survives_a_blocking_gate(gate_result, hypothetical_score)
    computed = score(gate_result)
    if computed.bucket != gate_result.final_bucket:
        raise RetrievalScoringError(
            f"{gate_result.claim_id}: lo scoring ha cambiato il bucket"
        )
    if computed.all_scores_disabled and computed.total != 0.0:
        raise RetrievalScoringError(
            f"{gate_result.claim_id}: punteggio non nullo in un bucket a score disabilitati"
        )
    if computed.used_for_clinical_ranking and gate_result.blocking_gates:
        raise RetrievalScoringError(
            f"{gate_result.claim_id}: ranking clinico concesso con gate bloccanti "
            f"{list(gate_result.blocking_gates)}"
        )


def scoring_contract() -> dict[str, Any]:
    """Descrizione serializzabile dello scoring, per gli artefatti della fase."""
    return {
        "axis_weight_names": dict(sorted(AXIS_WEIGHT.items())),
        "bucket_rules": {
            GATE.AUDIT_BUCKET: "feature registrate, nessun ranking clinico",
            GATE.PRIMARY_BUCKET: "ranking score consentito",
            GATE.REJECTED_BUCKET: "tutti gli score disabilitati",
            GATE.WARNING_BUCKET: "score interno al bucket quando il gate lo consente",
        },
        "gold_used_for_weights": False,
        "legacy_penalties_registered_not_applied": list(LEGACY_PENALTIES),
        "operational_weights_source": "qualified_retriever_scoring_config.json",
        "records_per_feature": [
            "raw_value",
            "eligible",
            "weight",
            "contribution",
            "exclusion_reason",
        ],
        "scoring_subordinate_to_gates": True,
        "scoring_version": SCORING_VERSION,
        "weights_retuned_in_this_phase": False,
    }


__all__ = [
    "AXIS_WEIGHT",
    "SCORING_VERSION",
    "ClaimScore",
    "RetrievalScoringError",
    "ScoredFeature",
    "check_score_cannot_change_bucket",
    "score",
    "scoring_contract",
]
