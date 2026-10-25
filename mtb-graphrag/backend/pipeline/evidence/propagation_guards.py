"""Regole eseguibili che impediscono la propagazione di qualificatori sbagliati.

`check_propagation` in `build_first_review_artifacts` copre il caso concreto di
PMID 22277784. Queste regole sono la sua generalizzazione: valgono per qualunque
fonte, non contengono nomi di farmaci ne' di studi, e ciascuna porta un errore
tipizzato, un esempio che deve fallire e uno che deve passare.

Perche' tipizzare gli errori. Un elenco di stringhe dice *che* qualcosa e'
andato storto; un tipo dice *cosa*, e permette a chi chiama di decidere se una
violazione blocca la pipeline o va solo segnalata. La distinzione conta qui:
propagare una popolazione clinica su un modello cellulare deve bloccare, mentre
un'assenza dall'abstract trattata come assenza dalla fonte e' un errore di
ragionamento che si vuole vedere ma non necessariamente fermare.

Il principio comune a tutte: **l'assenza di informazione non e' informazione di
assenza**, e due cose di natura diversa non si qualificano a vicenda.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from .evidence_granularity import (
    CaseLevelGeneralizationError,
    CaseLevelRequirementError,
    FrequencyInferenceError,
    GENERALIZED_SCOPES,
    is_non_generalizable,
    granularity_of,
)
from .profile_unit import CLINICAL_UNIT_TYPES, PRECLINICAL_UNIT_TYPES

GUARD_VERSION = "propagation_guards/1.2"

# --- errori tipizzati ---------------------------------------------------------


class PropagationError(RuntimeError):
    """Un qualificatore sta per essere applicato dove non vale."""

    rule_id = "propagation"


class ClinicalToPreclinicalError(PropagationError):
    """Una proprieta' di pazienti applicata a un modello sperimentale."""

    rule_id = "clinical_to_preclinical"


class PreclinicalToClinicalError(PropagationError):
    """Una proprieta' di un modello sperimentale applicata a pazienti."""

    rule_id = "preclinical_to_clinical"


class CrossCohortError(PropagationError):
    """Una proprieta' di una coorte applicata a un'altra."""

    rule_id = "cross_cohort"


class CrossArmError(PropagationError):
    """Un intervento di un braccio applicato a un altro."""

    rule_id = "cross_arm"


class SubgroupToPopulationError(PropagationError):
    """Un biomarcatore di sottogruppo esteso alla popolazione globale."""

    rule_id = "subgroup_to_population"


class EvidenceStrengthError(PropagationError):
    """Un'evidenza viene riportata piu' forte di quanto sia."""

    rule_id = "evidence_strength"


class ProvenanceError(PropagationError):
    """Una normalizzazione terminologica senza provenienza."""

    rule_id = "provenance"


class CrossModelError(PropagationError):
    """Una proprieta' di un modello attribuita a un altro modello."""

    rule_id = "cross_model_identity"


class BiomarkerRoleError(PropagationError):
    """Un reperto molecolare trasformato in criterio di arruolamento."""

    rule_id = "observed_biomarker_role"


class AbsenceInferenceError(PropagationError):
    """L'assenza in una fonte parziale trattata come assenza nella fonte."""

    rule_id = "absence_inference"


# I tre errori della granularita' appartengono a due famiglie insieme, e non e'
# un vezzo: `evidence_granularity` possiede il concetto — che vale anche fuori
# dalle guardie — mentre `PropagationError` e' la famiglia che chi esegue la
# pipeline intercetta. Ereditare da una sola costringerebbe a scegliere fra un
# vocabolario dimezzato e un errore che sfugge al catch esistente.


class CaseLevelPropagationError(PropagationError, CaseLevelGeneralizationError):
    """Osservazioni su singoli pazienti estese alla coorte o alla popolazione."""

    rule_id = CaseLevelGeneralizationError.rule_id


