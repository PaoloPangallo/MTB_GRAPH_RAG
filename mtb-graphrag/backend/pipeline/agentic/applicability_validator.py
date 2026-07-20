"""Convalida deterministica del verdict di applicabilità prodotto dall'LLM.

Il verificatore LLM (``source_verifier``) produce un giudizio di applicabilità
libero, che può essere permissivo o commettere errori di inferenza clinica —
ad esempio dedurre che "first-line" implichi malattia metastatica, avanzata,
non operata o mai trattata in precedenza. Questo modulo applica regole
deterministiche e testabili, basate esclusivamente su categorie strutturate
(mai su ricerche testuali fragili nelle motivazioni), per convalidare o
ridurre quel verdict. Non lo rende mai più permissivo di quanto prodotto
dall'LLM: può solo confermarlo o renderlo più conservativo.
"""

from __future__ import annotations

from typing import Any, Literal

ApplicabilityStatus = Literal["compatible", "indeterminate", "not_compatible"]

LineCategory = Literal["first_line", "later_line", "post_progression", "adjuvant", "unknown"]
SettingCategory = Literal[
    "resected", "locally_advanced", "metastatic", "recurrent", "adjuvant", "unknown"
]
PriorTherapyRequirement = Literal[
    "treatment_naive", "previously_treated", "specific_therapy", "unknown"
]

LINE_CATEGORIES: frozenset[str] = frozenset(
    {"first_line", "later_line", "post_progression", "adjuvant", "unknown"}
)
SETTING_CATEGORIES: frozenset[str] = frozenset(
    {"resected", "locally_advanced", "metastatic", "recurrent", "adjuvant", "unknown"}
)
PRIOR_THERAPY_REQUIREMENTS: frozenset[str] = frozenset(
    {"treatment_naive", "previously_treated", "specific_therapy", "unknown"}
)

_VERDICT_RANK: dict[str, int] = {"not_compatible": 0, "indeterminate": 1, "compatible": 2}

_LATER_LINE_SOURCE_CATEGORIES = {"later_line", "post_progression"}

# Setting mutuamente esclusivi: un paziente "resected" (nessuna malattia
# attiva nota) non può contemporaneamente essere metastatico, localmente
# avanzato o recidivato, e viceversa.
_MUTUALLY_EXCLUSIVE_SETTINGS = {"metastatic", "locally_advanced", "recurrent"}


def normalize_line_category(value: Any) -> str:
    """Riporta un valore grezzo a una categoria di linea valida, altrimenti 'unknown'."""
    text = value.strip().lower() if isinstance(value, str) else ""
    return text if text in LINE_CATEGORIES else "unknown"


def normalize_setting_category(value: Any) -> str:
    """Riporta un valore grezzo a una categoria di setting valida, altrimenti 'unknown'."""
    text = value.strip().lower() if isinstance(value, str) else ""
    return text if text in SETTING_CATEGORIES else "unknown"


def normalize_prior_therapy_requirement(value: Any) -> str:
    """Riporta un valore grezzo a un requisito di pre-trattamento valido, altrimenti 'unknown'."""
    text = value.strip().lower() if isinstance(value, str) else ""
    return text if text in PRIOR_THERAPY_REQUIREMENTS else "unknown"


