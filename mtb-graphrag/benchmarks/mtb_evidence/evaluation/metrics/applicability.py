"""Applicabilita': una fonte valida non e' automaticamente pertinente al caso.

La distinzione che regge questo modulo: **una fonte documentalmente valida ma non
applicabile non e' un falso positivo documentale**. Diventa un errore solo se il
report la presenta come applicabile.

E' il cuore del caso C1. ADAURA e AURA3 sono studi reali, correttamente citati, e
sostengono cio' che affermano; semplicemente non riguardano un paziente in prima
linea senza T790M. Un sistema che le elimina sbaglia quanto uno che le presenta come
pertinenti: la risposta corretta e' conservarle e qualificarle.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from ...pilot.audit_lib.normalize import norm_text
from ..contracts import ClinicalGoldCase, MetricResult, ReportPrediction
from ..source_profiles import SourceClinicalProfileRepository

COMPATIBLE = "compatible"
NOT_COMPATIBLE = "not_compatible"
INDETERMINATE = "indeterminate"


def _expected_applicability(case: ClinicalGoldCase) -> dict[str, str]:
    return {
        claim.claim_id: norm_text(claim.applicability) or INDETERMINATE
        for claim in case.expected_claims
    }


def _predicted_applicability(report: ReportPrediction) -> dict[str, str]:
    return {
        str(key): norm_text(value) or INDETERMINATE
        for key, value in (report.applicability_by_claim or {}).items()
    }


def documentary_status_accuracy(
    case: ClinicalGoldCase, report: ReportPrediction
) -> MetricResult:
    """Accuratezza sullo stato documentale, indipendente dall'applicabilita'."""
    expected = {
        claim.claim_id: norm_text(claim.documentary_status)
        for claim in case.expected_claims
        if claim.documentary_status
    }
    predicted = {
        str(claim.get("claim_id")): norm_text(claim.get("documentary_status"))
        for claim in report.claims
        if claim.get("documentary_status")
    }
    correct = [key for key, value in expected.items() if predicted.get(key) == value]
    return MetricResult(
        name="documentary_status_accuracy",
        numerator=len(correct),
        denominator=len(expected),
        covered_items=tuple(correct),
        missing_items=tuple(key for key in expected if key not in correct),
    )


def applicability_status_accuracy(
    case: ClinicalGoldCase, report: ReportPrediction
) -> MetricResult:
    expected = _expected_applicability(case)
    predicted = _predicted_applicability(report)
    correct = [key for key, value in expected.items() if predicted.get(key) == value]
    return MetricResult(
        name="applicability_status_accuracy",
        numerator=len(correct),
        denominator=len(expected),
        covered_items=tuple(correct),
        missing_items=tuple(key for key in expected if key not in correct),
    )


def compatible_overstatement_rate(
    case: ClinicalGoldCase, report: ReportPrediction
) -> MetricResult:
    """Claim dichiarate applicabili che il gold marca non applicabili.

    E' l'errore piu' grave della famiglia: presenta al clinico come pertinente
    un'evidenza che riguarda un'altra popolazione.
    """
    expected = _expected_applicability(case)
    predicted = _predicted_applicability(report)
    overstated = [
        key
        for key, value in expected.items()
        if value == NOT_COMPATIBLE and predicted.get(key) == COMPATIBLE
    ]
    not_compatible = [key for key, value in expected.items() if value == NOT_COMPATIBLE]
    return MetricResult(
        name="compatible_overstatement_rate",
        numerator=len(overstated),
        denominator=len(not_compatible),
        missing_items=tuple(overstated),
        notes=("denominatore: claim che il gold marca non applicabili",),
    )


def not_compatible_leakage_rate(
    case: ClinicalGoldCase, report: ReportPrediction
) -> MetricResult:
    """Claim non applicabili presentate senza alcuna qualificazione.

    Distinta dall'overstatement: qui non si afferma che sia applicabile, ma si omette
    di dire che non lo e'. Per il lettore l'effetto e' simile.
    """
    expected = _expected_applicability(case)
    predicted = _predicted_applicability(report)
    leaked = [
        key
        for key, value in expected.items()
        if value == NOT_COMPATIBLE and key not in predicted
    ]
    not_compatible = [key for key, value in expected.items() if value == NOT_COMPATIBLE]
    return MetricResult(
        name="not_compatible_leakage_rate",
        numerator=len(leaked),
        denominator=len(not_compatible),
        missing_items=tuple(leaked),
        notes=("claim non applicabili riportate senza qualificazione esplicita",),
    )


def _profile_field_accuracy(
    name: str,
    field: str,
    report: ReportPrediction,
    profiles: SourceClinicalProfileRepository,
) -> MetricResult:
    """Quanto il testo del report riflette un campo dei profili delle fonti citate."""
    text = norm_text(report.text)
    correct: list[str] = []
    missing: list[str] = []
    for pmid in report.cited_pmids:
        profile = profiles.by_pmid(pmid)
        if profile is None:
            continue
        value = getattr(profile, field, "") or ""
        if not value:
            continue
        tokens = [token for token in norm_text(value).split() if len(token) > 3]
        (correct if any(token in text for token in tokens) else missing).append(
            f"{pmid}:{field}"
        )
    return MetricResult(
        name=name,
        numerator=len(correct),
        denominator=len(correct) + len(missing),
        covered_items=tuple(correct),
        missing_items=tuple(missing),
    )


def setting_accuracy(
    report: ReportPrediction, profiles: SourceClinicalProfileRepository
) -> MetricResult:
    return _profile_field_accuracy("setting_accuracy", "setting", report, profiles)


def therapy_line_accuracy(
    report: ReportPrediction, profiles: SourceClinicalProfileRepository
) -> MetricResult:
    return _profile_field_accuracy(
        "therapy_line_accuracy", "therapy_line", report, profiles
    )


def prior_therapy_accuracy(
    report: ReportPrediction, profiles: SourceClinicalProfileRepository
) -> MetricResult:
    text = norm_text(report.text)
    correct: list[str] = []
    missing: list[str] = []
    for pmid in report.cited_pmids:
        profile = profiles.by_pmid(pmid)
        if profile is None or not profile.prior_therapies:
            continue
        tokens = [
            token
            for therapy in profile.prior_therapies
            for token in norm_text(therapy).split()
            if len(token) > 4
        ]
        (correct if any(token in text for token in tokens) else missing).append(
            f"{pmid}:prior_therapy"
        )
    return MetricResult(
        name="prior_therapy_accuracy",
        numerator=len(correct),
        denominator=len(correct) + len(missing),
        covered_items=tuple(correct),
        missing_items=tuple(missing),
    )


def missing_context_detection(
    case: ClinicalGoldCase, report: ReportPrediction
) -> MetricResult:
    """Il sistema segnala di non avere il contesto necessario, quando e' cosi'.

    Il gold marca `expected_human_review` proprio nei casi in cui l'informazione
    disponibile non basta a decidere da sola.
    """
    expected = case.expected_human_review
    detected = report.requested_human_review or report.abstained
    return MetricResult(
        name="missing_context_detection",
        numerator=1.0 if detected == expected else 0.0,
        denominator=1.0,
        notes=(f"attesa={expected}, osservata={detected}",),
    )


def applicability_metrics(
    case: ClinicalGoldCase,
    report: ReportPrediction,
    profiles: SourceClinicalProfileRepository,
) -> dict[str, MetricResult]:
    return {
        metric.name: metric
        for metric in (
            documentary_status_accuracy(case, report),
            applicability_status_accuracy(case, report),
            setting_accuracy(report, profiles),
            therapy_line_accuracy(report, profiles),
            prior_therapy_accuracy(report, profiles),
            missing_context_detection(case, report),
            compatible_overstatement_rate(case, report),
            not_compatible_leakage_rate(case, report),
        )
    }