class CaseLevelFrequencyError(PropagationError, FrequencyInferenceError):
    """Una frequenza dedotta da osservazioni senza denominatore."""

    rule_id = FrequencyInferenceError.rule_id


class CaseLevelEnrolmentError(PropagationError, CaseLevelRequirementError):
    """Un reperto acquisito su singoli pazienti promosso a criterio di arruolamento."""

    rule_id = CaseLevelRequirementError.rule_id


# --- vocabolario --------------------------------------------------------------

# I vocabolari vengono dallo schema e non sono riscritti qui. Duplicarli
# significherebbe che ogni tipo di unita' aggiunto allo schema resterebbe
# invisibile alle guardie — e una unita' che le guardie non riconoscono passa
# tutti i controlli senza che nessuno se ne accorga.
CLINICAL_UNIT_KINDS = frozenset(CLINICAL_UNIT_TYPES)
PRECLINICAL_UNIT_KINDS = frozenset(PRECLINICAL_UNIT_TYPES)

_PATIENT_TERMS = re.compile(
    r"\b(?:patients?|subjects?|participants?|enrolled|cases?)\b", re.IGNORECASE
)
_MODEL_TERMS = re.compile(
    r"\b(?:cell lines?|Ba/?F3|xenograft|PDX|in vitro|in vivo|murine|mouse|mice|"
    r"parental|transfected|engineered)\b",
    re.IGNORECASE,
)
_PRECLINICAL_SETTING = re.compile(r"\b(?:preclinical|in vitro|in vivo)\b", re.IGNORECASE)

# Dimensioni che non hanno senso su un modello sperimentale.
CLINICAL_ONLY_DIMENSIONS = (
    "therapy_line",
    "prior_therapies",
    "resection_status",
    "stage",
    "inclusion_criteria",
    "exclusion_criteria",
)

NON_VALUES = frozenset({"", "unknown", "not_applicable", "not_separable"})


@dataclass(frozen=True)
class GuardViolation:
    """Una violazione, con la regola che l'ha rilevata."""

    rule_id: str
    rule_name: str
    error_type: type[PropagationError]
    subject: str
    dimensions: tuple[str, ...]
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "error_type": self.error_type.__name__,
            "subject": self.subject,
            "dimensions": list(self.dimensions),
            "message": self.message,
        }

    def raise_it(self) -> None:
        raise self.error_type(self.message)


def _value(unit: Mapping[str, Any], dimension: str) -> str:
    value = unit.get(dimension)
    if isinstance(value, (list, tuple)):
        return " ".join(str(item) for item in value)
    return "" if value is None else str(value)


def _has_value(unit: Mapping[str, Any], dimension: str) -> bool:
    value = unit.get(dimension)
    if isinstance(value, (list, tuple)):
        return bool(value)
    return str(value or "").strip().casefold() not in NON_VALUES


def _is_clinical(unit: Mapping[str, Any]) -> bool:
    return str(unit.get("unit_type") or "") in CLINICAL_UNIT_KINDS


def _is_preclinical(unit: Mapping[str, Any]) -> bool:
    return str(unit.get("unit_type") or "") in PRECLINICAL_UNIT_KINDS


# --- regole -------------------------------------------------------------------


def rule_clinical_population_to_model(unit: Mapping[str, Any]) -> list[GuardViolation]:
    """Una popolazione di pazienti non descrive un modello sperimentale."""
    if not _is_preclinical(unit):
        return []
    population = _value(unit, "population")
    if population and _PATIENT_TERMS.search(population):
        return [
            GuardViolation(
                "clinical_population_to_model",
                "popolazione clinica su modello sperimentale",
                ClinicalToPreclinicalError,
                str(unit.get("profile_unit_id") or ""),
                ("population",),
                f"unita' preclinica con popolazione di pazienti: «{population}»",
            )
        ]
    return []