def _is_declared(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _normalized_patient_setting(value: Any) -> str:
    if not _is_declared(value):
        return "unknown"
    return str(value).strip().lower().replace("-", "_")


def _normalized_patient_line(value: Any) -> str:
    if not _is_declared(value):
        return "unknown"
    text = str(value).strip().lower()
    if text == "first-line":
        return "first_line"
    if text in {"second-line", "later-line", "post-progression"}:
        return "later_line"
    return "unknown"


def _downgrade(current: str, cap: str) -> str:
    """Restituisce il verdict più conservativo tra ``current`` e ``cap``, mai il contrario."""
    return current if _VERDICT_RANK[current] <= _VERDICT_RANK[cap] else cap


def validate_applicability(
    extracted_source_context: dict[str, Any],
    declared_patient_context: dict[str, Any],
    llm_verdict: str,
) -> ApplicabilityStatus:
    """Convalida/riduce il ``llm_verdict`` sulla base di categorie strutturate.

    Regole (si applicano tutte; il risultato è il verdict più conservativo
    fra quello prodotto dall'LLM e quello imposto da ogni regola violata):

    - "first-line" non implica metastatico, avanzato, non operato o mai
      trattato: nessuna di queste inferenze è mai effettuata qui.
    - un campo del contesto paziente non dichiarato (vuoto/assente) resta
      "sconosciuto", mai sostituito con un default.
    - se la fonte richiede un ``source_setting_category`` noto e il paziente
      non ha dichiarato un ``disease_setting``, il verdict è ridotto ad
      "indeterminate".
    - se la fonte richiede stadio avanzato/metastatico (setting "metastatic"
      o "locally_advanced") e il paziente non ha dichiarato ``disease_stage``,
      il verdict è ridotto ad "indeterminate".
    - se la fonte richiede la presenza/assenza di trattamenti precedenti
      (``source_prior_therapy_requirement`` noto) e il campo paziente è
      vuoto, il verdict è ridotto ad "indeterminate".
    - "not_compatible" è consentito solo in presenza di un conflitto esplicito
      fra valori dichiarati (es. richiesta first-line contro fonte
      post-progression/later-line, oppure setting dichiarati mutuamente
      esclusivi come "resected" contro "metastatic").
    - il verdict non viene mai reso più permissivo di quello ricevuto.
    """
    verdict: str = llm_verdict if llm_verdict in _VERDICT_RANK else "indeterminate"

    line_category = normalize_line_category(extracted_source_context.get("source_line_category"))
    setting_category = normalize_setting_category(extracted_source_context.get("source_setting_category"))
    prior_requirement = normalize_prior_therapy_requirement(
        extracted_source_context.get("source_prior_therapy_requirement")
    )

    patient_stage = declared_patient_context.get("disease_stage")
    patient_setting_raw = declared_patient_context.get("disease_setting")
    patient_prior_therapies = declared_patient_context.get("prior_therapies")
    patient_therapy_line = declared_patient_context.get("therapy_line")

    patient_setting = _normalized_patient_setting(patient_setting_raw)
    patient_line = _normalized_patient_line(patient_therapy_line)

    # Conflitto esplicito di linea: richiesta first-line dichiarata contro
    # fonte esclusivamente post-progressione/di linea successiva (o viceversa
    # una richiesta di linea successiva contro una fonte che richiede
    # esplicitamente pazienti mai trattati in precedenza).
    line_conflict = (
        (patient_line == "first_line" and line_category in _LATER_LINE_SOURCE_CATEGORIES)
        or (patient_line == "later_line" and line_category == "first_line" and prior_requirement == "treatment_naive")
    )

    # Conflitto esplicito di setting: stati di malattia dichiarati e
    # mutuamente esclusivi (es. paziente "resected" contro fonte
    # "metastatic"/"locally_advanced"/"recurrent", o viceversa).
    setting_conflict = (
        (patient_setting == "resected" and setting_category in _MUTUALLY_EXCLUSIVE_SETTINGS)
        or (setting_category == "resected" and patient_setting in _MUTUALLY_EXCLUSIVE_SETTINGS)
    )

    if line_conflict or setting_conflict:
        return _downgrade(verdict, "not_compatible")  # type: ignore[return-value]

    needs_indeterminate = False
    if setting_category != "unknown" and not _is_declared(patient_setting_raw):
        needs_indeterminate = True
    if setting_category in {"metastatic", "locally_advanced"} and not _is_declared(patient_stage):
        needs_indeterminate = True
    if prior_requirement != "unknown" and not _is_declared(patient_prior_therapies):
        needs_indeterminate = True

    if needs_indeterminate:
        return _downgrade(verdict, "indeterminate")  # type: ignore[return-value]

    return verdict  # type: ignore[return-value]
