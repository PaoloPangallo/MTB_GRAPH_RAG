"""Contratto dei claim non terapeutici e identita' versionata.

La migrazione shadow ha lasciato tre record senza claim perche' la tassonomia
aveva soltanto tipi di intervento: `evidence:347`, `evidence:1846`,
`evidence:1847` non portano una terapia e nessuno dei tre tipi terapeutici
poteva ospitarli. Questa fase decide cosa siano, e per farlo estende la gerarchia
invece di forzare i record dentro un tipo che non li descrive.

Il contratto e' dichiarativo. Nessun claim non terapeutico viene materializzato
nel repository shadow operativo: qui si definisce cosa sarebbe un
`DiagnosticClaim` o un `PrognosticClaim`, si simula la loro identita' e si
riconcilia il conteggio. L'implementazione e' la fase successiva.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

CONTRACT_VERSION = "non-therapeutic-claim-contract/1.0"
ERRATUM_VERSION = "adjudication_erratum/1.0"
AMENDED_SPEC_VERSION = "migration_specification_amended/1.1"
CLAIM_ID_FORMULA_VERSION = "non_therapeutic_claim_id_formula/1.0"

FIELD_SEPARATOR = "|"
CLAIM_ID_PREFIX = "CLM-"
ID_HEX_LENGTH = 20


class ContractError(RuntimeError):
    """Il contratto e' stato violato o interrogato con dati incoerenti."""


# ── gerarchia ─────────────────────────────────────────────────────────────────
#
# `EvidenceClaim` e' la radice astratta: tutto cio' che afferma qualcosa su un
# biomarcatore in un contesto di malattia, con provenienza documentale. I tre
# tipi terapeutici restano dove sono, sotto `TherapeuticClaim`, che e' il nodo
# che porta l'intervento. Diagnostico e prognostico sono fratelli di
# `TherapeuticClaim`, non suoi sottotipi: non hanno intervento, e metterli sotto
# un nodo che lo richiede costringerebbe a inventarlo.

EVIDENCE_CLAIM_HIERARCHY: dict[str, Any] = {
    "EvidenceClaim": {
        "abstract": True,
        "is_claim": True,
        "requires": [
            "claim_id",
            "parent_id",
            "biomarker_or_subject",
            "disease_scope",
            "polarity",
            "source_unit_ids",
            "locators",
            "provenance",
        ],
        "children": {
            "TherapeuticClaim": {
                "abstract": True,
                "requires_intervention": True,
                "receives_therapy_score": True,
                "counted_in_therapy_metrics": True,
                "children": {
                    "AtomicInterventionClaim": {"abstract": False},
                    "AggregateInterventionClaim": {"abstract": False},
                    "RegimenClaim": {"abstract": False},
                },
            },
            "DiagnosticClaim": {
                "abstract": False,
                "requires_intervention": False,
                "receives_therapy_score": False,
                "counted_in_therapy_metrics": False,
                "children": {},
            },
            "PrognosticClaim": {
                "abstract": False,
                "requires_intervention": False,
                "receives_therapy_score": False,
                "counted_in_therapy_metrics": False,
                "children": {},
            },
        },
    }
}

# Oggetti che non sono claim positivi e non entrano nella gerarchia sopra.
NON_CLAIM_OBJECT_KINDS = (
    "graph_evidence_record",
    "unsupported_association",
    "unresolved_association",
)

THERAPEUTIC_CLAIM_TYPES = (
    "atomic_intervention_claim",
    "aggregate_intervention_claim",
    "regimen_claim",
)

NON_THERAPEUTIC_CLAIM_TYPES = ("diagnostic_claim", "prognostic_claim")

ALL_CLAIM_TYPES = THERAPEUTIC_CLAIM_TYPES + NON_THERAPEUTIC_CLAIM_TYPES


# ── PredictiveClaim: valutato, non introdotto ─────────────────────────────────