def rule_clinical_dimensions_to_model(unit: Mapping[str, Any]) -> list[GuardViolation]:
    """Linea, stadio, resezione e criteri non si pongono su un modello."""
    if not _is_preclinical(unit):
        return []
    offending = tuple(
        dimension for dimension in CLINICAL_ONLY_DIMENSIONS if _has_value(unit, dimension)
    )
    if not offending:
        return []
    return [
        GuardViolation(
            "clinical_dimensions_to_model",
            "dimensioni cliniche su modello sperimentale",
            ClinicalToPreclinicalError,
            str(unit.get("profile_unit_id") or ""),
            offending,
            f"unita' preclinica con dimensioni cliniche valorizzate: {list(offending)}",
        )
    ]


def rule_preclinical_setting_to_patients(unit: Mapping[str, Any]) -> list[GuardViolation]:
    """Un setting preclinico non descrive una coorte di pazienti."""
    if not _is_clinical(unit):
        return []
    setting = _value(unit, "setting")
    if setting and _PRECLINICAL_SETTING.search(setting):
        return [
            GuardViolation(
                "preclinical_setting_to_patients",
                "setting preclinico su coorte clinica",
                PreclinicalToClinicalError,
                str(unit.get("profile_unit_id") or ""),
                ("setting",),
                f"coorte clinica con setting preclinico: «{setting}»",
            )
        ]
    return []


def rule_model_comparator_to_patients(unit: Mapping[str, Any]) -> list[GuardViolation]:
    """Un comparatore cellulare non e' un braccio di confronto clinico."""
    if not _is_clinical(unit):
        return []
    comparator = _value(unit, "comparator")
    if comparator and _MODEL_TERMS.search(comparator):
        return [
            GuardViolation(
                "model_comparator_to_patients",
                "comparatore cellulare su coorte clinica",
                PreclinicalToClinicalError,
                str(unit.get("profile_unit_id") or ""),
                ("comparator",),
                f"coorte clinica con comparatore sperimentale: «{comparator}»",
            )
        ]
    return []


def rule_cross_cohort(units: Sequence[Mapping[str, Any]]) -> list[GuardViolation]:
    """Due unita' della stessa fonte non condividono i qualificatori specifici.

    Se due coorti della stessa pubblicazione dichiarano lo stesso identico
    setting, linea e popolazione, o sono la stessa coorte — e allora non
    andavano separate — o un valore e' stato copiato dall'una all'altra.
    """
    violations: list[GuardViolation] = []
    by_source: dict[str, list[Mapping[str, Any]]] = {}
    for unit in units:
        by_source.setdefault(str(unit.get("canonical_source_id") or ""), []).append(unit)

    for source, group in by_source.items():
        if len(group) < 2:
            continue
        for index, left in enumerate(group):
            for right in group[index + 1 :]:
                if str(left.get("cohort_id")) == str(right.get("cohort_id")):
                    continue
                shared = tuple(
                    dimension
                    for dimension in ("population", "setting", "therapy_line")
                    if _has_value(left, dimension)
                    and _value(left, dimension) == _value(right, dimension)
                )
                if len(shared) >= 3:
                    violations.append(
                        GuardViolation(
                            "cross_cohort_identity",
                            "qualificatori identici fra coorti distinte",
                            CrossCohortError,
                            f"{left.get('profile_unit_id')} / {right.get('profile_unit_id')}",
                            shared,
                            (
                                f"due unita' di {source} condividono {list(shared)}: o sono "
                                "la stessa coorte, o un valore e' stato copiato"
                            ),
                        )
                    )
    return violations


