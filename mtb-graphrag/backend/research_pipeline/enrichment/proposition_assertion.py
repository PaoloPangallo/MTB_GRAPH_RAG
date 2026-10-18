"""Deterministic scope contract for candidate-anchored document propositions.

This is deliberately a conservative grammar, not a general English parser.
Its positive class is narrow: a candidate-anchored relation predicate must be
in the source's own main assertion. Reported or embedded propositions can be
useful bibliography, but do not establish document FULL_SUPPORT.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AssertionAssessment:
    state: str
    reason: str
    focused_text: str

    @property
    def epistemic_scope(self) -> str:
        """Expose the semantic scope independently of legacy verifier states."""
        if self.state in {"DIRECT_ASSERTION", "DIRECT_NEGATIVE_ASSERTION"}:
            return "DIRECT_ASSERTION"
        if self.state == "REPORTED_ASSERTION":
            return "ATTRIBUTED_ASSERTION"
        if self.state == "HYPOTHETICAL_ASSERTION":
            return "HYPOTHETICAL_ASSERTION"
        if self.state == "REJECTED_ASSERTION":
            return "REJECTED_ASSERTION"
        if self.state == "RETRACTED_ASSERTION":
            return "RETRACTED_ASSERTION"
        if self.state == "ENTITY_CO_OCCURRENCE":
            return "COOCCURRENCE"
        if self.reason == "PROPOSITION_NOT_ESTABLISHED" and re.search(
            r"\b(?:retracted|withdrawn|rescinded)\b", self.focused_text,
            re.IGNORECASE,
        ):
            return "RETRACTED_ASSERTION"
        return "UNCERTAIN_ASSERTION"


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _labels(candidate: dict[str, Any], key: str) -> tuple[str, ...]:
    return tuple(_norm(item.get("label")) for item in candidate.get(key) or []
                 if isinstance(item, dict) and _norm(item.get("label")))


def _candidate_anchored(text: str, candidate: dict[str, Any]) -> bool:
    biomarkers = _labels(candidate, "biomarkers")
    interventions = _labels(candidate, "interventions")
    required_groups = [biomarkers, interventions]
    return all(not group or all(re.search(rf"\b{re.escape(label)}\b", text)
                                for label in group) for group in required_groups)


def comparative_cohort_outcome(text: str, intervention: str, subjects: tuple[str, ...], disease: str = "") -> bool:
    """Narrow, literal regimen-led outcome grammar; not a general NLP verdict.

    The named intervention must be the matrix subject, not a comparator.
    Molecular anchors must be in the explicitly described patient cohort.
    Epistemic operators are assessed independently on the complete quote.
    """
    # Sentence boundaries must survive normalization. A later sentence cannot
    # supply a missing molecular anchor for the outcome cohort.
    first_sentence = re.split(r"[.!?;]", text, maxsplit=1)[0]
    main, drug = _norm(first_sentence), _norm(intervention)
    molecular_phrase = " ".join(_norm(subject) for subject in subjects if _norm(subject))
    disease_phrase = _norm(disease)
    if not drug or not molecular_phrase or not disease_phrase:
        return False
    match = re.match(rf"^(?:a |the )?(?:combination of )?{re.escape(drug)} "
                     r"resulted in (?:significantly )?longer (?:overall |progression free )?survival\b", main)
    if not match:
        return False
    cohort = re.fullmatch(
        r"(?: and a higher response rate)?"
        r"(?: than (?:the )?(?:control(?: group)?|standard therapy))?"
        r" in (?:patients|participants) with (.+)", main[match.end():],
    )
    if not cohort:
        return False
    population = cohort[1].strip()
    # Only affirmative, single-cohort descriptions are licensed. Unknown
    # syntax abstains, rather than borrowing anchors from another population.
    return bool(re.fullmatch(
        rf"{re.escape(disease_phrase)} with (?:the )?"
        rf"{re.escape(molecular_phrase)}(?: mutation)?", population,
    ))


def _direct_assertion_licensed(main: str, candidate: dict[str, Any], source_text: str = "") -> bool:
    """Positive license: first-party result or candidate-led observation.

    An arbitrary matrix subject (author, prior experiment, cited report) is
    not silently promoted merely because its complement contains a predicate.
    Unrecognized prose abstains; this deliberately favors FULL precision.
    """
    main = re.sub(r"^in our (?:cohort|study|analysis),?\s+", "", main)
    if re.match(r"^(?:we\s+|our (?:results|data|experiments|findings)\s+|this (?:study|analysis)\s+)", main):
        return True
    if re.match(r"^but\s+", main):
        return True  # only after relation_support has licensed subject ellipsis
    if comparative_cohort_outcome(source_text, str(candidate.get("_grounded_intervention") or ""),
                                 _labels(candidate, "biomarkers"),
                                 str(candidate.get("_grounded_disease") or "")):
        return True
    subjects = (*_labels(candidate, "biomarkers"), *_labels(candidate, "interventions"))
    if not subjects:
        return False
    first = subjects[0]
    return bool(re.match(
        rf"^(?:the\s+)?{re.escape(first)}\b"
        rf"|^(?:patients|tumors|cells|samples)\s+(?:with|harboring|carrying)\s+{re.escape(first)}\b"
        rf"|^in\s+(?:patients|tumors|cells|samples)\s+(?:with|harboring|carrying)\s+{re.escape(first)}\b",
        main,
    ))


def focus_main_clause(source_text: str) -> str:
    """Use the final matrix clause when an explicit discourse pivot is present."""
    text = str(source_text or "").strip()
    if re.match(r"^(?:although|though|whereas)\b", text, re.IGNORECASE):
        before, marker, after = text.partition(",")
        if marker and after.strip():
            text = after.strip()
    # A later contrast or independent sentence can withdraw or supersede an
    # earlier embedded proposition. Never merge predicates across the pivot.
    pivot = list(re.finditer(
        r"(?:,\s*but\s+|\.\s*(?:however,?\s+|this\s+|our\s+(?:results|data|experiments|findings)\s+|we\s+))",
        text, re.IGNORECASE,
    ))
    if pivot:
        text = text[pivot[-1].start():].lstrip(" ,.")
    text = re.sub(r"^however,?\s+", "", text, flags=re.IGNORECASE)
    return text


def assess_proposition_assertion(
    source_text: str | None, candidate: dict[str, Any], relation_state: str,
) -> AssertionAssessment:
    """Classify the quote's matrix assertion, never the Reader's label.

    Rejection of a claim is not automatically a biological opposite effect:
    it blocks positive support, while direct negative findings are contradictory.
    A negated rejection or lack of contradiction likewise does not prove the
    positive claim.
    """
    if not source_text:
        return AssertionAssessment("NO_RELATION", "NO_AUTHORIZED_QUOTE", "")
    focused_text = focus_main_clause(source_text)
    full = _norm(source_text)
    main = _norm(focused_text)
    if not _candidate_anchored(full, candidate):
        return AssertionAssessment("NO_RELATION", "CANDIDATE_ENTITIES_NOT_IN_QUOTE", focused_text)

    # Scope operators are evaluated on the main clause, not as a bag of words
    # across an introductory concessive clause. Double negation remains
    # non-confirmative: not rejecting a proposition is not asserting it.
    if re.search(r"\b(?:not|never) (?:rejected|disproved|refuted)\b", main) or re.search(
        r"\bno evidence contradicted\b", main,
    ):
        return AssertionAssessment("UNCERTAIN_ASSERTION", "NEGATED_REJECTION_IS_NOT_CONFIRMATION", focused_text)
    if re.search(r"\bno evidence (?:that|of|for)\b", main):
        return AssertionAssessment("UNCERTAIN_ASSERTION", "ABSENCE_OF_EVIDENCE_NOT_OPPOSITE_EFFECT", focused_text)

    # A trailing scope operator governs the preceding positive proposition.
    # The relation predicate alone cannot override a later withdrawal, an
    # imaginary framing, or a reportative qualifier in the same source unit.
    if re.search(r"\b(?:retracted|withdrawn|rescinded|invalidated|discredited|debunked|overturned|repudiated)\b", main):
        return AssertionAssessment("RETRACTED_ASSERTION", "PROPOSITION_WITHDRAWN_OR_INVALIDATED", focused_text)
    if re.search(
        r"\b(?:fictional|imaginary|simulated|counterfactual) (?:scenario|case|setting|model)\b"
        r"|\bin (?:an? |the )?imagined world\b"
        r"|\bin (?:a|the) dream\b"
        r"|\bor so (?:we|they) (?:imagined|supposed|speculated)\b", main,
    ):
        return AssertionAssessment("HYPOTHETICAL_ASSERTION", "PROPOSITION_IN_HYPOTHETICAL_SCOPE", focused_text)
    if re.search(
        r"\bso (?:the|this) (?:story|account|rumor) goes\b"
        r"|\bor so (?:the )?(?:critics|authors|reporters|observers|manuscript|article|report) (?:alleged|claimed|said)\b",
        # A manuscript's claim is attribution, not a direct biological finding.
        main,
    ):
        return AssertionAssessment("REPORTED_ASSERTION", "PROPOSITION_ONLY_REPORTED", focused_text)

    proposition_noun = bool(re.search(
        r"\b(?:proposition|hypothesis|claim|association|finding|findings|this|it)\b", main,
    ))
    rejection_verb = bool(re.search(
        r"\b(?:was|were|is|are|has been|have been)? ?"
        r"(?:rejected|dismissed|disproved|refuted|not supported|not confirmed)\b"
        r"|\b(?:did|does|do) not confirm\b"
        r"|\bfailed to (?:confirm|reproduce|replicate|validate)\b", main,
    ))
    if rejection_verb and (proposition_noun or re.search(r"\b(?:subsequent|our) (?:experiments|results)\b", main)):
        return AssertionAssessment("REJECTED_ASSERTION", "MATRIX_PREDICATE_REJECTS_PROPOSITION", focused_text)

    if "?" in focused_text or re.search(r"\b(?:whether|unknown|unclear)\b", main):
        return AssertionAssessment("QUESTIONED_ASSERTION", "PROPOSITION_QUESTIONED_OR_UNRESOLVED", focused_text)

    if re.search(
        r"\b(?:if|hypothesized|hypothesis|hypothetical|might|may|could|potentially|possibly|"
        r"speculated|speculation|speculative|conjectured|conjecture|presumed|theorized)\b",
        main,
    ):
        return AssertionAssessment("HYPOTHETICAL_ASSERTION", "MODAL_OR_CONDITIONAL_PROPOSITION", focused_text)

    if re.search(
        r"\b(?:inconclusive|unconfirmed|retracted|withdrawn|disputed|allegedly|purportedly)\b"
        r"|\bnot replicated\b|\b(?:thought|imaginary) experiment\b",
        main,
    ):
        return AssertionAssessment("UNCERTAIN_ASSERTION", "PROPOSITION_NOT_ESTABLISHED", focused_text)

    attribution = bool(re.search(
        r"\b(?:previous (?:studies|authors)|prior (?:studies|authors)|the authors)\s+"
        r"(?:suggested|proposed|claimed|reported)\b"
        r"|\b[a-z]+ et al\s+(?:reported|suggested|proposed|claimed|found)\b"
        r"|\ba (?:previous|prior) report (?:found|suggested|proposed|claimed|reported)\b"
        r"|\bit has been claimed\b|\breported claim\b", main,
    )) or bool(re.search(
        r"\baccording to\b|\b(?:was|were|has been|have been) reported to\b"
        r"|\b(?:is|was|are|were) said to\b"
        r"|\b(?:an? |one )(?:earlier |prior |previous )?(?:study|trial|report)\s+"
        r"(?:reported|suggested|proposed|claimed|found)\b"
        r"|\b(?:earlier|prior|previous)\s+(?:studies|trials|reports|authors)\s*"
        r"(?:indicate|indicated|suggest|suggested|report|reported|found|showed|demonstrated|:)?\b"
        r"|\bas reported (?:previously|by)\b"
        r"|\bprevious studies\s*:"
        r"|\b(?:we|our (?:results|data|study))\s+(?:found|showed|reported)\s+that\s+"
        r"(?:an?\s+)?(?:earlier|prior|previous)\s+(?:study|trial|report)\s+"
        r"(?:showed|found|reported|suggested|claimed|proposed)\b",
        focused_text, re.IGNORECASE,
    ))
    attribution = attribution or bool(re.search(
        r"[\"“].+[\"”]\s*(?:the|a)?\s*(?:review|article|authors?)\s+"
        r"(?:quoted|wrote|said|noted)\b",
        focused_text, re.IGNORECASE,
    ))
    if attribution:
        return AssertionAssessment("REPORTED_ASSERTION", "SOURCE_ATTRIBUTES_PROPOSITION_TO_OTHERS", focused_text)

    # A clinical predicate inside a ``that`` complement is not, by itself,
    # the source's assertion. Only an explicit first-party finding operator
    # licenses it; unknown matrix operators abstain rather than inherit the
    # embedded predicate's positive wording.
    if re.search(r"\bthat\b", main):
        matrix = re.split(r"\bthat\b", main, maxsplit=1)[0]
        if rejection_verb:
            return AssertionAssessment("REJECTED_ASSERTION", "MATRIX_REJECTS_EMBEDDED_PROPOSITION", focused_text)
        first_party_finding = re.search(
            r"\b(?:we|our (?:results|data|experiments|findings)|this (?:study|analysis))\s+"
            r"(?:found|find|show|showed|shows|demonstrate|demonstrated|demonstrates|confirm|confirmed|confirms)\b",
            matrix,
        )
        if not first_party_finding:
            return AssertionAssessment("UNCERTAIN_ASSERTION", "MATRIX_ASSERTION_NOT_ESTABLISHED", focused_text)

    if relation_state == "RELATION_NEGATED":
        return AssertionAssessment("DIRECT_NEGATIVE_ASSERTION", "DIRECT_NEGATIVE_RELATION_PREDICATE", focused_text)
    if relation_state == "RELATION_ASSERTED":
        if _direct_assertion_licensed(main, candidate, focused_text):
            return AssertionAssessment("DIRECT_ASSERTION", "DIRECT_CANDIDATE_ANCHORED_PREDICATE", focused_text)
        return AssertionAssessment("UNCERTAIN_ASSERTION", "DIRECT_MATRIX_ASSERTION_NOT_LICENSED", focused_text)
    if relation_state == "ENTITY_CO_OCCURRENCE":
        return AssertionAssessment("ENTITY_CO_OCCURRENCE", "NO_DIRECT_RELATION_PREDICATE", focused_text)
    return AssertionAssessment("UNCERTAIN_ASSERTION", "RELATION_SCOPE_NOT_DEMONSTRATED", focused_text)
