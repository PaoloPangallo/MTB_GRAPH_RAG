"""Estrazione ancorata alla fonte, e risoluzione della struttura delle coorti.

Ogni valore prodotto qui porta con se' il **testo che lo giustifica**: pattern,
sezione dell'abstract, offset e stringa esatta. Un qualificatore senza span non
viene emesso, e la ragione e' che un valore plausibile e non verificabile e'
peggio di un valore mancante — il primo entra nelle metriche, il secondo si vede.

L'estrazione e' deterministica e non usa modelli linguistici. E' quindi molto
piu' povera di un lettore umano, e va letta come tale: produce proposte
`source_checked` da confermare, mai una revisione.

Due asimmetrie deliberate.

**La sezione conta.** Un farmaco nominato in RESULTS e' verosimilmente il farmaco
studiato; lo stesso farmaco in BACKGROUND puo' essere un riferimento alla
letteratura. La distinzione separa `direct_support` da `indirect_support`, ed e'
la sola cosa che l'abstract permette di dire onestamente su quel punto.

**Il comparatore viene rilevato ma non nominato.** Riconoscere che uno studio ha
un braccio di confronto e' affidabile; estrarne il nome con una regex non lo e'.
Il campo resta `unknown` e diventa una domanda per il revisore.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

CURATION_VERSION = "source_curation/1.0"

# Stati di risoluzione della coorte ammessi dal protocollo.
COHORT_RESOLVED = "cohort_resolved"
COHORT_PARTIALLY_RESOLVED = "cohort_partially_resolved"
COHORT_NOT_SEPARABLE = "cohort_not_separable"
INSUFFICIENT_SOURCE_INFORMATION = "insufficient_source_information"
SOURCE_UNAVAILABLE = "source_unavailable"
REQUIRES_CLINICAL_REVIEW = "requires_clinical_review"

RESOLUTION_STATES = (
    COHORT_RESOLVED,
    COHORT_PARTIALLY_RESOLVED,
    COHORT_NOT_SEPARABLE,
    INSUFFICIENT_SOURCE_INFORMATION,
    SOURCE_UNAVAILABLE,
    REQUIRES_CLINICAL_REVIEW,
)

# Classificazione della relazione statement-unita'.
CANDIDATE_VALID = "candidate_valid"
CANDIDATE_PARTIAL = "candidate_partial"
CANDIDATE_AMBIGUOUS = "candidate_ambiguous"
CANDIDATE_CONFLICTING = "candidate_conflicting"
CANDIDATE_INVALID = "candidate_invalid"
CANDIDATE_NOT_DETERMINABLE = "candidate_not_determinable"

CANDIDATE_STATES = (
    CANDIDATE_VALID,
    CANDIDATE_PARTIAL,
    CANDIDATE_AMBIGUOUS,
    CANDIDATE_CONFLICTING,
    CANDIDATE_INVALID,
    CANDIDATE_NOT_DETERMINABLE,
)

DIRECT_SUPPORT = "direct_support"
INDIRECT_SUPPORT = "indirect_support"
UNSUPPORTED_BY_PRIMARY_SOURCE = "unsupported_by_primary_source"

# Sezioni in cui un farmaco nominato e' verosimilmente il farmaco studiato.
PRIMARY_SECTIONS = frozenset(
    {
        "METHODS",
        "MATERIALS AND METHODS",
        "PATIENTS AND METHODS",
        "EXPERIMENTAL DESIGN",
        "RESULTS",
        "FINDINGS",
        "PURPOSE",
        "OBJECTIVE",
        "UNLABELLED",
    }
)


@dataclass(frozen=True)
class Detection:
    """Un valore, e il testo che lo giustifica."""

    dimension: str
    value: str
    matched_text: str
    section_label: str
    start: int
    end: int
    pattern_id: str
    confidence: str = "low"

    def as_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "value": self.value,
            "matched_text": self.matched_text,
            "section_label": self.section_label,
            "char_start": self.start,
            "char_end": self.end,
            "pattern_id": self.pattern_id,
            "confidence": self.confidence,
        }

    @property
    def locator(self) -> str:
        return f"abstract#{self.section_label}@{self.start}-{self.end}"


# (dimensione, valore, pattern, id, confidenza)
PATTERNS: tuple[tuple[str, str, str, str, str], ...] = (
    # setting
    ("setting", "neoadjuvant", r"\bneo-?adjuvant\b", "setting.neoadjuvant", "medium"),
    ("setting", "adjuvant", r"(?<!neo)(?<!neo-)\badjuvant\b", "setting.adjuvant", "medium"),
    ("setting", "perioperative", r"\bperi-?operative\b", "setting.perioperative", "medium"),
    ("setting", "metastatic", r"\bmetastatic\b", "setting.metastatic", "medium"),
    ("setting", "locally advanced", r"\blocally advanced\b", "setting.locally_advanced", "medium"),
    ("setting", "advanced", r"\badvanced\b", "setting.advanced", "low"),
    # linea di terapia
    ("therapy_line", "first line", r"\bfirst-?line\b", "line.first", "medium"),
    ("therapy_line", "first line", r"\b(?:previously untreated|treatment-?na[iï]ve|chemotherapy-?na[iï]ve)\b", "line.naive", "medium"),
    ("therapy_line", "second line or later", r"\bsecond-?line\b", "line.second", "medium"),
    ("therapy_line", "second line or later", r"\b(?:previously treated|pre-?treated|after (?:progression|failure) on)\b", "line.pretreated", "medium"),
    ("therapy_line", "relapsed or refractory", r"\b(?:relapsed|refractory)\b", "line.relapsed", "low"),
    # stadio
    ("stage", "stage IV", r"\bstage\s*(?:IV|4)\b", "stage.iv", "medium"),
    ("stage", "stage III", r"\bstage\s*(?:III|3)[AB]?\b", "stage.iii", "medium"),
    ("stage", "stage II", r"\bstage\s*(?:II|2)[AB]?\b", "stage.ii", "medium"),
    ("stage", "stage I", r"\bstage\s*(?:I|1)[AB]?\b", "stage.i", "low"),
    # resezione
    ("resection_status", "unresectable", r"\bunresectable\b", "resection.unresectable", "medium"),
    ("resection_status", "resected", r"\b(?:completely )?resected\b", "resection.resected", "medium"),
    ("resection_status", "resectable", r"(?<!un)\bresectable\b", "resection.resectable", "medium"),
    # disegno
    ("evidence_design", "clinical_trial_phase_3", r"\bphase\s*(?:3|III)\b", "design.p3", "medium"),
    ("evidence_design", "clinical_trial_phase_2", r"\bphase\s*(?:2|II)\b", "design.p2", "medium"),
    ("evidence_design", "clinical_trial_phase_1", r"\bphase\s*(?:1|I)\b", "design.p1", "medium"),
    ("evidence_design", "randomized_controlled_trial", r"\brandomi[sz]ed\b", "design.randomized", "medium"),
    ("evidence_design", "single_arm_study", r"\bsingle-?(?:arm|group)\b", "design.single_arm", "medium"),
    ("evidence_design", "retrospective_study", r"\bretrospective(?:ly)?\b", "design.retrospective", "medium"),
    ("evidence_design", "case_report", r"\bcase report\b", "design.case_report", "medium"),
    # preclinico: affermazioni dirette, non deduzioni per assenza
    ("evidence_design", "preclinical_in_vitro", r"\bin vitro\b", "design.in_vitro", "medium"),
    ("evidence_design", "preclinical_cell_lines", r"\bcell lines?\b", "design.cell_lines", "medium"),
    ("evidence_design", "preclinical_xenograft", r"\bxenograft|patient-?derived xenograft|\bPDX\b", "design.xenograft", "medium"),
    ("evidence_design", "preclinical_mouse_model", r"\b(?:mouse|murine) model\b", "design.mouse", "medium"),
)

# Marcatori della struttura delle coorti.
MULTI_COHORT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bcohorts?\s+[AB1-9]\b", "cohort.named"),
    (r"\barms?\s+[AB1-9]\b", "cohort.arm_named"),
    (r"\b(?:two|three|four|2|3|4)\s+cohorts\b", "cohort.counted"),
    (r"\b(?:two|three|four|2|3|4)\s+(?:treatment\s+)?arms\b", "cohort.arms_counted"),
    (r"\brandomly assigned\b", "cohort.randomised"),
    (r"\brandomi[sz]ed\s+(?:1:1|2:1|to receive)\b", "cohort.randomised_ratio"),
    (r"\bcompared with\b|\bversus\b|\bvs\.?\b", "cohort.comparator"),
)

SINGLE_COHORT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bsingle-?arm\b", "single.arm"),
    (r"\bsingle-?group\b", "single.group"),
    (r"\bone cohort\b", "single.one_cohort"),
)

COMPARATOR_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bversus\b", "comparator.versus"),
    (r"\bcompared with\b", "comparator.compared_with"),
    (r"\bcontrol (?:arm|group)\b", "comparator.control_arm"),
    (r"\bplacebo\b", "comparator.placebo"),
)


def _sections(record: Mapping[str, Any]) -> list[tuple[str, str]]:
    sections = record.get("abstract_sections") or []
    if sections:
        return [(str(item.get("label") or "UNLABELLED"), str(item.get("text") or "")) for item in sections]
    text = str(record.get("abstract_text") or "")
    return [("UNLABELLED", text)] if text else []


def detect(record: Mapping[str, Any]) -> list[Detection]:
    """Tutte le rilevazioni, con la sezione in cui cadono."""
    found: list[Detection] = []
    for label, text in _sections(record):
        for dimension, value, pattern, pattern_id, confidence in PATTERNS:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                found.append(
                    Detection(
                        dimension=dimension,
                        value=value,
                        matched_text=match.group(0),
                        section_label=label,
                        start=match.start(),
                        end=match.end(),
                        pattern_id=pattern_id,
                        confidence=confidence,
                    )
                )
    return found


def _markers(record: Mapping[str, Any], patterns: Sequence[tuple[str, str]]) -> list[Detection]:
    found: list[Detection] = []
    for label, text in _sections(record):
        for pattern, pattern_id in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                found.append(
                    Detection(
                        dimension="cohort_structure",
                        value=pattern_id,
                        matched_text=match.group(0),
                        section_label=label,
                        start=match.start(),
                        end=match.end(),
                        pattern_id=pattern_id,
                        confidence="medium",
                    )
                )
    return found


def collapse(detections: Sequence[Detection], dimension: str) -> Detection | None:
    """Un solo valore per dimensione, o nessuno se le rilevazioni discordano.

    Il silenzio in caso di disaccordo e' voluto. Se l'abstract dice sia
    «adiuvante» sia «metastatico», la risposta giusta non e' sceglierne uno con
    una regola di precedenza inventata: e' non rispondere e chiedere a chi legge
    la fonte.
    """
    relevant = [item for item in detections if item.dimension == dimension]
    if not relevant:
        return None
    values = {item.value for item in relevant}
    if len(values) > 1:
        return None
    # Fra piu' occorrenze dello stesso valore si tiene quella in una sezione
    # primaria, che e' il locator piu' difendibile.
    primary = [item for item in relevant if item.section_label in PRIMARY_SECTIONS]
    pool = primary or relevant
    return sorted(pool, key=lambda item: (item.section_label, item.start))[0]


@dataclass
class CohortResolution:
    """L'esito della domanda: quante coorti descrive questa fonte?"""

    profile_unit_id: str
    canonical_source_id: str
    state: str
    cohort_count_asserted: int | None = None
    multi_cohort_markers: tuple[Detection, ...] = ()
    single_cohort_markers: tuple[Detection, ...] = ()
    comparator_markers: tuple[Detection, ...] = ()
    statement_intervention_count: int = 0
    criterion: str = ""
    explanation: str = ""
    requires_clinical_review: bool = True
    new_units_created: int = 0
    shared_dimensions: tuple[str, ...] = ()
    specific_dimensions: tuple[str, ...] = ()
    unknown_dimensions: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile_unit_id": self.profile_unit_id,
            "canonical_source_id": self.canonical_source_id,
            "resolution_state": self.state,
            "cohort_count_asserted": self.cohort_count_asserted,
            "multi_cohort_markers": [item.as_dict() for item in self.multi_cohort_markers],
            "single_cohort_markers": [item.as_dict() for item in self.single_cohort_markers],
            "comparator_markers": [item.as_dict() for item in self.comparator_markers],
            "statement_intervention_count": self.statement_intervention_count,
            "criterion": self.criterion,
            "explanation": self.explanation,
            "requires_clinical_review": self.requires_clinical_review,
            "new_units_created": self.new_units_created,
            "shared_dimensions": list(self.shared_dimensions),
            "specific_dimensions": list(self.specific_dimensions),
            "unknown_dimensions": list(self.unknown_dimensions),
            "curation_version": CURATION_VERSION,
        }