def rule_cross_arm_intervention(units: Sequence[Mapping[str, Any]]) -> list[GuardViolation]:
    """Un braccio non eredita l'intervento di un altro braccio."""
    violations: list[GuardViolation] = []
    by_source: dict[str, list[Mapping[str, Any]]] = {}
    for unit in units:
        if str(unit.get("unit_type")) == "clinical_trial_arm":
            by_source.setdefault(str(unit.get("canonical_source_id") or ""), []).append(unit)

    for source, group in by_source.items():
        if len(group) < 2:
            continue
        seen: dict[str, str] = {}
        for unit in group:
            for name in unit.get("intervention") or ():
                key = str(name).casefold()
                owner = seen.get(key)
                if owner and owner != str(unit.get("cohort_id")):
                    violations.append(
                        GuardViolation(
                            "cross_arm_intervention",
                            "intervento condiviso fra bracci distinti",
                            CrossArmError,
                            str(unit.get("profile_unit_id") or ""),
                            ("intervention",),
                            f"«{name}» compare in due bracci distinti di {source}",
                        )
                    )
                seen.setdefault(key, str(unit.get("cohort_id")))
    return violations


def rule_subgroup_to_population(unit: Mapping[str, Any]) -> list[GuardViolation]:
    """Un requisito di sottogruppo non descrive la popolazione globale."""
    label = str(unit.get("cohort_label") or "").casefold()
    if "subgroup" not in label and "sottogruppo" not in label:
        return []
    population = _value(unit, "population").casefold()
    if population and not any(
        term in population for term in ("subgroup", "sottogruppo", "subset")
    ):
        return [
            GuardViolation(
                "subgroup_to_population",
                "sottogruppo presentato come popolazione globale",
                SubgroupToPopulationError,
                str(unit.get("profile_unit_id") or ""),
                ("population", "biomarker_requirements"),
                (
                    "l'unita' descrive un sottogruppo ma la popolazione non lo dichiara: "
                    "il requisito verrebbe esteso a tutti"
                ),
            )
        ]
    return []


def rule_relative_versus_complete_resistance(
    decision: Mapping[str, Any]
) -> list[GuardViolation]:
    """Sensibilita' ridotta e resistenza completa non sono la stessa cosa."""
    qualifier = str(decision.get("resistance_qualifier") or "")
    text = " ".join(
        str(decision.get(key) or "") for key in ("rationale", "note", "explanation")
    ).casefold()
    if qualifier == "complete_resistance" and re.search(
        r"\b(?:reduced|residual|retain(?:s|ed)?|partial)\b", text
    ):
        return [
            GuardViolation(
                "relative_versus_complete_resistance",
                "resistenza relativa riportata come completa",
                EvidenceStrengthError,
                str(decision.get("statement_id") or ""),
                ("resistance_qualifier",),
                (
                    "la motivazione descrive attivita' residua ma il qualificatore dichiara "
                    "resistenza completa"
                ),
            )
        ]
    return []


def rule_in_vitro_to_clinical_benefit(decision: Mapping[str, Any]) -> list[GuardViolation]:
    """Sensibilita' in vitro non e' beneficio clinico."""
    if str(decision.get("clinical_or_preclinical") or "") != "preclinical":
        return []
    if decision.get("clinical_response_observed") is True:
        return [
            GuardViolation(
                "in_vitro_to_clinical_benefit",
                "risposta clinica dichiarata su evidenza in vitro",
                EvidenceStrengthError,
                str(decision.get("statement_id") or ""),
                ("clinical_response_observed",),
                "evidenza solo preclinica ma clinical_response_observed = true",
            )
        ]
    return []


def rule_mapping_needs_provenance(mapping: Mapping[str, Any]) -> list[GuardViolation]:
    """Un codice di sviluppo normalizzato senza provenienza e' una fabbricazione."""
    if not mapping.get("mapped_term"):
        return []
    has_status = bool(mapping.get("mapping_status"))
    declares_literal = "literal_string_present_in_source" in mapping
    if has_status and declares_literal:
        return []
    return [
        GuardViolation(
            "mapping_needs_provenance",
            "mapping terminologico senza provenienza",
            ProvenanceError,
            str(mapping.get("source_term") or ""),
            ("intervention",),
            (
                f"«{mapping.get('source_term')}» → «{mapping.get('mapped_term')}» senza "
                "mapping_status o senza dichiarare se la stringa compare nella fonte"
            ),
        )
    ]