PREDICTIVE_CLAIM_ASSESSMENT: dict[str, Any] = {
    "required": False,
    "concrete_case_in_corpus": False,
    "nearest_case": "evidence:347",
    "why_the_nearest_case_does_not_qualify": (
        "La fonte di evidence:347 e' davvero un'analisi predittiva — misura se "
        "l'effetto di cetuximab sia modulato dallo stato mutazionale di EGFR — ma il "
        "record del grafo non porta alcun intervento. Materializzarlo come claim "
        "predittivo richiederebbe di attribuirgli cetuximab, cioe' inventare "
        "l'intervento che tutta questa linea di lavoro esiste per non inventare. "
        "Il caso e' vicino e non utilizzabile."
    ),
    "why_the_type_would_be_redundant": (
        "Un claim predittivo e' un'affermazione su un biomarcatore che modula "
        "l'effetto di un intervento, e nel modello attuale si scrive gia': e' un "
        "TherapeuticClaim con `direction` sensitivity o resistance. Introdurre "
        "PredictiveClaim come fratello creerebbe due modi di dire la stessa cosa, e "
        "due modi di dire la stessa cosa diventano due denominatori diversi."
    ),
    "reconsider_when": (
        "Un record porta un intervento documentato e la fonte riporta una "
        "modificazione dell'effetto per stato del biomarcatore, senza che il "
        "risultato sia esprimibile come direzione di sensibilita' o resistenza."
    ),
}


# ── contratto DiagnosticClaim ─────────────────────────────────────────────────

DIAGNOSTIC_CLAIM_FIELDS = (
    "claim_id",
    "parent_id",
    "claim_type",
    "diagnostic_subject",
    "biomarker",
    "disease_scope",
    "diagnostic_interpretation",
    "assay_or_method",
    "population_or_sample_scope",
    "direction",
    "polarity",
    "source_unit_ids",
    "locators",
    "qualification_link_ids",
    "review_status",
    "provenance",
    "legacy_statement_ids",
    "deprecated",
    "schema_version",
)

DIAGNOSTIC_INTERPRETATIONS = (
    "subtype_defining_alteration",
    "disease_associated_marker",
    "differential_diagnosis_support",
    "diagnostic_exclusion",
    "unknown",
)

# Tre inferenze che il contratto vieta esplicitamente, perche' sono i tre modi
# in cui un'osservazione diventa silenziosamente un test clinico.
DIAGNOSTIC_FORBIDDEN_INFERENCES = {
    "disease_association_to_diagnostic_utility": (
        "Un'associazione con una malattia non e' utilita' diagnostica: dice che "
        "l'alterazione si trova in quel tumore, non che serva a diagnosticarlo."
    ),
    "observed_biomarker_to_validated_test": (
        "Un biomarcatore osservato non e' un test clinicamente validato: la "
        "validazione e' un'affermazione sulla performance, che la fonte deve fare."
    ),
    "experimental_assay_to_approved_procedure": (
        "Un assay sperimentale non e' una procedura diagnostica approvata: il "
        "metodo con cui si e' misurato non e' il metodo con cui si diagnostica."
    ),
}

DIAGNOSTIC_CLAIM_CONTRACT: dict[str, Any] = {
    "claim_type": "diagnostic_claim",
    "contract_version": CONTRACT_VERSION,
    "parent_class": "EvidenceClaim",
    "requires_intervention": False,
    "intervention_field_present": False,
    "required_fields": list(DIAGNOSTIC_CLAIM_FIELDS),
    "diagnostic_interpretations": list(DIAGNOSTIC_INTERPRETATIONS),
    "forbidden_inferences": DIAGNOSTIC_FORBIDDEN_INFERENCES,
    "direction_semantics": (
        "`direction` non e' una direzione terapeutica. Per un claim diagnostico "
        "vale `diagnostic` e il contenuto informativo sta in "
        "`diagnostic_interpretation`."
    ),
    "receives_therapy_score": False,
    "counted_in_therapy_level_metrics": False,
    "flattened_into_intervention": False,
    "comparable_with_regimen_or_class": False,
}


# ── contratto PrognosticClaim ─────────────────────────────────────────────────

PROGNOSTIC_CLAIM_FIELDS = (
    "claim_id",
    "parent_id",
    "claim_type",
    "prognostic_subject",
    "biomarker",
    "disease_scope",
    "outcome",
    "direction",
    "polarity",
    "population_scope",
    "source_unit_ids",
    "locators",
    "qualification_link_ids",
    "review_status",
    "provenance",
    "legacy_statement_ids",
    "deprecated",
    "schema_version",
)

PROGNOSTIC_DIRECTIONS = (
    "better_outcome",
    "poor_outcome",
    "no_association",
    "unknown",
)

