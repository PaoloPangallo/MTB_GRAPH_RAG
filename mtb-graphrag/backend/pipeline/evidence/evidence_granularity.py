"""A quante persone si riferisce una evidenza, e che cosa questo vieta.

Una osservazione su un paziente e una proprieta' di una coorte hanno la stessa
forma — un biomarcatore, un farmaco, una direzione — e questo le rende
scambiabili per errore. Scambiare la prima con la seconda e' il modo piu' rapido
di far diventare quattordici pazienti cio' che si e' visto in uno, e nessun campo
del profilo se ne accorgerebbe: il risultato resta un record valido.

La granularita' e' il campo che se ne accorge. Non descrive la qualita'
dell'evidenza — un caso singolo puo' essere ben documentato quanto una coorte —
ma il **denominatore** a cui appartiene, e dal denominatore discendono tre
divieti:

- non si generalizza alla coorte da cui il caso proviene;
- non si generalizza alla popolazione della malattia;
- non si stima una frequenza. Un paziente su un denominatore ignoto non e' una
  percentuale, e due lo sono ancora meno: sembrano abbastanza da tentare.

E un quarto divieto, che sembra diverso e non lo e': una alterazione trovata
**dopo** il trattamento in un paziente non e' un criterio di arruolamento. La
direzione temporale non si inverte, e un reperto promosso a requisito farebbe
sembrare selezionata una popolazione che non lo era.

Il modulo non nomina fonti ne' pubblicazioni: la distinzione vale ovunque, e
legarla a un caso concreto la renderebbe inapplicabile al successivo.
"""

from __future__ import annotations

from typing import Any, Mapping

GRANULARITY_VERSION = "evidence_granularity/1.0"

# --- livelli ------------------------------------------------------------------
# Ordinati dal piu' ampio al piu' stretto. L'ordine non e' decorativo: un valore
# non si propaga mai verso un livello piu' ampio di quello in cui e' stato
# osservato.
GRANULARITY_POPULATION = "population_level"
GRANULARITY_COHORT = "cohort_level"
GRANULARITY_SUBGROUP = "subgroup_level"
# Piu' di un paziente, tutti nominati, troppo pochi per essere un denominatore.
# Serve un livello proprio: chiamarlo `case_level` direbbe «un paziente» quando
# sono due, e chiamarlo `subgroup_level` gli darebbe un denominatore che non ha.
GRANULARITY_NAMED_PATIENT_SUBSET = "named_patient_subset"
GRANULARITY_CASE = "case_level"
GRANULARITY_UNKNOWN = "unknown"

GRANULARITY_LEVELS = (
    GRANULARITY_POPULATION,
    GRANULARITY_COHORT,
    GRANULARITY_SUBGROUP,
    GRANULARITY_NAMED_PATIENT_SUBSET,
    GRANULARITY_CASE,
    GRANULARITY_UNKNOWN,
)

# I livelli da cui non si sale. `unknown` non e' fra questi: non sapere il
# denominatore non e' sapere che e' piccolo, ed e' un problema diverso.
NON_GENERALIZABLE_GRANULARITIES = (
    GRANULARITY_CASE,
    GRANULARITY_NAMED_PATIENT_SUBSET,
)

# --- ambiti di popolazione ----------------------------------------------------
SCOPE_SINGLE_PATIENT = "single_patient"
SCOPE_NAMED_PATIENTS_SUBSET = "named_patients_subset"
SCOPE_COHORT = "cohort"
SCOPE_POPULATION = "general_population"
SCOPE_UNKNOWN = "unknown"

POPULATION_SCOPES = (
    SCOPE_SINGLE_PATIENT,
    SCOPE_NAMED_PATIENTS_SUBSET,
    SCOPE_COHORT,
    SCOPE_POPULATION,
    SCOPE_UNKNOWN,
)

# Ambiti che una evidenza non generalizzabile non puo' dichiarare.
GENERALIZED_SCOPES = (SCOPE_COHORT, SCOPE_POPULATION)

FORBIDDEN = "forbidden"


# --- errori tipizzati ---------------------------------------------------------


class EvidenceGranularityError(RuntimeError):
    """Una evidenza dichiara un denominatore che non ha."""

    rule_id = "evidence_granularity"


class CaseLevelGeneralizationError(EvidenceGranularityError):
    """Una osservazione su singoli pazienti estesa alla coorte o alla popolazione."""

    rule_id = "case_level_to_cohort_population"


class FrequencyInferenceError(EvidenceGranularityError):
    """Una frequenza dedotta da osservazioni che non hanno un denominatore."""

    rule_id = "case_level_frequency_inference"


class CaseLevelRequirementError(EvidenceGranularityError):
    """Un reperto acquisito promosso a criterio di arruolamento."""

    rule_id = "case_level_to_enrolment_requirement"


# --- interrogazione -----------------------------------------------------------


def is_non_generalizable(granularity: Any) -> bool:
    """La granularita' vieta la generalizzazione al denominatore superiore?"""
    return str(granularity or "").strip().casefold() in NON_GENERALIZABLE_GRANULARITIES


def granularity_of(record: Mapping[str, Any]) -> str:
    """La granularita' dichiarata da un record serializzato.

    Accetta anche i record che portano soltanto il booleano storico `case_level`:
    gli artefatti precedenti al vocabolario lo usavano, e riscriverli per farli
    combaciare cancellerebbe la loro data.
    """
    declared = str(record.get("evidence_granularity") or "").strip()
    if declared:
        return declared
    if record.get("case_level"):
        return GRANULARITY_CASE
    return GRANULARITY_UNKNOWN


def constraints_for(granularity: str) -> dict[str, Any]:
    """I divieti che discendono da un livello, in forma serializzabile.

    Restituirli invece di lasciarli scrivere a mano su ogni record e' cio' che
    impedisce a un artefatto di dichiararsi case-level e generalizzabile insieme.
    """
    if is_non_generalizable(granularity):
        return {
            "evidence_granularity": granularity,
            "cohort_generalizable": False,
            "population_level_propagation": FORBIDDEN,
            "frequency_inference": FORBIDDEN,
            "enrolment_requirement_promotion": FORBIDDEN,
            "granularity_version": GRANULARITY_VERSION,
        }
    return {
        "evidence_granularity": granularity,
        "cohort_generalizable": granularity == GRANULARITY_COHORT,
        "population_level_propagation": "allowed_within_declared_denominator",
        "frequency_inference": "allowed_within_declared_denominator",
        "enrolment_requirement_promotion": FORBIDDEN,
        "granularity_version": GRANULARITY_VERSION,
    }


__all__ = [
    "GRANULARITY_VERSION",
    "GRANULARITY_POPULATION",
    "GRANULARITY_COHORT",
    "GRANULARITY_SUBGROUP",
    "GRANULARITY_NAMED_PATIENT_SUBSET",
    "GRANULARITY_CASE",
    "GRANULARITY_UNKNOWN",
    "GRANULARITY_LEVELS",
    "NON_GENERALIZABLE_GRANULARITIES",
    "SCOPE_SINGLE_PATIENT",
    "SCOPE_NAMED_PATIENTS_SUBSET",
    "SCOPE_COHORT",
    "SCOPE_POPULATION",
    "SCOPE_UNKNOWN",
    "POPULATION_SCOPES",
    "GENERALIZED_SCOPES",
    "FORBIDDEN",
    "EvidenceGranularityError",
    "CaseLevelGeneralizationError",
    "FrequencyInferenceError",
    "CaseLevelRequirementError",
    "is_non_generalizable",
    "granularity_of",
    "constraints_for",
]
