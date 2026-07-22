"""Valutazione del linker contro il gold dei collegamenti.

Ogni metrica qui restituisce `not_evaluable` quando il denominatore non esiste,
invece di 0.0. La differenza non e' formale: uno 0.0 in una tabella viene letto
come «il sistema sbaglia sempre», mentre la situazione reale e' «non e' stato
misurato». Su un lavoro che finisce in tesi, la seconda affermazione e' l'unica
difendibile.

La precisione conta piu' del recall, e le metriche sono ordinate di conseguenza.
Uno statement non qualificato lascia il retriever al comportamento V2; uno
statement qualificato con setting o linea sbagliati produce un filtro che scarta
l'evidenza giusta o ne ammette una inapplicabile, e nessuna metrica a valle lo
distingue da una qualificazione corretta.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from backend.pipeline.evidence.qualification_gold import (
    AMBIGUOUS_LINK,
    CONFLICTING_LINK,
    INVALID_LINK,
    PARTIAL_LINK,
    VALID_LINK,
    StatementQualificationGold,
)

NOT_EVALUABLE = "not_evaluable"
EVALUATION_VERSION = "linking_evaluation/1.0"

# Come lo stato del linker corrente si traduce nel vocabolario del gold.
LINKER_STATUS_TO_GOLD = {
    "exact_source_match": VALID_LINK,
    "multi_source_match": VALID_LINK,
    "ambiguous_match": AMBIGUOUS_LINK,
    "conflicting_match": CONFLICTING_LINK,
    "no_match": INVALID_LINK,
    "requires_human_review": AMBIGUOUS_LINK,
}


@dataclass(frozen=True)
class CandidatePair:
    """Una coppia proposta dal linker, non ancora giudicata."""

    statement_id: str
    profile_unit_id: str
    predicted_status: str
    match_method: str = ""
    matched_identifiers: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "statement_id": self.statement_id,
            "profile_unit_id": self.profile_unit_id,
            "predicted_status": self.predicted_status,
            "predicted_gold_status": LINKER_STATUS_TO_GOLD.get(self.predicted_status, INVALID_LINK),
            "match_method": self.match_method,
            "matched_identifiers": list(self.matched_identifiers),
            "is_gold": False,
            "note": "proposta del linker: non e' un verdetto e non va copiata nel gold",
        }


def _ratio(numerator: int, denominator: int) -> float | str:
    return round(numerator / denominator, 4) if denominator else NOT_EVALUABLE


def evaluate_linking(
    candidates: Sequence[CandidatePair],
    gold_records: Sequence[StatementQualificationGold],
) -> dict[str, Any]:
    """Confronta linker e gold sui soli record valutabili."""
    evaluable = [record for record in gold_records if record.is_evaluable]
    by_pair = {
        (record.statement_id, record.profile_unit_id): record for record in evaluable
    }
    predicted = {
        (candidate.statement_id, candidate.profile_unit_id): candidate
        for candidate in candidates
    }

    # Il denominatore e' l'insieme delle coppie **con gold**. Una coppia proposta
    # dal linker e priva di gold non e' un falso positivo: e' un caso non
    # giudicato, e contarla come errore inventerebbe una misura.
    judged = [pair for pair in predicted if pair in by_pair]

    true_positive = 0
    false_positive = 0
    exact = 0
    for pair in judged:
        gold = by_pair[pair]
        candidate = predicted[pair]
        mapped = LINKER_STATUS_TO_GOLD.get(candidate.predicted_status, INVALID_LINK)
        gold_status = gold.final_status
        if gold_status in (VALID_LINK, PARTIAL_LINK) and mapped == VALID_LINK:
            true_positive += 1
            if mapped == gold_status:
                exact += 1
        elif mapped == VALID_LINK:
            false_positive += 1
        elif mapped == gold_status:
            exact += 1

    false_negative = sum(
        1
        for pair, record in by_pair.items()
        if record.final_status in (VALID_LINK, PARTIAL_LINK) and pair not in predicted
    )

    precision = _ratio(true_positive, true_positive + false_positive)
    recall = _ratio(true_positive, true_positive + false_negative)
    f1: float | str = NOT_EVALUABLE
    if isinstance(precision, float) and isinstance(recall, float) and (precision + recall):
        f1 = round(2 * precision * recall / (precision + recall), 4)

    def _detection(status: str) -> float | str:
        relevant = [pair for pair in judged if by_pair[pair].final_status == status]
        if not relevant:
            return NOT_EVALUABLE
        hits = sum(
            1
            for pair in relevant
            if LINKER_STATUS_TO_GOLD.get(predicted[pair].predicted_status) == status
        )
        return round(hits / len(relevant), 4)

    return {
        "evaluation_version": EVALUATION_VERSION,
        "candidate_count": len(candidates),
        "gold_record_count": len(gold_records),
        "evaluated_count": len(judged),
        "not_evaluated_count": len(candidates) - len(judged),
        "provisional_count": sum(1 for record in gold_records if not record.is_evaluable),
        "frozen_count": sum(1 for record in gold_records if record.frozen_at),
        "linking_precision": precision,
        "linking_recall": recall,
        "linking_f1": f1,
        "exact_match_precision": _ratio(exact, len(judged)),
        "partial_link_accuracy": _detection(PARTIAL_LINK),
        "invalid_link_rejection_accuracy": _detection(INVALID_LINK),
        "ambiguity_detection_accuracy": _detection(AMBIGUOUS_LINK),
        "conflict_detection_accuracy": _detection(CONFLICTING_LINK),
        "dimension_level_precision": NOT_EVALUABLE,
        "dimension_level_recall": NOT_EVALUABLE,
        "note": (
            "precision e recall sono calcolate solo sulle coppie con gold valutabile. "
            "Una coppia proposta dal linker e priva di gold non e' un falso positivo: "
            "e' un caso non giudicato."
            if judged
            else "nessun record di gold valutabile: nessuna metrica di linking e' calcolabile. "
            "Il gold richiede due annotazioni indipendenti, che questa fase non ha prodotto."
        ),
    }


def dimension_metrics(
    candidates: Sequence[CandidatePair],
    gold_records: Sequence[StatementQualificationGold],
) -> dict[str, Any]:
    """Precision e recall per dimensione, quando il gold le dichiara."""
    evaluable = [record for record in gold_records if record.is_evaluable]
    if not evaluable:
        return {
            "status": NOT_EVALUABLE,
            "reason": "nessun gold valutabile dichiara le dimensioni applicabili",
        }
    per_dimension: dict[str, dict[str, int]] = {}
    for record in evaluable:
        for dimension in record.final_dimensions():
            bucket = per_dimension.setdefault(dimension, {"gold": 0})
            bucket["gold"] += 1
    return {"status": "evaluated", "gold_dimension_counts": per_dimension}
