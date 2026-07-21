"""Confronto fra insiemi e fra claim, riusato da tutte le metriche.

Riusa la normalizzazione e le regole di non-fusione gia' validate dall'audit del
grafo: alias farmacologici controllati, PMID nelle due forme, NCT in uppercase,
malattie confrontate distinguendo vocabolario da specificita'. Riscriverle qui
significherebbe avere due definizioni di "corrispondenza" che possono divergere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from ..pilot.audit_lib.aliases import build_alias_table
from ..pilot.audit_lib.classify import classify_variant_form
from ..pilot.audit_lib.disease import diseases_match
from ..pilot.audit_lib.normalize import norm_drug, norm_nct_set, norm_pmid_set, norm_text
from .contracts import MetricResult

_ALIASES = build_alias_table()


def normalize_therapies(values: Iterable[Any]) -> set[str]:
    return {name for name in (norm_drug(value, _ALIASES) for value in values or ()) if name}


def normalize_pmids(values: Iterable[Any]) -> set[str]:
    return set(norm_pmid_set(list(values or ())))


def normalize_ncts(values: Iterable[Any]) -> set[str]:
    return set(norm_nct_set(list(values or ())))


@dataclass(frozen=True)
class SetScore:
    """Precision, recall e F1 con gli insiemi che li hanno prodotti."""

    name: str
    true_positives: tuple[str, ...]
    false_positives: tuple[str, ...]
    false_negatives: tuple[str, ...]
    excluded_unreachable: tuple[str, ...] = ()

    @property
    def precision(self) -> float | None:
        denominator = len(self.true_positives) + len(self.false_positives)
        return len(self.true_positives) / denominator if denominator else None

    @property
    def recall(self) -> float | None:
        denominator = len(self.true_positives) + len(self.false_negatives)
        return len(self.true_positives) / denominator if denominator else None

    @property
    def f1(self) -> float | None:
        precision, recall = self.precision, self.recall
        if precision is None or recall is None or (precision + recall) == 0:
            return None
        return 2 * precision * recall / (precision + recall)

    def as_metrics(self) -> dict[str, MetricResult]:
        note = (
            f"esclusi perche' non presenti nello snapshot: {list(self.excluded_unreachable)}"
            if self.excluded_unreachable
            else ""
        )
        notes = (note,) if note else ()
        return {
            f"{self.name}_precision": MetricResult(
                name=f"{self.name}_precision",
                numerator=len(self.true_positives),
                denominator=len(self.true_positives) + len(self.false_positives),
                covered_items=self.true_positives,
                missing_items=self.false_positives,
                notes=notes,
            ),
            f"{self.name}_recall": MetricResult(
                name=f"{self.name}_recall",
                numerator=len(self.true_positives),
                denominator=len(self.true_positives) + len(self.false_negatives),
                covered_items=self.true_positives,
                missing_items=self.false_negatives,
                notes=notes,
            ),
            f"{self.name}_f1": MetricResult(
                name=f"{self.name}_f1",
                numerator=(self.f1 or 0.0),
                denominator=1.0 if self.f1 is not None else 0.0,
                notes=notes,
            ),
        }


def score_sets(
    name: str,
    predicted: Iterable[str],
    expected_reachable: Iterable[str],
    *,
    unreachable: Iterable[str] = (),
) -> SetScore:
    """Confronta il predetto con cio' che era **realmente recuperabile**.

    Gli elementi non presenti nello snapshot vengono esclusi dal denominatore del
    recall e non contano come falsi positivi se predetti: un modello che nomina una
    terapia assente dal grafo sta sbagliando in un altro modo, misurato altrove
    come `unsupported_claim_rate`, non come errore di retrieval.
    """
    predicted_set = set(predicted or ())
    expected_set = set(expected_reachable or ())
    excluded = set(unreachable or ())
    predicted_set -= excluded
    return SetScore(
        name=name,
        true_positives=tuple(sorted(predicted_set & expected_set)),
        false_positives=tuple(sorted(predicted_set - expected_set)),
        false_negatives=tuple(sorted(expected_set - predicted_set)),
        excluded_unreachable=tuple(sorted(excluded)),
    )


# Dimensioni su cui una claim del report deve concordare con la fonte per contare
# come corretta. Ricalca la regola dell'audit: farmaco e PMID sono solo l'ancora.
CLAIM_DIMENSIONS = ("subject", "object", "disease", "direction", "pmid")


@dataclass(frozen=True)
class ClaimMatch:
    claim_id: str
    matched: bool
    differing_dimensions: tuple[str, ...] = ()
    matched_against: str = ""


def _claim_field(claim: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = claim.get(name)
        if value:
            return str(value)
    return ""


def match_claim_against(
    claim: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]]
) -> ClaimMatch:
    """Cerca fra i candidati una claim che concordi su tutte le dimensioni presenti."""
    claim_id = str(claim.get("claim_id") or claim.get("id") or "")
    claim_drug = norm_drug(_claim_field(claim, "object", "drug", "therapy"), _ALIASES)
    claim_pmids = normalize_pmids([_claim_field(claim, "pmid", "source_id")])
    claim_disease = _claim_field(claim, "disease")
    claim_subject = _claim_field(claim, "subject", "molecular_profile", "variant")
    claim_direction = norm_text(_claim_field(claim, "direction", "evidence_direction"))
    claim_compound = classify_variant_form(claim_subject).is_compound

    best: ClaimMatch | None = None
    for candidate in candidates:
        differing: list[str] = []
        candidate_drug = norm_drug(
            _claim_field(candidate, "object", "drug", "therapy"), _ALIASES
        )
        if claim_drug and candidate_drug and claim_drug != candidate_drug:
            differing.append("object")
        candidate_pmids = normalize_pmids(
            [_claim_field(candidate, "pmid", "source_id")]
            + list(candidate.get("pmids") or [])
            + list(candidate.get("citation_id") or [])
        )
        if claim_pmids and candidate_pmids and not (claim_pmids & candidate_pmids):
            differing.append("pmid")
        candidate_disease = _claim_field(candidate, "disease")
        if claim_disease and candidate_disease and not diseases_match(
            claim_disease, candidate_disease
        ):
            differing.append("disease")
        candidate_subject = _claim_field(
            candidate, "subject", "molecular_profile", "variant"
        )
        if candidate_subject and classify_variant_form(candidate_subject).is_compound != (
            claim_compound
        ):
            differing.append("subject")
        candidate_direction = norm_text(
            _claim_field(candidate, "direction", "evidence_direction")
        )
        if claim_direction and candidate_direction:
            agrees = claim_direction[:7] == candidate_direction[:7]
            if not agrees:
                differing.append("direction")

        match = ClaimMatch(
            claim_id=claim_id,
            matched=not differing,
            differing_dimensions=tuple(differing),
            matched_against=str(candidate.get("record_id") or candidate.get("claim_id") or ""),
        )
        if match.matched:
            return match
        if best is None or len(match.differing_dimensions) < len(best.differing_dimensions):
            best = match
    return best or ClaimMatch(claim_id=claim_id, matched=False, differing_dimensions=("no_candidate",))


def score_claims(
    predicted: Sequence[Mapping[str, Any]], expected: Sequence[Mapping[str, Any]]
) -> SetScore:
    """Precision e recall sulle claim, con corrispondenza su tutte le dimensioni."""
    matched_expected: set[str] = set()
    true_positives: list[str] = []
    false_positives: list[str] = []
    for claim in predicted:
        match = match_claim_against(claim, expected)
        identifier = str(claim.get("claim_id") or claim.get("id") or claim.get("object") or "?")
        if match.matched:
            true_positives.append(identifier)
            matched_expected.add(match.matched_against or identifier)
        else:
            false_positives.append(identifier)
    false_negatives = [
        str(claim.get("claim_id") or claim.get("id") or "?")
        for claim in expected
        if str(claim.get("claim_id") or claim.get("id") or "?") not in matched_expected
        and not any(
            match_claim_against(p, [claim]).matched for p in predicted
        )
    ]
    return SetScore(
        name="claim",
        true_positives=tuple(sorted(true_positives)),
        false_positives=tuple(sorted(false_positives)),
        false_negatives=tuple(sorted(false_negatives)),
    )