def resolve_cohorts(
    *,
    profile_unit_id: str,
    canonical_source_id: str,
    abstract: Mapping[str, Any] | None,
    intervention_count: int,
    disease_count: int,
) -> CohortResolution:
    """Decide lo stato della coorte dai marcatori realmente presenti.

    Nessuno stato viene assegnato per esclusione o per default ottimistico:
    ogni ramo cita il marcatore che lo giustifica, e l'assenza di marcatori
    produce `insufficient_source_information`, non «coorte unica».
    """
    if abstract is None or not abstract.get("abstract_available"):
        return CohortResolution(
            profile_unit_id=profile_unit_id,
            canonical_source_id=canonical_source_id,
            state=SOURCE_UNAVAILABLE,
            statement_intervention_count=intervention_count,
            criterion="nessun abstract disponibile nel record del registro",
            explanation=(
                "La fonte non espone un abstract. Serve il full text, che questa fase "
                "non recupera."
            ),
        )

    multi = tuple(_markers(abstract, MULTI_COHORT_PATTERNS))
    single = tuple(_markers(abstract, SINGLE_COHORT_PATTERNS))
    comparators = tuple(_markers(abstract, COMPARATOR_PATTERNS))

    if single and not multi:
        state = COHORT_RESOLVED if intervention_count <= 1 else COHORT_NOT_SEPARABLE
        if state == COHORT_NOT_SEPARABLE:
            explanation = (
                f"La fonte dichiara un braccio unico, ma gli statement le attribuiscono "
                f"{intervention_count} interventi distinti. La discrepanza non si risolve "
                "scegliendo: o alcuni statement citano la fonte in modo indiretto, oppure "
                "il grafo ha attribuito alla fonte un farmaco che essa nomina soltanto."
            )
        else:
            explanation = "Braccio unico dichiarato dalla fonte e un solo intervento negli statement."
        return CohortResolution(
            profile_unit_id=profile_unit_id,
            canonical_source_id=canonical_source_id,
            state=state,
            cohort_count_asserted=1,
            multi_cohort_markers=multi,
            single_cohort_markers=single,
            comparator_markers=comparators,
            statement_intervention_count=intervention_count,
            criterion="marcatore esplicito di braccio unico",
            explanation=explanation,
            requires_clinical_review=state != COHORT_RESOLVED,
        )

    if multi:
        return CohortResolution(
            profile_unit_id=profile_unit_id,
            canonical_source_id=canonical_source_id,
            state=COHORT_PARTIALLY_RESOLVED,
            cohort_count_asserted=None,
            multi_cohort_markers=multi,
            single_cohort_markers=single,
            comparator_markers=comparators,
            statement_intervention_count=intervention_count,
            criterion="marcatori espliciti di piu' bracci o coorti",
            explanation=(
                "La fonte descrive piu' di un braccio. L'abstract stabilisce che le coorti "
                "esistono, ma non permette di assegnare ciascuno statement alla propria: "
                "servirebbe il full text. Le unita' non vengono suddivise, perche' una "
                "suddivisione basata sugli statement del sistema creerebbe coorti che la "
                "fonte non afferma."
            ),
            requires_clinical_review=True,
        )

    if intervention_count > 1 or disease_count > 1:
        return CohortResolution(
            profile_unit_id=profile_unit_id,
            canonical_source_id=canonical_source_id,
            state=INSUFFICIENT_SOURCE_INFORMATION,
            multi_cohort_markers=multi,
            single_cohort_markers=single,
            comparator_markers=comparators,
            statement_intervention_count=intervention_count,
            criterion="nessun marcatore di struttura nell'abstract",
            explanation=(
                "Gli statement attribuiscono alla fonte piu' interventi o piu' malattie, ma "
                "l'abstract non contiene marcatori di struttura. L'assenza di marcatori non "
                "dimostra che la coorte sia unica."
            ),
            requires_clinical_review=True,
        )

    return CohortResolution(
        profile_unit_id=profile_unit_id,
        canonical_source_id=canonical_source_id,
        state=COHORT_RESOLVED,
        cohort_count_asserted=1,
        multi_cohort_markers=multi,
        single_cohort_markers=single,
        comparator_markers=comparators,
        statement_intervention_count=intervention_count,
        criterion="un solo intervento e una sola malattia negli statement, nessun marcatore contrario",
        explanation="Nulla nella fonte o negli statement suggerisce piu' di una coorte.",
        requires_clinical_review=False,
    )


