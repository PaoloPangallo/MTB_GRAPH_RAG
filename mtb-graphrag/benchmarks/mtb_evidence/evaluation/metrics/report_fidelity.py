"""Fedelta' del report rispetto ai record recuperati e ai profili delle fonti.

Il riferimento qui non e' il gold ma **cio' che il retrieval ha effettivamente
consegnato**: si misura quanto di quel materiale sopravvive alla scrittura. Un fatto
mai recuperato non puo' essere perso dal report, e attribuirglielo confonderebbe due
stadi diversi della catena.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ...pilot.audit_lib.normalize import norm_text
from ..contracts import MetricResult, ReportPrediction, RetrievalPrediction
from ..matching import normalize_ncts, normalize_pmids, normalize_therapies, score_claims
from ..source_profiles import SourceClinicalProfileRepository


def claim_metrics(
    report: ReportPrediction, retrieved_claims: Sequence[Mapping[str, Any]]
) -> dict[str, MetricResult]:
    return score_claims(list(report.claims), list(retrieved_claims)).as_metrics()


def citation_accuracy(
    report: ReportPrediction, retrieval: RetrievalPrediction
) -> MetricResult:
    """Quota di citazioni del report che esistono davvero fra i record recuperati.

    Una citazione inventata non e' un errore di stile: e' un riferimento che il
    lettore non puo' verificare, ed e' il modo piu' diretto in cui un report perde
    valore probatorio.
    """
    cited = normalize_pmids(report.cited_pmids)
    available = normalize_pmids(retrieval.pmids)
    supported = cited & available
    return MetricResult(
        name="citation_accuracy",
        numerator=len(supported),
        denominator=max(len(cited), 1) if cited else 0,
        covered_items=tuple(sorted(supported)),
        missing_items=tuple(sorted(cited - available)),
        notes=("PMID citati ma non presenti fra i record recuperati",) if cited - available else (),
    )


def citation_coverage(
    report: ReportPrediction, retrieval: RetrievalPrediction
) -> MetricResult:
    """Quota di fonti recuperate che il report cita davvero."""
    cited = normalize_pmids(report.cited_pmids)
    available = normalize_pmids(retrieval.pmids)
    return MetricResult(
        name="citation_coverage",
        numerator=len(cited & available),
        denominator=len(available),
        covered_items=tuple(sorted(cited & available)),
        missing_items=tuple(sorted(available - cited)),
    )


def qualifier_preservation(
    report: ReportPrediction,
    profiles: SourceClinicalProfileRepository,
) -> MetricResult:
    """Quota di qualificatori obbligatori delle fonti citate che il report conserva.

    I qualificatori vengono dai profili clinici annotati a mano, non dal grafo: e'
    l'unico posto in cui setting, linea e popolazione esistono in forma verificabile.
    """
    text = norm_text(report.text)
    mentioned = {norm_text(item) for item in report.qualifiers_present}
    required: list[tuple[str, str]] = []
    for pmid in normalize_pmids(report.cited_pmids):
        profile = profiles.by_pmid(pmid)
        if profile is None:
            continue
        for label, value in (
            ("setting", profile.setting),
            ("therapy_line", profile.therapy_line),
            ("stage", profile.stage),
        ):
            if value:
                required.append((f"{pmid}:{label}", value))

    preserved: list[str] = []
    lost: list[str] = []
    for key, value in required:
        tokens = [token for token in norm_text(value).split() if len(token) > 3]
        found = any(token in text for token in tokens) or norm_text(value) in mentioned
        (preserved if found else lost).append(key)

    return MetricResult(
        name="qualifier_preservation",
        numerator=len(preserved),
        denominator=len(required),
        covered_items=tuple(preserved),
        missing_items=tuple(lost),
        notes=("qualificatori dai profili clinici annotati, non dal grafo",),
    )


def context_omission_rate(
    report: ReportPrediction, profiles: SourceClinicalProfileRepository
) -> MetricResult:
    """Complemento della conservazione dei qualificatori."""
    preservation = qualifier_preservation(report, profiles)
    return MetricResult(
        name="context_omission_rate",
        numerator=len(preservation.missing_items),
        denominator=preservation.denominator,
        missing_items=preservation.missing_items,
    )


def unsupported_claim_rate(
    report: ReportPrediction, retrieval: RetrievalPrediction
) -> MetricResult:
    """Quota di claim del report senza alcun aggancio ai record recuperati."""
    available_therapies = normalize_therapies(retrieval.therapies)
    available_pmids = normalize_pmids(retrieval.pmids)
    unsupported: list[str] = []
    for claim in report.claims:
        drug = normalize_therapies([claim.get("object") or claim.get("drug") or ""])
        pmids = normalize_pmids([claim.get("pmid") or ""])
        drug_ok = not drug or bool(drug & available_therapies)
        pmid_ok = not pmids or bool(pmids & available_pmids)
        if not (drug_ok and pmid_ok):
            unsupported.append(str(claim.get("claim_id") or claim.get("object") or "?"))
    return MetricResult(
        name="unsupported_claim_rate",
        numerator=len(unsupported),
        denominator=max(len(report.claims), 1) if report.claims else 0,
        missing_items=tuple(unsupported),
    )


def contradiction_rate(report: ReportPrediction) -> MetricResult:
    """Claim del report che si contraddicono sulla stessa coppia soggetto-oggetto."""
    directions: dict[tuple[str, str], set[str]] = {}
    for claim in report.claims:
        key = (
            norm_text(claim.get("subject") or ""),
            norm_text(claim.get("object") or ""),
        )
        direction = norm_text(claim.get("direction") or "")
        if key[0] and key[1] and direction:
            directions.setdefault(key, set()).add(direction[:7])
    contradictory = [key for key, values in directions.items() if len(values) > 1]
    return MetricResult(
        name="contradiction_rate",
        numerator=len(contradictory),
        denominator=max(len(directions), 1) if directions else 0,
        missing_items=tuple(f"{a}->{b}" for a, b in contradictory),
    )


def structural_coverage(
    report: ReportPrediction, retrieval: RetrievalPrediction
) -> MetricResult:
    """Quota di elementi recuperati che compaiono in qualche forma nel report."""
    available = normalize_therapies(retrieval.therapies) | normalize_pmids(retrieval.pmids)
    present = normalize_therapies(report.mentioned_therapies) | normalize_pmids(
        report.cited_pmids
    )
    return MetricResult(
        name="structural_coverage",
        numerator=len(available & present),
        denominator=len(available),
        covered_items=tuple(sorted(available & present)),
        missing_items=tuple(sorted(available - present)),
    )


def abstention_accuracy(report: ReportPrediction, expected_abstention: bool) -> MetricResult:
    correct = report.abstained == expected_abstention
    return MetricResult(
        name="abstention_accuracy",
        numerator=1.0 if correct else 0.0,
        denominator=1.0,
        notes=(
            f"attesa={expected_abstention}, osservata={report.abstained}",
        ),
    )


def human_review_routing_accuracy(
    report: ReportPrediction, expected_human_review: bool
) -> MetricResult:
    correct = report.requested_human_review == expected_human_review
    return MetricResult(
        name="human_review_routing_accuracy",
        numerator=1.0 if correct else 0.0,
        denominator=1.0,
        notes=(
            f"attesa={expected_human_review}, osservata={report.requested_human_review}",
        ),
    )


def report_metrics(
    report: ReportPrediction,
    retrieval: RetrievalPrediction,
    profiles: SourceClinicalProfileRepository,
    *,
    expected_abstention: bool = False,
    expected_human_review: bool = False,
    retrieved_claims: Sequence[Mapping[str, Any]] = (),
) -> dict[str, MetricResult]:
    metrics = dict(claim_metrics(report, retrieved_claims or list(retrieval.claims)))
    for metric in (
        citation_accuracy(report, retrieval),
        citation_coverage(report, retrieval),
        qualifier_preservation(report, profiles),
        context_omission_rate(report, profiles),
        unsupported_claim_rate(report, retrieval),
        contradiction_rate(report),
        structural_coverage(report, retrieval),
        abstention_accuracy(report, expected_abstention),
        human_review_routing_accuracy(report, expected_human_review),
    ):
        metrics[metric.name] = metric
    return metrics