PROGNOSTIC_FORBIDDEN_INFERENCES = {
    "observational_association_to_causality": (
        "Un'associazione osservazionale non e' una relazione causale: il disegno "
        "che la produce non puo' stabilirla."
    ),
    "prognostic_to_predictive": (
        "Un'associazione prognostica non e' un effetto predittivo del trattamento: "
        "la prima descrive come va il paziente, la seconda come risponde alla "
        "terapia, e confonderle e' il modo piu' diretto di attribuire a un farmaco "
        "un beneficio che nessuno ha misurato."
    ),
    "correlation_to_clinical_utility": (
        "Una correlazione non e' utilita' clinica: perche' lo diventi serve che "
        "cambi una decisione, e che qualcuno lo abbia mostrato."
    ),
    "generic_outcome_to_survival_benefit": (
        "Un esito generico non e' un beneficio di sopravvivenza specifico: "
        "l'endpoint va conservato come la fonte lo nomina."
    ),
}

PROGNOSTIC_CLAIM_CONTRACT: dict[str, Any] = {
    "claim_type": "prognostic_claim",
    "contract_version": CONTRACT_VERSION,
    "parent_class": "EvidenceClaim",
    "requires_intervention": False,
    "intervention_field_present": False,
    "required_fields": list(PROGNOSTIC_CLAIM_FIELDS),
    "directions": list(PROGNOSTIC_DIRECTIONS),
    "forbidden_inferences": PROGNOSTIC_FORBIDDEN_INFERENCES,
    "outcome_semantics": (
        "`outcome` conserva l'endpoint come la fonte lo nomina. Un endpoint "
        "normalizzato a 'survival' quando la fonte diceva 'recurrence-free "
        "survival' e' un endpoint diverso."
    ),
    "receives_therapy_score": False,
    "counted_in_therapy_level_metrics": False,
    "flattened_into_intervention": False,
    "comparable_with_regimen_or_class": False,
}


# ── requisiti minimi di materializzazione ─────────────────────────────────────

REQUIRED_FOR_ANY_APPROVED_CLAIM = (
    "source_id",
    "subject",
    "disease_scope",
    "direction_or_interpretation",
    "source_unit_id",
    "locators",
    "polarity",
    "provenance",
)


def check_materialisation_preconditions(candidate: Mapping[str, Any]) -> tuple[str, ...]:
    """Campi mancanti perche' un claim possa essere approvato. Vuoto = completo."""
    missing = []
    for field in REQUIRED_FOR_ANY_APPROVED_CLAIM:
        value = candidate.get(field)
        if value in (None, "", (), []):
            missing.append(field)
    return tuple(missing)


# ── verdetti dell'audit ───────────────────────────────────────────────────────

AUDIT_VERDICTS = (
    "diagnostic_claim_supported",
    "prognostic_claim_supported",
    "diagnostic_and_prognostic_claims_supported",
    "non_therapeutic_claim_unresolved",
    "metadata_only_not_claim",
    "insufficient_source_support",
)

VERDICT_PRODUCES_CLAIMS = {
    "diagnostic_claim_supported": ("diagnostic_claim",),
    "prognostic_claim_supported": ("prognostic_claim",),
    "diagnostic_and_prognostic_claims_supported": ("diagnostic_claim", "prognostic_claim"),
    "non_therapeutic_claim_unresolved": (),
    "metadata_only_not_claim": (),
    "insufficient_source_support": (),
}


def claims_for_verdict(verdict: str) -> tuple[str, ...]:
    if verdict not in AUDIT_VERDICTS:
        raise ContractError(f"verdetto sconosciuto: {verdict}")
    return VERDICT_PRODUCES_CLAIMS[verdict]


# ── tipi di query ─────────────────────────────────────────────────────────────

QUERY_TYPES = (
    "diagnostic_evidence_query",
    "prognostic_evidence_query",
    "therapeutic_evidence_query",
    "untyped_evidence_query",
)

# Quale tipo di claim ogni tipo di query puo' portare in primario. La matrice e'
# esplicita perche' l'errore che previene — una query diagnostica che recupera un
# claim terapeutico come se fosse diagnostico — e' un errore di categoria, e gli
# errori di categoria non si vedono guardando i punteggi.
QUERY_TYPE_PRIMARY_ELIGIBILITY: dict[str, dict[str, bool]] = {
    "diagnostic_evidence_query": {
        "diagnostic_claim": True,
        "prognostic_claim": False,
        "atomic_intervention_claim": False,
        "aggregate_intervention_claim": False,
        "regimen_claim": False,
    },
    "prognostic_evidence_query": {
        "diagnostic_claim": False,
        "prognostic_claim": True,
        "atomic_intervention_claim": False,
        "aggregate_intervention_claim": False,
        "regimen_claim": False,
    },
    "therapeutic_evidence_query": {
        "diagnostic_claim": False,
        "prognostic_claim": False,
        "atomic_intervention_claim": True,
        "aggregate_intervention_claim": True,
        "regimen_claim": True,
    },
    "untyped_evidence_query": {
        "diagnostic_claim": True,
        "prognostic_claim": True,
        "atomic_intervention_claim": True,
        "aggregate_intervention_claim": True,
        "regimen_claim": True,
    },
}