def classify_statement_support(
    *,
    abstract: Mapping[str, Any] | None,
    intervention: str,
    has_conflict: bool,
    cohort_state: str,
) -> tuple[str, str, str]:
    """Classifica la relazione statement-unita' e il tipo di supporto.

    Restituisce `(stato del candidato, tipo di supporto, spiegazione)`.
    """
    if has_conflict:
        return (
            CANDIDATE_CONFLICTING,
            UNSUPPORTED_BY_PRIMARY_SOURCE,
            "conflitto gia' registrato fra la denominazione della fonte e quella dello statement",
        )
    if abstract is None or not abstract.get("abstract_available"):
        return (
            CANDIDATE_NOT_DETERMINABLE,
            UNSUPPORTED_BY_PRIMARY_SOURCE,
            "nessun abstract: il supporto non e' verificabile in questa fase",
        )

    needle = (intervention or "").strip().casefold()
    if not needle:
        return (
            CANDIDATE_NOT_DETERMINABLE,
            UNSUPPORTED_BY_PRIMARY_SOURCE,
            "lo statement non nomina un intervento",
        )

    primary_hit = False
    secondary_hit = False
    for label, text in _sections(abstract):
        if needle in text.casefold():
            if label in PRIMARY_SECTIONS:
                primary_hit = True
            else:
                secondary_hit = True

    if primary_hit:
        state = (
            CANDIDATE_AMBIGUOUS
            if cohort_state in (COHORT_PARTIALLY_RESOLVED, COHORT_NOT_SEPARABLE)
            else CANDIDATE_VALID
        )
        explanation = (
            "l'intervento compare in una sezione primaria, ma la coorte non e' risolta: "
            "non si sa a quale braccio lo statement appartenga"
            if state == CANDIDATE_AMBIGUOUS
            else "l'intervento compare in una sezione primaria dell'abstract"
        )
        return state, DIRECT_SUPPORT, explanation

    if secondary_hit:
        return (
            CANDIDATE_PARTIAL,
            INDIRECT_SUPPORT,
            "l'intervento compare solo in sezioni non primarie: puo' essere un riferimento "
            "alla letteratura invece dell'oggetto dello studio",
        )

    # Volutamente non `candidate_invalid`. Un abstract non nomina tutto cio' che
    # il testo completo contiene, e dedurre la falsita' della claim dall'assenza
    # nell'abstract sarebbe un errore piu' grave di quello che eviterebbe.
    return (
        CANDIDATE_NOT_DETERMINABLE,
        UNSUPPORTED_BY_PRIMARY_SOURCE,
        "l'intervento non compare nell'abstract; l'assenza nell'abstract non dimostra "
        "che la fonte non lo tratti nel full text",
    )