def rule_absence_is_not_evidence(decision: Mapping[str, Any]) -> list[GuardViolation]:
    """L'assenza in un testo parziale non dimostra assenza nella fonte."""
    status = str(decision.get("candidate_link_status") or decision.get("candidate_state") or "")
    text = str(decision.get("rationale") or decision.get("explanation") or "").casefold()
    if status == "candidate_invalid" and re.search(
        r"non compare|not (?:present|found|mentioned)|assente", text
    ):
        return [
            GuardViolation(
                "absence_is_not_evidence",
                "assenza nel testo trattata come assenza nella fonte",
                AbsenceInferenceError,
                str(decision.get("statement_id") or ""),
                ("support_type",),
                (
                    "il collegamento e' dichiarato invalido perche' il termine non compare "
                    "nel testo consultato; un abstract non nomina tutto cio' che il full "
                    "text contiene"
                ),
            )
        ]
    return []


def _subject_of(decision: Mapping[str, Any]) -> str:
    return str(
        decision.get("statement_id")
        or decision.get("profile_unit_id")
        or decision.get("gold_link_id")
        or ""
    )


def _denominator(decision: Mapping[str, Any]) -> str:
    subset = decision.get("subset_size")
    cohort = decision.get("cohort_size")
    if subset is None and cohort is None:
        return "un denominatore che la fonte non fornisce"
    return f"{subset if subset is not None else '?'} su {cohort if cohort is not None else '?'}"


def rule_case_level_to_cohort_population(decision: Mapping[str, Any]) -> list[GuardViolation]:
    """Cio' che si e' visto in uno o due pazienti non e' una proprieta' della coorte.

    La regola non guarda quanti pazienti ci sono: guarda che cosa la decisione
    **dichiara** di poter fare col numero che ha. Un record puo' dire di riguardare
    un solo paziente e insieme dichiararsi generalizzabile, e allora le due
    affermazioni non possono essere entrambe vere.
    """
    granularity = granularity_of(decision)
    if not is_non_generalizable(granularity):
        return []

    scope = str(decision.get("population_scope") or "").strip().casefold()
    claims_cohort = bool(decision.get("cohort_generalizable"))
    claims_scope = scope in GENERALIZED_SCOPES
    if not claims_cohort and not claims_scope:
        return []

    declared = "cohort_generalizable=true" if claims_cohort else f"population_scope={scope}"
    return [
        GuardViolation(
            CaseLevelPropagationError.rule_id,
            "evidenza su pazienti nominati estesa al loro denominatore",
            CaseLevelPropagationError,
            _subject_of(decision),
            ("population",),
            (
                f"granularita' {granularity!r} ({_denominator(decision)}) ma la decisione "
                f"dichiara {declared}: estendere l'osservazione al denominatore "
                "trasformerebbe cio' che si e' visto in pochi in una proprieta' di tutti"
            ),
        )
    ]


# I campi che, se valorizzati, dicono che qualcuno ha calcolato una frequenza.
_FREQUENCY_FIELDS = ("frequency", "prevalence", "rate", "proportion", "percentage")


def rule_case_level_frequency_inference(decision: Mapping[str, Any]) -> list[GuardViolation]:
    """Un paziente su un denominatore ignoto non e' una percentuale.

    Due lo sono ancora meno di uno: sembrano abbastanza da tentare la divisione, e
    il risultato ha l'aspetto di una stima invece che di un caso.
    """
    granularity = granularity_of(decision)
    if not is_non_generalizable(granularity):
        return []

    computed = [name for name in _FREQUENCY_FIELDS if _has_value(decision, name)]
    permitted = str(decision.get("frequency_inference") or "").strip().casefold()
    allows = permitted not in ("", "forbidden")
    if not computed and not allows:
        return []

    declared = ", ".join(computed) if computed else f"frequency_inference={permitted}"
    return [
        GuardViolation(
            CaseLevelFrequencyError.rule_id,
            "frequenza dedotta da evidenza senza denominatore",
            CaseLevelFrequencyError,
            _subject_of(decision),
            tuple(computed) or ("frequency_inference",),
            (
                f"granularita' {granularity!r} ({_denominator(decision)}) ma la decisione "
                f"porta {declared}: una frequenza richiede un denominatore, e questa "
                "evidenza non ne ha uno"
            ),
        )
    ]