# La query senza tipo puo' recuperare piu' tipi, ma non li mescola: ogni tipo ha
# la propria sezione, e i risultati non competono fra sezioni.
UNTYPED_QUERY_SECTIONING = {
    "sections_are_separate": True,
    "buckets_are_per_section": True,
    "cross_type_ranking": False,
    "sections": ["therapeutic", "diagnostic", "prognostic"],
}

REJECTION_REASON_CODES = (
    "CLAIM_TYPE_NOT_ELIGIBLE_FOR_QUERY_TYPE",
    "THERAPEUTIC_CLAIM_NOT_DIAGNOSTIC_EVIDENCE",
    "THERAPEUTIC_CLAIM_NOT_PROGNOSTIC_EVIDENCE",
    "PROGNOSTIC_CLAIM_NOT_PREDICTIVE_EVIDENCE",
    "DIAGNOSTIC_CLAIM_NOT_THERAPEUTIC_EVIDENCE",
    "NON_THERAPEUTIC_CLAIM_HAS_NO_INTERVENTION_TO_MATCH",
)


def primary_eligible(query_type: str, claim_type: str) -> bool:
    """Idoneita' primaria per coppia (tipo query, tipo claim). Nessun punteggio."""
    if query_type not in QUERY_TYPES:
        raise ContractError(f"tipo di query sconosciuto: {query_type}")
    if claim_type not in ALL_CLAIM_TYPES:
        raise ContractError(f"tipo di claim sconosciuto: {claim_type}")
    return QUERY_TYPE_PRIMARY_ELIGIBILITY[query_type][claim_type]


def rejection_reason(query_type: str, claim_type: str) -> str | None:
    """Perche' quella coppia non e' primaria, quando non lo e'."""
    if primary_eligible(query_type, claim_type):
        return None
    if query_type == "diagnostic_evidence_query" and claim_type in THERAPEUTIC_CLAIM_TYPES:
        return "THERAPEUTIC_CLAIM_NOT_DIAGNOSTIC_EVIDENCE"
    if query_type == "prognostic_evidence_query" and claim_type in THERAPEUTIC_CLAIM_TYPES:
        return "THERAPEUTIC_CLAIM_NOT_PROGNOSTIC_EVIDENCE"
    if query_type == "therapeutic_evidence_query" and claim_type in NON_THERAPEUTIC_CLAIM_TYPES:
        return "DIAGNOSTIC_CLAIM_NOT_THERAPEUTIC_EVIDENCE"
    if query_type == "prognostic_evidence_query" and claim_type == "diagnostic_claim":
        return "CLAIM_TYPE_NOT_ELIGIBLE_FOR_QUERY_TYPE"
    return "CLAIM_TYPE_NOT_ELIGIBLE_FOR_QUERY_TYPE"


# ── scoring scope ─────────────────────────────────────────────────────────────

SCORE_ELIGIBILITY_CONTRACT: dict[str, Any] = {
    "contract_version": CONTRACT_VERSION,
    "weights_assigned": False,
    "note": (
        "Il contratto e' strutturale. Nessun peso viene assegnato qui: assegnarli "
        "prima che i tipi siano stabili produrrebbe una taratura su una tassonomia "
        "che sta ancora cambiando."
    ),
    "by_claim_type": {
        "diagnostic_claim": {
            "primary_eligible_for": ["diagnostic_evidence_query", "untyped_evidence_query"],
            "primary_conditions": [
                "biomarker_or_subject_compatible",
                "disease_compatible",
                "diagnostic_role_supported_by_source",
            ],
            "receives_therapy_score": False,
            "enters_therapy_level_metrics": False,
            "flattened_into_intervention": False,
            "compared_with_regimen_or_class": False,
        },
        "prognostic_claim": {
            "primary_eligible_for": ["prognostic_evidence_query", "untyped_evidence_query"],
            "primary_conditions": [
                "biomarker_compatible",
                "disease_compatible",
                "outcome_and_direction_compatible",
            ],
            "receives_therapy_score": False,
            "enters_therapy_level_metrics": False,
            "flattened_into_intervention": False,
            "compared_with_regimen_or_class": False,
        },
    },
    "shared_invariants": [
        "un claim non terapeutico non riceve therapy score",
        "un claim non terapeutico non entra nelle metriche therapy-level",
        "un claim non terapeutico non viene appiattito in `intervention`",
        "un claim non terapeutico non viene confrontato con regimi o classi",
    ],
}


