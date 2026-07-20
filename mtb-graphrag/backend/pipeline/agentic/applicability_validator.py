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


def _force(final: str, forced_reason: str, original_verdict: str, original_reason: str) -> tuple[str, str]:
    """Impone ``final`` in modo incondizionato (non un cap di rango: un
    ``not_compatible`` del modello privo di giustificazione esplicita viene
    corretto qui anche se sarebbe già "più conservativo" del cap — un
    not_compatible non giustificato non è conservativo, è sbagliato). La
    motivazione cambia SOLO se il verdict cambia davvero rispetto
    all'originale — altrimenti la motivazione originale resta coerente."""
    return (final, forced_reason) if final != original_verdict else (final, original_reason)


def _evaluate_forced(
    extracted_source_context: dict[str, Any],
    declared_patient_context: dict[str, Any],
) -> tuple[str, str] | None:
    """Valuta le regole deterministiche condivise (conflitto esplicito o dati
    mancanti) sulla base delle sole categorie strutturate — mai su un verdict
    LLM. Restituisce ``(verdict_forzato, motivazione)`` quando una regola
    impone un esito, oppure ``None`` quando il contesto è pienamente noto e
    non in conflitto (nessuna forzatura necessaria: solo in questo caso un
    "compatible" è ammesso)."""
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
    if line_conflict:
        return "not_compatible", (
            "Conflitto esplicito di linea terapeutica: il caso dichiara la linea "
            f"'{patient_therapy_line}' mentre la fonte riguarda la categoria di linea "
            f"'{line_category}'; le due linee sono in conflitto esplicito."
        )

    # Conflitto esplicito di setting: stati di malattia dichiarati e
    # mutuamente esclusivi (es. paziente "resected" contro fonte
    # "metastatic"/"locally_advanced"/"recurrent", o viceversa).
    setting_conflict = (
        (patient_setting == "resected" and setting_category in _MUTUALLY_EXCLUSIVE_SETTINGS)
        or (setting_category == "resected" and patient_setting in _MUTUALLY_EXCLUSIVE_SETTINGS)
    )
    if setting_conflict:
        return "not_compatible", (
            "Conflitto esplicito di setting di malattia: il paziente è dichiarato "
            f"'{patient_setting_raw}' mentre la fonte riguarda la categoria di setting "
            f"'{setting_category}'; i due setting sono mutuamente esclusivi."
        )

    missing: list[str] = []
    # Una categoria sorgente mancante/"unknown" non permette mai un giudizio
    # positivo: senza sapere linea/setting/pre-trattamento della fonte non è
    # possibile confermare una corrispondenza esplicita col caso.
    if line_category == "unknown":
        missing.append("la categoria di linea della fonte non è determinabile")
    if setting_category == "unknown":
        missing.append("la categoria di setting della fonte non è determinabile")
    if prior_requirement == "unknown":
        missing.append("il requisito di pre-trattamento della fonte non è determinabile")
    if setting_category != "unknown" and not _is_declared(patient_setting_raw):
        missing.append("il setting del paziente non è dichiarato")
    if setting_category in {"metastatic", "locally_advanced"} and not _is_declared(patient_stage):
        missing.append("lo stadio del paziente non è dichiarato")
    if prior_requirement != "unknown" and not _is_declared(patient_prior_therapies):
        missing.append("i trattamenti precedenti del paziente non sono dichiarati")

    if missing:
        unique_missing = list(dict.fromkeys(missing))
        return "indeterminate", (
            "Dati insufficienti per confermare la compatibilità: " + "; ".join(unique_missing) + "."
        )

    return None


def derive_applicability(
    extracted_source_context: dict[str, Any],
    declared_patient_context: dict[str, Any],
) -> tuple[ApplicabilityStatus, str]:
    """Applicabilità puramente deterministica, senza alcun verdict LLM: fase
    B del percorso rapido (indipendente dalla chiamata LLM cacheable del
    profilo sorgente in fase A). Usa le stesse regole di ``validate_applicability``
    ma non richiede — né può ricevere — un giudizio del modello: se nessun
    conflitto o dato mancante impone un esito, il contesto è per costruzione
    pienamente noto e non in conflitto, quindi "compatible" è l'unico esito
    coerente."""
    forced = _evaluate_forced(extracted_source_context, declared_patient_context)
    if forced is not None:
        return forced  # type: ignore[return-value]
    return "compatible", "Setting, linea e pre-trattamento dichiarati coincidono esplicitamente con il contesto del caso."


def validate_applicability(
    extracted_source_context: dict[str, Any],
    declared_patient_context: dict[str, Any],
    llm_verdict: str,
    llm_reason: str = "",
) -> tuple[ApplicabilityStatus, str]:
    """Convalida/riduce il ``llm_verdict`` sulla base di categorie strutturate,
    e restituisce ``(verdict, reason)`` — la motivazione è sempre coerente con
    il verdict finale: se il verdict viene declassato, la motivazione originale
    dell'LLM (che può descrivere una corrispondenza che il validatore ha
    invece giudicato insufficiente o in conflitto) viene sostituita con una
    motivazione deterministica; se il verdict resta invariato, la motivazione
    originale è preservata.

    Regole (si applicano tutte; il risultato è il verdict più conservativo
    fra quello prodotto dall'LLM e quello imposto da ogni regola violata):

    - "compatible" è consentito SOLO quando le tre categorie strutturate della
      fonte (linea, setting, requisito di pre-trattamento) sono tutte note E i
      corrispondenti campi del paziente sono dichiarati e coincidono: una
      categoria della fonte mancante o "unknown" non permette mai di
      confermare "compatible", anche se l'unico dato disponibile (es.
      "first-line") coincide.
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
    - "not_compatible" richiede SEMPRE due valori esplicitamente dichiarati e
      in conflitto, rilevati qui dal validatore (es. richiesta first-line
      dichiarata contro fonte post-progression/later-line, oppure setting
      dichiarati mutuamente esclusivi come "resected" contro "metastatic").
      Un "not_compatible" del modello non corroborato da uno di questi
      conflitti espliciti NON viene mai preservato: se mancano dati non
      diventa "indeterminate" solo perché era "già conservativo" — un
      not_compatible ingiustificato è un errore da correggere, non un valore
      di sicurezza da mantenere. Fonte adiuvante/resected con setting del
      caso non dichiarato produce quindi sempre "indeterminate", mai
      "not_compatible" per l'assunzione implicita che first-line implichi
      malattia avanzata/non resecata.
    """
    original_verdict = llm_verdict if llm_verdict in _VERDICT_RANK else "indeterminate"
    original_reason = (
        llm_reason if llm_verdict in _VERDICT_RANK
        else "Verdict del modello non riconosciuto: trattato come indeterminato per default conservativo."
    )

    forced = _evaluate_forced(extracted_source_context, declared_patient_context)
    if forced is not None:
        final, forced_reason = forced
        return _force(final, forced_reason, original_verdict, original_reason)

    # Nessun conflitto esplicito rilevato dal validatore e nessun dato
    # mancante: un "not_compatible" del modello non confermato da uno dei
    # conflitti verificati sopra non è ammesso — "not_compatible" richiede
    # sempre due valori esplicitamente dichiarati e incompatibili.
    if original_verdict == "not_compatible":
        return "indeterminate", (
            "Il verdict 'not_compatible' del modello non corrisponde a un conflitto esplicito "
            "tra valori dichiarati rilevato dal validatore: applicabilità trattata come indeterminata."
        )

    return original_verdict, original_reason