def rule_case_level_to_enrolment_requirement(
    decision: Mapping[str, Any],
) -> list[GuardViolation]:
    """Un reperto trovato dopo il trattamento non e' un criterio di arruolamento.

    La direzione temporale non si inverte. Un requisito di arruolamento seleziona
    chi entra; una alterazione osservata alla progressione descrive chi e' gia'
    dentro, e promuoverla farebbe sembrare selezionata una popolazione che non lo
    era.
    """
    granularity = granularity_of(decision)
    if not is_non_generalizable(granularity):
        return []

    promoted = bool(decision.get("promoted_to_enrolment_criterion")) or _has_value(
        decision, "biomarker_requirements"
    )
    permitted = str(decision.get("enrolment_requirement_promotion") or "").strip().casefold()
    if not promoted and permitted in ("", "forbidden"):
        return []

    declared = (
        "biomarker_requirements valorizzato"
        if _has_value(decision, "biomarker_requirements")
        else f"enrolment_requirement_promotion={permitted or 'true'}"
    )
    return [
        GuardViolation(
            CaseLevelEnrolmentError.rule_id,
            "reperto acquisito promosso a criterio di arruolamento",
            CaseLevelEnrolmentError,
            _subject_of(decision),
            ("biomarker_requirements",),
            (
                f"granularita' {granularity!r} ma la decisione porta {declared}: una "
                "alterazione osservata su singoli pazienti dopo il trattamento non "
                "puo' diventare il criterio con cui quei pazienti erano stati scelti"
            ),
        )
    ]


def rule_case_report_to_population(unit: Mapping[str, Any]) -> list[GuardViolation]:
    """Un case report non descrive una popolazione."""
    design = _value(unit, "evidence_design").casefold()
    if "case report" not in design and "case_report" not in design:
        return []
    if not _has_value(unit, "population"):
        return []
    population = _value(unit, "population").casefold()
    if not re.search(r"\b(?:case|patient|single)\b", population):
        return [
            GuardViolation(
                "case_report_to_population",
                "case report presentato come popolazione",
                EvidenceStrengthError,
                str(unit.get("profile_unit_id") or ""),
                ("population",),
                f"case report con popolazione generalizzata: «{population}»",
            )
        ]
    return []


def rule_cross_model_identity(units: Sequence[Mapping[str, Any]]) -> list[GuardViolation]:
    """Due modelli distinti della stessa fonte non sono lo stesso modello.

    `cross_cohort_identity` non copre questo caso: confronta popolazione, setting
    e linea di terapia, che su un modello sono `not_applicable` e quindi non
    scattano mai. Un modello si descrive con altro — il fondo cellulare, la
    linea, il saggio — e sono quelle le dimensioni da confrontare.

    Due unita' precliniche che dichiarano lo stesso fondo, la stessa linea e lo
    stesso saggio o sono lo stesso esperimento, e allora non andavano separate,
    oppure un valore e' stato copiato dall'una all'altra.
    """
    violations: list[GuardViolation] = []
    by_source: dict[str, list[Mapping[str, Any]]] = {}
    for unit in units:
        if _is_preclinical(unit):
            by_source.setdefault(str(unit.get("canonical_source_id") or ""), []).append(unit)

    for source, group in by_source.items():
        for index, left in enumerate(group):
            for right in group[index + 1 :]:
                if str(left.get("profile_unit_id")) == str(right.get("profile_unit_id")):
                    continue
                shared = tuple(
                    dimension
                    for dimension in ("model_type", "cell_line", "assay")
                    if _has_value(left, dimension)
                    and _value(left, dimension) == _value(right, dimension)
                )
                if len(shared) >= 3:
                    violations.append(
                        GuardViolation(
                            "cross_model_identity",
                            "modelli distinti con la stessa identita'",
                            CrossModelError,
                            f"{left.get('profile_unit_id')} / {right.get('profile_unit_id')}",
                            shared,
                            (
                                f"due modelli di {source} condividono {list(shared)}: o sono "
                                "lo stesso esperimento, o un valore e' stato copiato"
                            ),
                        )
                    )
    return violations