# ── metriche ──────────────────────────────────────────────────────────────────

METRIC_SCOPE_CONTRACT: dict[str, Any] = {
    "contract_version": CONTRACT_VERSION,
    "metrics_computed_in_this_phase": False,
    "families": {
        "therapeutic_claim_metrics": {
            "denominator_includes": list(THERAPEUTIC_CLAIM_TYPES),
            "denominator_excludes": list(NON_THERAPEUTIC_CLAIM_TYPES) + list(NON_CLAIM_OBJECT_KINDS),
        },
        "diagnostic_claim_metrics": {
            "denominator_includes": ["diagnostic_claim"],
            "denominator_excludes": list(THERAPEUTIC_CLAIM_TYPES) + ["prognostic_claim"],
        },
        "prognostic_claim_metrics": {
            "denominator_includes": ["prognostic_claim"],
            "denominator_excludes": list(THERAPEUTIC_CLAIM_TYPES) + ["diagnostic_claim"],
        },
        "source_provenance_metrics": {
            "denominator_includes": ["graph_evidence_record"],
            "denominator_excludes": list(ALL_CLAIM_TYPES),
        },
        "structural_coverage": {
            "denominator_includes": list(ALL_CLAIM_TYPES) + list(NON_CLAIM_OBJECT_KINDS),
            "denominator_excludes": [],
            "note": (
                "E' l'unica famiglia che guarda tutto insieme, e serve a misurare "
                "la copertura del modello, non la qualita' clinica."
            ),
        },
    },
    "cross_family_comparison_allowed": False,
    "corpus_version_label_required": True,
}


# ── identita' dei claim non terapeutici ───────────────────────────────────────


def _require(name: str, value: Any) -> str:
    if value is None:
        raise ContractError(f"campo di identita' assente: {name}")
    text = str(value)
    if not text.strip():
        raise ContractError(f"campo di identita' vuoto: {name}")
    if FIELD_SEPARATOR in text:
        raise ContractError(
            f"il campo {name} contiene il separatore {FIELD_SEPARATOR!r}"
        )
    return text


NON_THERAPEUTIC_IDENTITY_FIELDS = (
    "graph_evidence_id",
    "claim_type",
    "canonical_subject",
    "biomarker",
    "disease_scope",
    "direction_or_interpretation",
    "polarity",
    "source_unit_id",
)


def identity_payload(
    *,
    graph_evidence_id: str,
    claim_type: str,
    canonical_subject: str,
    biomarker: str,
    disease_scope: str,
    direction_or_interpretation: str,
    polarity: str,
    source_unit_id: str,
) -> str:
    """Serializzazione canonica dell'identita' di un claim non terapeutico.

    La formula ha otto campi e non sette: rispetto a quella terapeutica sparisce
    `canonical_intervention_or_regimen` — non c'e' intervento da mettere, e
    metterci un segnaposto creerebbe un campo artificiale — e compaiono
    `canonical_subject` e `disease_scope`, che per un claim diagnostico o
    prognostico portano l'informazione che li distingue.
    """
    return FIELD_SEPARATOR.join(
        _require(name, value)
        for name, value in (
            ("graph_evidence_id", graph_evidence_id),
            ("claim_type", claim_type),
            ("canonical_subject", canonical_subject),
            ("biomarker", biomarker),
            ("disease_scope", disease_scope),
            ("direction_or_interpretation", direction_or_interpretation),
            ("polarity", polarity),
            ("source_unit_id", source_unit_id),
        )
    )


def claim_identity_sha256(**kwargs: str) -> str:
    return hashlib.sha256(identity_payload(**kwargs).encode("utf-8")).hexdigest()


def claim_id(**kwargs: str) -> str:
    return CLAIM_ID_PREFIX + claim_identity_sha256(**kwargs)[:ID_HEX_LENGTH]


def canonical_subject(label: str) -> str:
    """Forma canonica del soggetto. Nessuna sostituzione di sinonimi."""
    return " ".join(str(label or "").split()).lower()
