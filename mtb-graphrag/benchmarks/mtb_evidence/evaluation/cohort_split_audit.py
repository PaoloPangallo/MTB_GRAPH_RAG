"""Audit strutturale delle fonti: quante unita' propagabili contiene davvero.

Il rilevatore in produzione decide `requires_cohort_split` confrontando
interventi e malattie **fra gli statement** di una fonte. La revisione di
PMID 22277784 ne ha mostrato il limite in modo netto: quella fonte contiene una
coorte clinica di 18 pazienti e tre pannelli su cellule Ba/F3, e il rilevatore
l'aveva classificata `insufficient_source_information` — cioe' non l'aveva
segnalata affatto, pur avendo dieci statement a disposizione.

Il limite non e' quindi soltanto il caso «un solo statement». E' che il segnale
vive nella **fonte**, non nella distribuzione degli statement, e l'abstract
spesso non lo espone. Questo modulo aggiunge un rilevatore che legge i segnali
dove stanno, e riporta i segnali insieme al verdetto: un verdetto senza le sue
prove non e' auditabile.

Nessun modello linguistico decide qui. Le regole sono lessicali, deterministiche
e ancorate a span, e il loro compito e' **segnalare**, non concludere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

AUDIT_VERSION = "cohort_split_audit/1.0"
DETECTOR_VERSION = "source_level_split_detector/2.0"

# --- stati strutturali principali (uno solo per fonte) ------------------------
SINGLE_PROPAGATABLE = "single_propagatable_unit"
CLINICAL_PRECLINICAL_SPLIT = "clinical_preclinical_split_required"
MULTI_ARM_CLINICAL_SPLIT = "multi_arm_clinical_split_required"
MULTI_COHORT_CLINICAL_SPLIT = "multi_cohort_clinical_split_required"
MULTI_PRECLINICAL_SPLIT = "multi_preclinical_model_split_required"
CLINICAL_SUBGROUP_SPLIT = "clinical_subgroup_split_required"
ANALYSIS_LEVEL_SPLIT = "analysis_level_split_required"
PARTIALLY_SEPARABLE = "partially_separable"
COHORT_NOT_SEPARABLE = "cohort_not_separable"
INSUFFICIENT_SOURCE_INFORMATION = "insufficient_source_information"
SOURCE_UNAVAILABLE = "source_unavailable"
REQUIRES_CLINICAL_REVIEW = "requires_clinical_review"

STRUCTURE_STATES = (
    SINGLE_PROPAGATABLE,
    CLINICAL_PRECLINICAL_SPLIT,
    MULTI_ARM_CLINICAL_SPLIT,
    MULTI_COHORT_CLINICAL_SPLIT,
    MULTI_PRECLINICAL_SPLIT,
    CLINICAL_SUBGROUP_SPLIT,
    ANALYSIS_LEVEL_SPLIT,
    PARTIALLY_SEPARABLE,
    COHORT_NOT_SEPARABLE,
    INSUFFICIENT_SOURCE_INFORMATION,
    SOURCE_UNAVAILABLE,
    REQUIRES_CLINICAL_REVIEW,
)

# --- flag indipendenti --------------------------------------------------------
STRUCTURE_FLAGS = (
    "contains_clinical_evidence",
    "contains_preclinical_evidence",
    "contains_in_vitro_evidence",
    "contains_in_vivo_evidence",
    "contains_multiple_interventions",
    "contains_multiple_comparators",
    "contains_multiple_diseases",
    "contains_multiple_biomarker_groups",
    "contains_multiple_therapy_lines",
    "contains_multiple_study_populations",
    "contains_secondary_analysis",
    "contains_case_level_evidence",
    "contains_cohort_level_evidence",
)

# --- verdetto del rilevatore --------------------------------------------------
SPLIT_NOT_INDICATED = "split_not_indicated"
SPLIT_POSSIBLE = "split_possible"
SPLIT_LIKELY = "split_likely"
SPLIT_REQUIRED = "split_required"
SPLIT_INSUFFICIENT_INFORMATION = "insufficient_information"

SPLIT_LIKELIHOODS = (
    SPLIT_NOT_INDICATED,
    SPLIT_POSSIBLE,
    SPLIT_LIKELY,
    SPLIT_REQUIRED,
    SPLIT_INSUFFICIENT_INFORMATION,
)

# --- tipi di supporto ---------------------------------------------------------
DIRECT_CLINICAL_SUPPORT = "direct_clinical_support"
DIRECT_PRECLINICAL_SUPPORT = "direct_preclinical_support"
CLINICAL_WITH_PRECLINICAL_VALIDATION = "clinical_observation_with_preclinical_validation"
INDIRECT_SUPPORT = "indirect_support"
CONTEXT_ONLY = "context_only"
NOT_DETERMINABLE = "not_determinable"
UNSUPPORTED_BY_ACCESSIBLE_SOURCE = "unsupported_by_accessible_source"

SUPPORT_TYPES = (
    DIRECT_CLINICAL_SUPPORT,
    DIRECT_PRECLINICAL_SUPPORT,
    CLINICAL_WITH_PRECLINICAL_VALIDATION,
    INDIRECT_SUPPORT,
    CONTEXT_ONLY,
    NOT_DETERMINABLE,
    UNSUPPORTED_BY_ACCESSIBLE_SOURCE,
)

CANDIDATE_STATES = (
    "candidate_valid",
    "candidate_partial",
    "candidate_ambiguous",
    "candidate_conflicting",
    "candidate_invalid",
    "candidate_not_determinable",
)

# Stato che una proposta di audit puo' avere. Deliberatamente separato dagli
# stati di revisione: una proposta strutturale non e' una revisione, e nessun
# percorso automatico deve poterla promuovere.
SPLIT_PROPOSED_BY_AUDIT = "split_proposed_by_structural_audit"


@dataclass(frozen=True)
class Signal:
    """Un segnale trovato nella fonte, con la prova che lo sostiene."""

    signal_id: str
    category: str
    matched_text: str
    section_label: str
    start: int
    end: int
    weight: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "category": self.category,
            "matched_text": self.matched_text,
            "section_label": self.section_label,
            "char_start": self.start,
            "char_end": self.end,
            "weight": self.weight,
            "locator": f"{self.section_label}@{self.start}-{self.end}",
        }


# (id, categoria, pattern, peso)
#
# I pesi non sono una probabilita'. Sono un ordinamento fra segnali di forza
# diversa: «randomly assigned to» dice quasi certamente che esistono due bracci,
# «patients» da solo dice soltanto che si parla di persone.
SOURCE_SIGNALS: tuple[tuple[str, str, str, int], ...] = (
    # struttura a coorti e bracci
    ("cohort.named", "cohort_structure", r"\bcohorts?\s+[A-D0-9]\b", 3),
    ("cohort.counted", "cohort_structure", r"\b(?:two|three|four|five|2|3|4|5)\s+cohorts\b", 3),
    ("cohort.expansion", "cohort_structure", r"\bexpansion cohorts?\b", 3),
    ("arm.named", "arm_structure", r"\barms?\s+[A-D0-9]\b", 3),
    ("arm.counted", "arm_structure", r"\b(?:two|three|four|2|3|4)\s+(?:treatment\s+)?arms\b", 3),
    ("arm.randomised", "arm_structure", r"\brandomly (?:assigned|allocated)\b", 3),
    ("arm.ratio", "arm_structure", r"\brandomi[sz]ed\s*(?:\(?\s*)?(?:1:1|2:1|1:1:1)\b", 3),
    ("arm.crossover", "arm_structure", r"\bcross-?over\b", 2),
    ("group.plural", "cohort_structure", r"\b(?:treatment|control|study) groups\b", 2),
    # popolazione clinica
    ("clinical.patients", "clinical", r"\bpatients?\b", 1),
    ("clinical.enrolled", "clinical", r"\benroll(?:ed|ment)\b", 2),
    ("clinical.phase", "clinical", r"\bphase\s*(?:1|2|3|4|I{1,3}V?|IV)\b", 2),
    ("clinical.retrospective", "clinical", r"\bretrospective(?:ly)?\b", 2),
    ("clinical.biopsy", "clinical", r"\b(?:repeat|resistant|paired|serial)\s+biops(?:y|ies)\b", 2),
    ("clinical.case_report", "case_level", r"\bcase report\b|\bwe (?:report|describe) (?:a|the case of a) patient\b", 3),
    # modelli preclinici
    ("preclinical.in_vitro", "in_vitro", r"\bin vitro\b", 3),
    ("preclinical.cell_lines", "in_vitro", r"\bcell lines?\b", 3),
    ("preclinical.baf3", "in_vitro", r"\bBa/?F3\b", 3),
    ("preclinical.transfected", "in_vitro", r"\btransfect(?:ed|ion)\b", 2),
    ("preclinical.viability", "in_vitro", r"\b(?:cell (?:viability|survival)|IC50|GI50)\b", 2),
    ("preclinical.xenograft", "in_vivo", r"\bxenograft|patient-?derived xenograft|\bPDX\b", 3),
    ("preclinical.mouse", "in_vivo", r"\b(?:mouse|murine|mice) (?:model|xenograft)s?\b", 3),
    ("preclinical.in_vivo", "in_vivo", r"\bin vivo\b", 2),
    # sottogruppi e analisi
    ("subgroup.explicit", "subgroup", r"\bsubgroup(?:s| analysis| analyses)\b", 3),
    ("analysis.secondary", "secondary_analysis", r"\b(?:secondary|exploratory|post-?hoc) analys(?:i|e)s\b", 3),
    ("analysis.preplanned", "secondary_analysis", r"\bpre-?specified analys(?:i|e)s\b", 2),
    ("analysis.interim", "secondary_analysis", r"\binterim analysis\b", 2),
    # confronto
    ("comparator.versus", "comparator", r"\bversus\b|\bcompared with\b", 2),
    ("comparator.placebo", "comparator", r"\bplacebo\b", 2),
    ("comparator.control", "comparator", r"\bcontrol (?:arm|group)\b", 2),
    # popolazioni multiple
    ("population.multiple", "population", r"\b(?:two|three|separate|distinct)\s+(?:populations|cohorts|series)\b", 3),
    ("population.pooled", "population", r"\bpooled (?:analysis|data)\b", 2),
)

# Categorie che, se compresenti, indicano che la fonte descrive cose di natura
# diversa e non fondibili.
CLINICAL_CATEGORIES = frozenset({"clinical", "case_level"})
PRECLINICAL_CATEGORIES = frozenset({"in_vitro", "in_vivo"})
MULTIPLICITY_CATEGORIES = frozenset(
    {"cohort_structure", "arm_structure", "subgroup", "secondary_analysis", "population"}
)


def _sections(record: Mapping[str, Any] | None) -> list[tuple[str, str]]:
    if not record:
        return []
    sections = record.get("abstract_sections") or []
    if sections:
        return [
            (str(item.get("label") or "UNLABELLED"), str(item.get("text") or ""))
            for item in sections
        ]
    text = str(record.get("abstract_text") or record.get("document_text") or "")
    return [("UNLABELLED", text)] if text else []


def detect_signals(record: Mapping[str, Any] | None) -> list[Signal]:
    """Tutti i segnali source-level, ciascuno con il suo span."""
    found: list[Signal] = []
    for label, text in _sections(record):
        for signal_id, category, pattern, weight in SOURCE_SIGNALS:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                found.append(
                    Signal(
                        signal_id=signal_id,
                        category=category,
                        matched_text=match.group(0),
                        section_label=label,
                        start=match.start(),
                        end=match.end(),
                        weight=weight,
                    )
                )
    return found


@dataclass
class SplitAssessment:
    """Verdetto del rilevatore, con i segnali che lo giustificano."""

    likelihood: str
    signals: tuple[Signal, ...] = ()
    categories: tuple[str, ...] = ()
    score: int = 0
    rationale: str = ""
    has_clinical: bool = False
    has_preclinical: bool = False
    has_multiplicity: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "split_likelihood": self.likelihood,
            "score": self.score,
            "categories": list(self.categories),
            "signal_count": len(self.signals),
            "signals": [item.as_dict() for item in self.signals],
            "has_clinical_evidence": self.has_clinical,
            "has_preclinical_evidence": self.has_preclinical,
            "has_multiplicity_signal": self.has_multiplicity,
            "rationale": self.rationale,
            "detector_version": DETECTOR_VERSION,
        }


def assess_split(record: Mapping[str, Any] | None) -> SplitAssessment:
    """Valuta la probabilita' di split dai soli segnali della fonte.

    Il verdetto non dipende dal numero di statement, ed e' il punto: il
    rilevatore in produzione non poteva vedere nulla su una fonte a statement
    singolo, e non ha visto nulla nemmeno su PMID 22277784, che di statement ne
    ha dieci.
    """
    if not record or not (record.get("abstract_available") or record.get("document_text")):
        return SplitAssessment(
            likelihood=SPLIT_INSUFFICIENT_INFORMATION,
            rationale="nessun testo della fonte disponibile",
        )

    signals = detect_signals(record)
    if not signals:
        return SplitAssessment(
            likelihood=SPLIT_INSUFFICIENT_INFORMATION,
            rationale=(
                "nessun segnale strutturale nel testo disponibile. L'assenza di segnali "
                "non dimostra che la fonte descriva una sola unita': su PMID 22277784 "
                "l'abstract non ne conteneva e il full text mostrava quattro unita'"
            ),
        )

    categories = {signal.category for signal in signals}
    has_clinical = bool(categories & CLINICAL_CATEGORIES)
    has_preclinical = bool(categories & PRECLINICAL_CATEGORIES)
    has_multiplicity = bool(categories & MULTIPLICITY_CATEGORIES)
    score = sum(signal.weight for signal in signals)

    # La compresenza di evidenza clinica e preclinica e' il segnale piu' forte
    # disponibile: sono cose di natura diversa, e un profilo unico permetterebbe
    # a una popolazione di pazienti di qualificare un assay su cellule.
    if has_clinical and has_preclinical:
        likelihood = SPLIT_REQUIRED
        rationale = (
            "la fonte contiene sia evidenza clinica sia evidenza preclinica: sono "
            "unita' di natura diversa e un profilo unico le fonderebbe"
        )
    elif has_multiplicity and (has_clinical or has_preclinical):
        likelihood = SPLIT_LIKELY
        rationale = (
            "segnali espliciti di piu' bracci, coorti, sottogruppi o analisi in una "
            "fonte con evidenza identificabile"
        )
    elif has_multiplicity:
        likelihood = SPLIT_POSSIBLE
        rationale = "segnali di molteplicita' senza un contesto di evidenza chiaro"
    else:
        likelihood = SPLIT_NOT_INDICATED
        rationale = (
            "nessun segnale di molteplicita' nel testo disponibile; verdetto limitato "
            "a cio' che il testo consultato espone"
        )

    return SplitAssessment(
        likelihood=likelihood,
        signals=tuple(signals),
        categories=tuple(sorted(categories)),
        score=score,
        rationale=rationale,
        has_clinical=has_clinical,
        has_preclinical=has_preclinical,
        has_multiplicity=has_multiplicity,
    )


def structure_flags(assessment: SplitAssessment, unit: Mapping[str, Any]) -> dict[str, bool]:
    """Flag indipendenti, calcolati da segnali e statement."""
    categories = set(assessment.categories)
    signal_ids = {signal.signal_id for signal in assessment.signals}
    interventions = list(unit.get("interventions") or ())
    diseases = list(unit.get("diseases") or ())
    biomarkers = list(unit.get("biomarkers") or ())

    return {
        "contains_clinical_evidence": bool(categories & CLINICAL_CATEGORIES),
        "contains_preclinical_evidence": bool(categories & PRECLINICAL_CATEGORIES),
        "contains_in_vitro_evidence": "in_vitro" in categories,
        "contains_in_vivo_evidence": "in_vivo" in categories,
        "contains_multiple_interventions": len(interventions) > 1,
        "contains_multiple_comparators": "comparator" in categories,
        "contains_multiple_diseases": len(diseases) > 1,
        "contains_multiple_biomarker_groups": len(biomarkers) > 1,
        "contains_multiple_therapy_lines": False,
        "contains_multiple_study_populations": "population" in categories
        or "cohort_structure" in categories,
        "contains_secondary_analysis": "secondary_analysis" in categories,
        "contains_case_level_evidence": "case_level" in categories,
        "contains_cohort_level_evidence": bool(categories & {"cohort_structure", "clinical"}),
    }


def classify_structure(
    assessment: SplitAssessment,
    unit: Mapping[str, Any],
    flags: Mapping[str, bool],
    *,
    full_text_consulted: bool = False,
) -> tuple[str, str]:
    """Stato strutturale principale, uno solo, con la sua motivazione.

    L'ordine dei rami non e' arbitrario: si va dal segnale piu' specifico al
    piu' generico, cosi' che una fonte clinica e preclinica insieme non finisca
    classificata come «piu' bracci» soltanto perche' contiene anche quella parola.
    """
    if assessment.likelihood == SPLIT_INSUFFICIENT_INFORMATION and not assessment.signals:
        if not (unit.get("abstract_available") or unit.get("full_text_available")):
            return SOURCE_UNAVAILABLE, "nessun testo della fonte accessibile"
        return (
            INSUFFICIENT_SOURCE_INFORMATION,
            "testo accessibile ma privo di segnali strutturali; l'assenza non prova "
            "che la fonte descriva una sola unita'",
        )

    if flags["contains_clinical_evidence"] and flags["contains_preclinical_evidence"]:
        return (
            CLINICAL_PRECLINICAL_SPLIT,
            "la fonte contiene sia una componente clinica sia una preclinica",
        )

    categories = set(assessment.categories)
    if "arm_structure" in categories and flags["contains_clinical_evidence"]:
        return MULTI_ARM_CLINICAL_SPLIT, "segnali espliciti di piu' bracci clinici"
    if "cohort_structure" in categories and flags["contains_clinical_evidence"]:
        return MULTI_COHORT_CLINICAL_SPLIT, "segnali espliciti di piu' coorti cliniche"
    if flags["contains_preclinical_evidence"] and (
        flags["contains_in_vitro_evidence"] and flags["contains_in_vivo_evidence"]
    ):
        return (
            MULTI_PRECLINICAL_SPLIT,
            "la fonte descrive sia modelli in vitro sia modelli in vivo",
        )
    if "subgroup" in categories:
        return CLINICAL_SUBGROUP_SPLIT, "analisi per sottogruppo dichiarata"
    if "secondary_analysis" in categories:
        return ANALYSIS_LEVEL_SPLIT, "analisi secondaria o esplorativa dichiarata"

    if assessment.likelihood in (SPLIT_LIKELY, SPLIT_POSSIBLE):
        return (
            PARTIALLY_SEPARABLE,
            "segnali di molteplicita' presenti ma non sufficienti a delimitare le unita'",
        )

    # Concludere «unita' singola» dal solo abstract e' l'errore che questa fase
    # esiste per non ripetere. L'abstract di PMID 22277784 non conteneva alcun
    # segnale strutturale, e il full text descriveva una coorte clinica e tre
    # pannelli su cellule. Un'assenza di segnali in un testo parziale e' assenza
    # di informazione, non informazione di assenza.
    if not full_text_consulted:
        return (
            INSUFFICIENT_SOURCE_INFORMATION,
            "nessun segnale di molteplicita' nel solo abstract. Non basta a concludere "
            "che la fonte descriva una unita' sola: sul caso gia' revisionato l'abstract "
            "taceva e il full text mostrava quattro unita'",
        )
    return (
        SINGLE_PROPAGATABLE,
        "full text consultato e nessun segnale di molteplicita'",
    )


# --- screening leggero sulle fonti a statement singolo ------------------------

SCREEN_PRIORITY_HIGH = "high"
SCREEN_PRIORITY_MEDIUM = "medium"
SCREEN_PRIORITY_LOW = "low"


def screen_source(unit: Mapping[str, Any], record: Mapping[str, Any] | None) -> dict[str, Any]:
    """Screening leggero: segnala un candidato, non lo cura.

    Serve a **quantificare** il rischio residuo, non a risolverlo. Nessuna
    unita' viene modificata e nessun profilo viene generato.
    """
    assessment = assess_split(record)
    statement_count = len(unit.get("statement_ids") or ())

    if assessment.likelihood == SPLIT_REQUIRED:
        priority = SCREEN_PRIORITY_HIGH
    elif assessment.likelihood == SPLIT_LIKELY:
        priority = SCREEN_PRIORITY_MEDIUM
    elif assessment.likelihood == SPLIT_INSUFFICIENT_INFORMATION:
        # Volutamente non «bassa». E' il bucket in cui era finito PMID 22277784,
        # e trattarlo come tranquillo ripeterebbe l'errore appena scoperto.
        priority = SCREEN_PRIORITY_MEDIUM
    else:
        priority = SCREEN_PRIORITY_LOW

    # Su quale testo il verdetto e' stato formulato. Serve a non far passare un
    # `split_not_indicated` ricavato dal solo abstract per un negativo forte:
    # l'abstract di PMID 22277784 non mostrava nulla e la fonte conteneva
    # quattro unita'.
    text_basis = "abstract" if record and record.get("abstract_available") else "none"
    negative_is_weak = (
        assessment.likelihood == SPLIT_NOT_INDICATED and text_basis != "full_text"
    )

    return {
        "profile_unit_id": unit.get("profile_unit_id", ""),
        "canonical_source_id": unit.get("canonical_source_id", ""),
        "statement_count": statement_count,
        "is_single_statement": statement_count <= 1,
        "split_likelihood": assessment.likelihood,
        "text_basis": text_basis,
        "negative_verdict_is_weak": negative_is_weak,
        "score": assessment.score,
        "signal_categories": list(assessment.categories),
        "signal_ids": sorted({signal.signal_id for signal in assessment.signals}),
        "signal_evidence": [item.as_dict() for item in assessment.signals[:12]],
        "has_clinical_evidence": assessment.has_clinical,
        "has_preclinical_evidence": assessment.has_preclinical,
        "source_availability": "available" if record and record.get("abstract_available") else "unavailable",
        "review_priority": priority,
        "rationale": assessment.rationale,
        "detector_version": DETECTOR_VERSION,
    }