def rule_observed_biomarker_to_requirement(unit: Mapping[str, Any]) -> list[GuardViolation]:
    """Un'alterazione osservata dopo il trattamento non e' un criterio di ingresso.

    La differenza decide chi verrebbe selezionato. «Pazienti con G1269A» come
    requisito descrive una popolazione che si potrebbe arruolare; «G1269A
    comparso alla progressione» descrive un esito. Promuovere il secondo al primo
    costruisce una coorte che non e' mai esistita.

    La regola chiede che il ruolo del biomarcatore sia dichiarato quando la
    dimensione e' popolata: senza dichiarazione non si distingue un requisito da
    un reperto, e il dubbio va reso esplicito invece di essere risolto in
    silenzio.
    """
    if not _has_value(unit, "biomarker_requirements"):
        return []

    role = str(unit.get("biomarker_role") or "").strip().casefold()
    if role == "enrolment_criterion":
        return []

    message = (
        f"{unit.get('profile_unit_id')} dichiara biomarker_requirements con ruolo "
        f"{role or 'non dichiarato'!r}: un reperto osservato non e' un criterio di "
        "arruolamento, e senza il ruolo i due casi non sono distinguibili"
    )
    return [
        GuardViolation(
            "observed_biomarker_to_requirement",
            "reperto molecolare promosso a criterio di arruolamento",
            BiomarkerRoleError,
            str(unit.get("profile_unit_id") or ""),
            ("biomarker_requirements",),
            message,
        )
    ]


UNIT_RULES: tuple[Callable[[Mapping[str, Any]], list[GuardViolation]], ...] = (
    rule_clinical_population_to_model,
    rule_clinical_dimensions_to_model,
    rule_preclinical_setting_to_patients,
    rule_model_comparator_to_patients,
    rule_subgroup_to_population,
    rule_case_report_to_population,
    rule_observed_biomarker_to_requirement,
)

GROUP_RULES: tuple[Callable[[Sequence[Mapping[str, Any]]], list[GuardViolation]], ...] = (
    rule_cross_cohort,
    rule_cross_arm_intervention,
    rule_cross_model_identity,
)

DECISION_RULES: tuple[Callable[[Mapping[str, Any]], list[GuardViolation]], ...] = (
    rule_relative_versus_complete_resistance,
    rule_in_vitro_to_clinical_benefit,
    rule_absence_is_not_evidence,
    rule_case_level_to_cohort_population,
    rule_case_level_frequency_inference,
    rule_case_level_to_enrolment_requirement,
)

MAPPING_RULES: tuple[Callable[[Mapping[str, Any]], list[GuardViolation]], ...] = (
    rule_mapping_needs_provenance,
)

# Le dodici regole della versione 1.0. Congelate perche' gli artefatti
# dell'audit strutturale le citano per nome: un artefatto che elenca dodici
# regole non e' obsoleto solo perche' ne sono state aggiunte altre, e il test
# deve poter distinguere i due casi.
GUARD_V1_RULE_IDS = (
    "clinical_population_to_model",
    "clinical_dimensions_to_model",
    "preclinical_setting_to_patients",
    "model_comparator_to_patients",
    "cross_cohort_identity",
    "cross_arm_intervention",
    "subgroup_to_population",
    "relative_versus_complete_resistance",
    "in_vitro_to_clinical_benefit",
    "mapping_needs_provenance",
    "absence_is_not_evidence",
    "case_report_to_population",
)

