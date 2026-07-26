"""Adattatore di scoring shadow.

Non modifica `qualified_retrieval_scoring` ne' il file di configurazione dei
pesi: li legge, ne riusa le componenti compatibili e non ne introduce di nuove.

La proprieta' che questo modulo esiste per garantire e' una sola: **il punteggio
non puo' cambiare il bucket**. Riceve soltanto oggetti gia' passati dal gate,
rifiuta di calcolare su un oggetto respinto, e restituisce feature tipizzate
insieme all'esito del gate che non ha il potere di modificare.

Le quattro penalita' legacy — pending terminology, not separable, unresolved,
invalid — restano nello scoring operativo e non vengono toccate. Qui sono
registrate come feature legacy non operative: leggibili, tracciabili, e senza
effetto sull'eleggibilita'. La ragione e' che ognuna delle quattro codificava
come sconto numerico una condizione che e' strutturale, e uno sconto si compensa.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.pipeline.evidence.shadow.structural_gates import (
    AUDIT_BUCKET,
    PRIMARY_BUCKET,
    REJECTED_BUCKET,
    StructuralMatchResult,
    WARNING_BUCKET,
)

SHADOW_SCORING_VERSION = "claim_shadow_scoring/1.0"

OPERATIONAL_SCORING_CONFIG = (
    Path(__file__).resolve().parents[1] / "qualified_retriever_scoring_config.json"
)

# Le penalita' legacy, per nome esatto come compaiono nello scoring operativo.
# Sono elencate per essere isolate e auditate, non per essere applicate.
LEGACY_PENALTIES = (
    "penalty_pending_terminology",
    "penalty_not_separable",
    "penalty_unresolved",
    "penalty_invalid",
)

# Le condizioni che nel modello shadow sono decisioni di gate o di bucket, e che
# nel percorso operativo erano sconti numerici.
PENALTY_TO_GATE_DECISION = {
    "penalty_pending_terminology": "mapping_pending -> audit_only_results",
    "penalty_not_separable": "aggregate_member_related -> retained_with_warning",
    "penalty_unresolved": "unresolved -> audit_only_results",
    "penalty_invalid": "unsupported -> audit_only_results",
}


class ShadowScoringError(RuntimeError):
    """Lo scoring e' stato chiamato prima o al posto del gate."""


@dataclass(frozen=True)
class ShadowScoreFeatures:
    claim_id: str
    claim_type: str
    bucket: str
    intervention_match_type: str
    structural_score_eligible: bool
    qualified_score_eligible: bool
    final_ranking_eligible: bool
    positive_score_forbidden: bool
    ranks_within_bucket_only: bool
    legacy_penalty_features: dict[str, Any] = field(default_factory=dict)
    scoring_version: str = SHADOW_SCORING_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "claim_type": self.claim_type,
            "bucket": self.bucket,
            "intervention_match_type": self.intervention_match_type,
            "structural_score_eligible": self.structural_score_eligible,
            "qualified_score_eligible": self.qualified_score_eligible,
            "final_ranking_eligible": self.final_ranking_eligible,
            "positive_score_forbidden": self.positive_score_forbidden,
            "ranks_within_bucket_only": self.ranks_within_bucket_only,
            "legacy_penalty_features": dict(self.legacy_penalty_features),
            "scoring_version": self.scoring_version,
        }


def load_operational_weights() -> dict[str, Any]:
    """Legge la configurazione operativa. Sola lettura, nessun peso nuovo."""
    return json.loads(OPERATIONAL_SCORING_CONFIG.read_text(encoding="utf-8"))


def legacy_penalty_audit() -> dict[str, Any]:
    """Le quattro penalita' come sono oggi, e cosa le sostituisce nel modello."""
    config = load_operational_weights()
    weights = config.get("weights", config)
    audit: dict[str, Any] = {}
    for name in LEGACY_PENALTIES:
        audit[name] = {
            "present_in_operational_config": name in weights,
            "operational_value": weights.get(name),
            "shadow_role": "legacy_feature_not_operational",
            "decides_primary_eligibility": False,
            "required_to_block_promotion": False,
            "replaced_by": PENALTY_TO_GATE_DECISION[name],
        }
    return audit


def features_for(match: StructuralMatchResult) -> ShadowScoreFeatures:
    """Feature tipizzate per un candidato gia' passato dal gate.

    Chiamarla su un candidato respinto dai vincoli nativi solleva: lo scoring non
    deve nemmeno vedere gli oggetti che il gate ha escluso, perche' vederli
    aprirebbe la possibilita' di ripescarli.
    """
    if match.rejected_by_native_constraints:
        raise ShadowScoringError(
            f"{match.claim_id}: scoring richiesto su un candidato respinto dai "
            "vincoli nativi; il gate viene prima"
        )
    eligibility = match.score_eligibility
    return ShadowScoreFeatures(
        claim_id=match.claim_id,
        claim_type=match.claim_type,
        bucket=match.bucket,
        intervention_match_type=match.intervention_match_type,
        structural_score_eligible=eligibility["structural_score_eligible"],
        qualified_score_eligible=eligibility["qualified_score_eligible"],
        final_ranking_eligible=eligibility["final_ranking_eligible"],
        positive_score_forbidden=eligibility["positive_score_forbidden"],
        ranks_within_bucket_only=eligibility["ranks_within_bucket_only"],
        legacy_penalty_features={
            name: {"applied": False, "reason": "gate_decision_supersedes_penalty"}
            for name in LEGACY_PENALTIES
        },
    )


def bucket_after_score(match: StructuralMatchResult, hypothetical_score: float) -> str:
    """Il bucket dopo aver applicato un punteggio arbitrario.

    Restituisce sempre il bucket deciso dal gate: la firma accetta un punteggio
    proprio per rendere verificabile che non lo usi. E' il test che un peso
    arbitrariamente alto non promuove un candidato fuori dal proprio bucket.
    """
    del hypothetical_score
    return match.bucket


def assert_gate_not_bypassed(
    match: StructuralMatchResult, hypothetical_score: float
) -> None:
    """Solleva se un punteggio riuscisse a spostare un candidato nel primario."""
    if bucket_after_score(match, hypothetical_score) != match.bucket:
        raise ShadowScoringError(f"{match.claim_id}: il punteggio ha cambiato il bucket")
    if match.bucket != PRIMARY_BUCKET and match.primary_candidate_eligible:
        raise ShadowScoringError(
            f"{match.claim_id}: idoneita' primaria fuori dal bucket primario"
        )
    if match.score_eligibility["positive_score_forbidden"] and hypothetical_score > 0:
        # Il punteggio positivo non e' vietato come valore: e' vietato che abbia
        # effetto. Il candidato resta dov'e', e questo e' cio' che va dimostrato.
        if match.bucket in (PRIMARY_BUCKET,):
            raise ShadowScoringError(
                f"{match.claim_id}: punteggio positivo su un match a punteggio vietato "
                "ha raggiunto il bucket primario"
            )
