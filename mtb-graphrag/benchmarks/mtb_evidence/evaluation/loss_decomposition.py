"""Attribuzione della perdita lungo la catena, claim per claim.

    clinical gold -> presente nel KG -> recuperato -> riportato -> correttamente qualificato

Ogni claim clinica riceve **esattamente uno** stato finale. Gli stati sono valutati
in ordine di catena e il primo che si applica vince: se una claim non e' nel grafo,
non ha senso chiedersi se il report l'abbia persa. Questo ordinamento e' cio' che
rende gli stati mutuamente esclusivi senza casi ambigui.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from ..pilot.audit_lib.normalize import norm_text
from .contracts import (
    ABSENT,
    AMBIGUOUS,
    APPLICABILITY_ERROR,
    CITATION_ERROR,
    CORRECTLY_ABSTAINED,
    LOST_IN_REPORT,
    MISREPRESENTED_IN_REPORT,
    MISSED_BY_RETRIEVAL,
    MISSING_FROM_KG,
    PARTIALLY_MODELLED_IN_KG,
    PARTIALLY_PRESENT,
    PRESENT,
    PRESENT_AND_CORRECT,
    QUALIFIER_OMISSION,
    UNRESOLVED,
    ClinicalGoldCase,
    ClinicalGoldClaim,
    LossDecomposition,
    ReportPrediction,
    RetrievalPrediction,
    SnapshotGoldCase,
    ensure_exhaustive_loss,
)
from .matching import match_claim_against, normalize_pmids, normalize_therapies

STAGE_KG = "knowledge_graph"
STAGE_RETRIEVAL = "retrieval"
STAGE_REPORT = "report"
STAGE_QUALIFICATION = "qualification"
STAGE_NONE = "none"


def _snapshot_state(snapshot: SnapshotGoldCase, claim_id: str) -> str | None:
    for item in snapshot.items:
        if item.clinical_item_id == claim_id:
            return item.presence_status
    return None


def classify_claim(
    claim: ClinicalGoldClaim,
    case: ClinicalGoldCase,
    snapshot: SnapshotGoldCase,
    retrieval: RetrievalPrediction,
    report: ReportPrediction,
) -> LossDecomposition:
    """Determina lo stato finale di una singola claim clinica."""

    # Caso di astensione: l'esito corretto e' non affermare nulla.
    if case.expected_abstention:
        if report.abstained and not report.claims:
            return LossDecomposition(
                claim_id=claim.claim_id,
                case_id=case.case_id,
                state=CORRECTLY_ABSTAINED,
                stage=STAGE_NONE,
                explanation="il gold richiede astensione e il sistema si e' astenuto",
            )
        return LossDecomposition(
            claim_id=claim.claim_id,
            case_id=case.case_id,
            state=MISREPRESENTED_IN_REPORT,
            stage=STAGE_REPORT,
            explanation="il gold richiede astensione ma il report afferma qualcosa",
            evidence={"claims_emitted": len(report.claims)},
        )

    # Stadio 1: la claim esiste nel grafo?
    presence = _snapshot_state(snapshot, claim.claim_id)
    if presence in {ABSENT, None}:
        return LossDecomposition(
            claim_id=claim.claim_id,
            case_id=case.case_id,
            state=MISSING_FROM_KG,
            stage=STAGE_KG,
            explanation="nessun record dello snapshot corrisponde a questa claim clinica",
            evidence={"presence_status": presence or "unmapped"},
        )
    if presence == AMBIGUOUS:
        return LossDecomposition(
            claim_id=claim.claim_id,
            case_id=case.case_id,
            state=PARTIALLY_MODELLED_IN_KG,
            stage=STAGE_KG,
            explanation=(
                "il grafo contiene qualcosa di correlato ma con un conflitto che ne "
                "impedisce l'equiparazione, per esempio la specificita' della malattia"
            ),
            evidence={"presence_status": presence},
        )

    # Stadio 2: il retrieval l'ha raggiunta?
    claim_drug = normalize_therapies([claim.object])
    claim_pmid = normalize_pmids([claim.pmid])
    retrieved_drugs = normalize_therapies(retrieval.therapies)
    retrieved_pmids = normalize_pmids(retrieval.pmids)
    drug_retrieved = not claim_drug or bool(claim_drug & retrieved_drugs)
    pmid_retrieved = not claim_pmid or bool(claim_pmid & retrieved_pmids)
    if not (drug_retrieved or pmid_retrieved):
        return LossDecomposition(
            claim_id=claim.claim_id,
            case_id=case.case_id,
            state=MISSED_BY_RETRIEVAL,
            stage=STAGE_RETRIEVAL,
            explanation="la claim era recuperabile dallo snapshot ma non e' stata recuperata",
            evidence={
                "expected_drug": sorted(claim_drug),
                "expected_pmid": sorted(claim_pmid),
            },
        )

    # Stadio 3: il report l'ha conservata?
    match = match_claim_against(claim.as_dict(), list(report.claims))
    if not report.claims or match.differing_dimensions == ("no_candidate",):
        return LossDecomposition(
            claim_id=claim.claim_id,
            case_id=case.case_id,
            state=LOST_IN_REPORT,
            stage=STAGE_REPORT,
            explanation="la claim e' stata recuperata ma non compare nel report",
        )
    if not match.matched:
        differing = set(match.differing_dimensions)
        if differing == {"pmid"}:
            return LossDecomposition(
                claim_id=claim.claim_id,
                case_id=case.case_id,
                state=CITATION_ERROR,
                stage=STAGE_REPORT,
                explanation="la claim e' riportata ma la citazione non corrisponde",
                evidence={"differing": sorted(differing)},
            )
        return LossDecomposition(
            claim_id=claim.claim_id,
            case_id=case.case_id,
            state=MISREPRESENTED_IN_REPORT,
            stage=STAGE_REPORT,
            explanation="la claim e' riportata ma diverge dalla fonte",
            evidence={"differing": sorted(differing)},
        )

    # Stadio 4: e' qualificata correttamente?
    expected_applicability = norm_text(claim.applicability)
    predicted_applicability = norm_text(
        (report.applicability_by_claim or {}).get(claim.claim_id, "")
    )
    if expected_applicability and predicted_applicability != expected_applicability:
        return LossDecomposition(
            claim_id=claim.claim_id,
            case_id=case.case_id,
            state=APPLICABILITY_ERROR,
            stage=STAGE_QUALIFICATION,
            explanation="la claim e' corretta ma l'applicabilita' al caso e' sbagliata",
            evidence={
                "expected": expected_applicability,
                "predicted": predicted_applicability or "non dichiarata",
            },
        )

    if claim.mandatory_qualifiers:
        text = norm_text(report.text)
        tokens = [
            token
            for token in norm_text(claim.mandatory_qualifiers).split()
            if len(token) > 5
        ]
        if tokens and not any(token in text for token in tokens):
            return LossDecomposition(
                claim_id=claim.claim_id,
                case_id=case.case_id,
                state=QUALIFIER_OMISSION,
                stage=STAGE_QUALIFICATION,
                explanation="la claim e' corretta ma i qualificatori obbligatori sono omessi",
                evidence={"qualifiers": claim.mandatory_qualifiers[:200]},
            )

    if presence == PARTIALLY_PRESENT:
        return LossDecomposition(
            claim_id=claim.claim_id,
            case_id=case.case_id,
            state=PARTIALLY_MODELLED_IN_KG,
            stage=STAGE_KG,
            explanation=(
                "la claim e' riportata correttamente, ma il grafo la rappresenta solo "
                "in parte: il risultato non e' pienamente verificabile sullo snapshot"
            ),
        )

    if presence == PRESENT:
        return LossDecomposition(
            claim_id=claim.claim_id,
            case_id=case.case_id,
            state=PRESENT_AND_CORRECT,
            stage=STAGE_NONE,
            explanation="presente nel grafo, recuperata, riportata e qualificata correttamente",
        )

    return LossDecomposition(
        claim_id=claim.claim_id,
        case_id=case.case_id,
        state=UNRESOLVED,
        stage=STAGE_NONE,
        explanation="nessuno stato applicabile: da esaminare a mano",
        evidence={"presence_status": presence},
    )


def decompose_case(
    case: ClinicalGoldCase,
    snapshot: SnapshotGoldCase,
    retrieval: RetrievalPrediction,
    report: ReportPrediction,
) -> tuple[LossDecomposition, ...]:
    """Decomposizione di tutte le claim di un caso, verificata come partizione."""
    result = tuple(
        classify_claim(claim, case, snapshot, retrieval, report)
        for claim in case.expected_claims
    )
    ensure_exhaustive_loss([claim.claim_id for claim in case.expected_claims], result)
    return result


def summarize(decompositions: Sequence[LossDecomposition]) -> dict[str, int]:
    """Conteggio per stato. La somma deve uguagliare il numero di claim."""
    counts: dict[str, int] = {}
    for item in decompositions:
        counts[item.state] = counts.get(item.state, 0) + 1
    return dict(sorted(counts.items()))


def summarize_by_stage(decompositions: Sequence[LossDecomposition]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in decompositions:
        counts[item.stage] = counts.get(item.stage, 0) + 1
    return dict(sorted(counts.items()))


def rows(decompositions: Sequence[LossDecomposition]) -> list[Mapping[str, object]]:
    return [item.as_dict() for item in decompositions]