# Aggiunte in 1.1 dalla revisione clinico/preclinica, perche' i loro pattern
# erano generali e nessuna regola esistente li copriva.
GUARD_V11_RULE_IDS = (
    "cross_model_identity",
    "observed_biomarker_to_requirement",
)

# Aggiunte in 1.2 dall'approvazione di una fonte che conteneva osservazioni su
# singoli pazienti dentro una coorte. Il pattern e' generale: nessuna delle tre
# nomina una fonte, e tutte e tre leggono soltanto la granularita' dichiarata.
GUARD_V12_RULE_IDS = (
    "case_level_to_cohort_population",
    "case_level_frequency_inference",
    "case_level_to_enrolment_requirement",
)

ALL_RULE_IDS = GUARD_V1_RULE_IDS + GUARD_V11_RULE_IDS + GUARD_V12_RULE_IDS

# Quali regole erano eseguibili a ciascuna versione. Serve a leggere gli artefatti
# gia' scritti: un risultato prodotto a 1.1 elenca quattordici regole, e
# confrontarlo con l'elenco corrente lo farebbe sembrare incompleto quando invece
# e' completo per la versione che dichiara. Aggiungere una regola non deve poter
# invalidare retroattivamente una verifica passata.
RULE_IDS_BY_VERSION: Mapping[str, tuple[str, ...]] = {
    "propagation_guards/1.0": GUARD_V1_RULE_IDS,
    "propagation_guards/1.1": GUARD_V1_RULE_IDS + GUARD_V11_RULE_IDS,
    "propagation_guards/1.2": ALL_RULE_IDS,
}


def rule_ids_for_version(version: str) -> tuple[str, ...]:
    """Le regole eseguibili alla versione dichiarata da un artefatto.

    Una versione sconosciuta restituisce l'elenco corrente: e' il caso di un
    artefatto scritto da una versione futura, e fingere che avesse meno regole
    sarebbe piu' fuorviante che ammettere di non conoscerla.
    """
    return RULE_IDS_BY_VERSION.get(str(version or ""), ALL_RULE_IDS)


def run_guards(
    *,
    units: Sequence[Mapping[str, Any]] = (),
    decisions: Sequence[Mapping[str, Any]] = (),
    mappings: Sequence[Mapping[str, Any]] = (),
) -> list[GuardViolation]:
    """Esegue tutte le regole e restituisce le violazioni, senza sollevare.

    Non solleva di sua iniziativa: chi chiama decide se una violazione blocca la
    pipeline o va soltanto registrata. `GuardViolation.raise_it` resta
    disponibile per il caso bloccante.
    """
    violations: list[GuardViolation] = []
    for unit in units:
        for rule in UNIT_RULES:
            violations.extend(rule(unit))
    for group_rule in GROUP_RULES:
        violations.extend(group_rule(units))
    for decision in decisions:
        for rule in DECISION_RULES:
            violations.extend(rule(decision))
    for mapping in mappings:
        for rule in MAPPING_RULES:
            violations.extend(rule(mapping))
    return violations


__all__ = [
    "GUARD_VERSION",
    "ALL_RULE_IDS",
    "GUARD_V1_RULE_IDS",
    "GUARD_V11_RULE_IDS",
    "GUARD_V12_RULE_IDS",
    "RULE_IDS_BY_VERSION",
    "rule_ids_for_version",
    "CaseLevelPropagationError",
    "CaseLevelFrequencyError",
    "CaseLevelEnrolmentError",
    "CrossModelError",
    "BiomarkerRoleError",
    "PropagationError",
    "ClinicalToPreclinicalError",
    "PreclinicalToClinicalError",
    "CrossCohortError",
    "CrossArmError",
    "SubgroupToPopulationError",
    "EvidenceStrengthError",
    "ProvenanceError",
    "AbsenceInferenceError",
    "GuardViolation",
    "run_guards",
    "UNIT_RULES",
    "GROUP_RULES",
    "DECISION_RULES",
    "MAPPING_RULES",
]
