"""Risultato del retriever, warning codificati e spiegazione deterministica.

Un risultato che dica soltanto «rank 3, score 4.2» non e' verificabile: chi legge
non puo' sapere se il 4.2 viene da un match di malattia o da un bonus di setting
che nessuno ha confermato. Per questo lo score arriva sempre con il suo
breakdown, e ogni limite arriva sempre con un **codice**.

I codici servono a due cose diverse. Un test puo' cercarli senza dipendere dalla
prosa; e la prosa puo' cambiare senza rompere niente, perche' non e' la prosa a
portare l'informazione.

La spiegazione e' composta da frasi fisse selezionate dai codici. Non e' generata
da un modello: un testo generato sarebbe piu' scorrevole e non sarebbe
riproducibile, e qui la riproducibilita' vale piu' della scorrevolezza.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

RESULT_VERSION = "qualified_retrieval_result/1.0"

# --- destinazione del risultato -----------------------------------------------
BUCKET_RANKED = "ranked_results"
BUCKET_RETAINED_WITH_WARNING = "retained_with_warning"
BUCKET_AUDIT_ONLY = "audit_only_results"
BUCKET_REJECTED_NATIVE = "rejected_by_native_constraints"

RESULT_BUCKETS = (
    BUCKET_RANKED,
    BUCKET_RETAINED_WITH_WARNING,
    BUCKET_AUDIT_ONLY,
    BUCKET_REJECTED_NATIVE,
)

# --- codici di warning --------------------------------------------------------
# Ogni codice descrive un limite di lettura, non un difetto. Un warning non e' una
# ragione per escludere: e' la ragione per cui escludere sarebbe sbagliato senza
# averlo letto.
W_PRECLINICAL_ONLY = "preclinical_only_evidence"
W_CLINICAL_ONLY = "clinical_only_evidence_no_functional_validation"
W_ABSTRACT_ONLY_SOURCE = "abstract_only_source"
W_UNRESOLVED_UNIT = "unresolved_profile_unit"
W_NOT_SEPARABLE = "not_separable_composition"
W_CASE_LEVEL = "case_level_evidence"
W_NAMED_PATIENT_SUBSET = "named_patient_subset_evidence"
W_NO_FREQUENCY_INFERENCE = "frequency_inference_forbidden"
W_TERMINOLOGY_PENDING = "terminology_mapping_pending"
W_EVIDENCE_STRENGTH_MISMATCH = "evidence_strength_mismatch"
W_NEGATIVE_EXPERIMENT = "negative_experiment"
W_CANDIDATE_PARTIAL = "candidate_partial"
W_CANDIDATE_AMBIGUOUS = "candidate_ambiguous"
W_CANDIDATE_CONFLICTING = "candidate_conflicting"
W_CANDIDATE_INVALID = "candidate_invalid"
W_BIOMARKER_ROLE_MISSING = "biomarker_role_missing"
W_SOURCE_BASIS_LIMITATION = "source_basis_limitation"
W_QUALIFIER_UNREVIEWED = "qualifier_unreviewed"
W_QUALIFIER_MISMATCH_NOT_FILTERED = "qualifier_mismatch_observed_but_not_hard_filtered"
W_DISEASE_MISMATCH = "disease_mismatch"
W_INTERVENTION_MISMATCH = "intervention_mismatch"
W_PROTOTYPE_ONLY_QUALIFIERS = "prototype_only_qualifiers"

WARNING_CODES = (
    W_PRECLINICAL_ONLY,
    W_CLINICAL_ONLY,
    W_ABSTRACT_ONLY_SOURCE,
    W_UNRESOLVED_UNIT,
    W_NOT_SEPARABLE,
    W_CASE_LEVEL,
    W_NAMED_PATIENT_SUBSET,
    W_NO_FREQUENCY_INFERENCE,
    W_TERMINOLOGY_PENDING,
    W_EVIDENCE_STRENGTH_MISMATCH,
    W_NEGATIVE_EXPERIMENT,
    W_CANDIDATE_PARTIAL,
    W_CANDIDATE_AMBIGUOUS,
    W_CANDIDATE_CONFLICTING,
    W_CANDIDATE_INVALID,
    W_BIOMARKER_ROLE_MISSING,
    W_SOURCE_BASIS_LIMITATION,
    W_QUALIFIER_UNREVIEWED,
    W_QUALIFIER_MISMATCH_NOT_FILTERED,
    W_DISEASE_MISMATCH,
    W_INTERVENTION_MISMATCH,
    W_PROTOTYPE_ONLY_QUALIFIERS,
)

# I warning che tolgono un risultato dai principali. Sono due soltanto, e per la
# stessa ragione: dicono che la revisione ha giudicato il collegamento non
# sostenuto, non che la fonte sia debole.
AUDIT_ONLY_WARNINGS = (W_CANDIDATE_INVALID,)

# --- codici di esclusione nativa ----------------------------------------------
X_BIOMARKER_MISMATCH = "native_biomarker_mismatch"
X_ALTERATION_MISMATCH_WITH_MATCHING_GENE = (
    "ALTERATION_MISMATCH_WITH_MATCHING_GENE"
)
X_DISEASE_MISMATCH = "native_disease_mismatch"
X_DIRECTION_MISMATCH = "native_direction_mismatch"
X_POLARITY_MISMATCH = "native_assertion_polarity_mismatch"
X_SCOPE_MISMATCH = "native_evidence_scope_mismatch"
X_INTERVENTION_MISMATCH = "native_intervention_mismatch"

NATIVE_EXCLUSION_CODES = (
    X_BIOMARKER_MISMATCH,
    X_ALTERATION_MISMATCH_WITH_MATCHING_GENE,
    X_DISEASE_MISMATCH,
    X_DIRECTION_MISMATCH,
    X_POLARITY_MISMATCH,
    X_SCOPE_MISMATCH,
    X_INTERVENTION_MISMATCH,
)

# --- frasi ---------------------------------------------------------------------
# Una frase per codice. Cambiare la prosa non cambia il comportamento: il codice
# resta lo stesso, e i test cercano quello.
_SENTENCES: Mapping[str, str] = {
    W_PRECLINICAL_ONLY: (
        "Il supporto e' preclinico: descrive un modello, non un paziente."
    ),
    W_CLINICAL_ONLY: (
        "Il supporto e' clinico e questa fonte non porta validazione funzionale."
    ),
    W_ABSTRACT_ONLY_SOURCE: (
        "La fonte e' stata letta soltanto in abstract: la struttura dello studio "
        "resta parzialmente ricostruibile."
    ),
    W_UNRESOLVED_UNIT: (
        "L'unita' di profilo non e' risolta: non si sa a quale braccio o sistema "
        "il valore appartenga."
    ),
    W_NOT_SEPARABLE: (
        "La composizione interna della fonte non e' separabile: i componenti sono "
        "confermati, la loro relazione no."
    ),
    W_CASE_LEVEL: (
        "L'evidenza riguarda un singolo paziente e non e' una proprieta' della "
        "coorte."
    ),
    W_NAMED_PATIENT_SUBSET: (
        "L'evidenza riguarda pochi pazienti nominati e non e' una proprieta' della "
        "coorte."
    ),
    W_NO_FREQUENCY_INFERENCE: (
        "Nessuna frequenza puo' essere dedotta: manca un denominatore."
    ),
    W_TERMINOLOGY_PENDING: (
        "Il termine della fonte e quello dello statement non sono sinonimi "
        "verificati: il match e' debole."
    ),
    W_EVIDENCE_STRENGTH_MISMATCH: (
        "La forza dell'affermazione differisce da quella della fonte."
    ),
    W_NEGATIVE_EXPERIMENT: (
        "Il risultato e' negativo: la fonte argomenta contro la proposizione, non "
        "a favore."
    ),
    W_CANDIDATE_PARTIAL: (
        "La prima revisione ha giudicato il collegamento parziale."
    ),
    W_CANDIDATE_AMBIGUOUS: (
        "La prima revisione ha giudicato il collegamento ambiguo: la fonte dice "
        "meno di quanto lo statement affermi."
    ),
    W_CANDIDATE_CONFLICTING: (
        "Due fonti revisionate propongono valori diversi per la stessa dimensione."
    ),
    W_CANDIDATE_INVALID: (
        "La prima revisione ha giudicato il collegamento non sostenuto dalla fonte."
    ),
    W_BIOMARKER_ROLE_MISSING: (
        "Il ruolo del biomarcatore non e' dichiarato: requisito di arruolamento e "
        "reperto non sono distinguibili."
    ),
    W_SOURCE_BASIS_LIMITATION: (
        "La base documentale limita cio' che la fonte puo' sostenere."
    ),
    W_QUALIFIER_UNREVIEWED: (
        "I qualificatori di questa fonte non sono stati revisionati da nessuno."
    ),
    W_QUALIFIER_MISMATCH_NOT_FILTERED: (
        "Un qualificatore non corrisponde al contesto richiesto, e non e' stato "
        "usato per escludere perche' la sua eligibility e' prototype_only."
    ),
    W_DISEASE_MISMATCH: "La malattia della fonte differisce da quella della query.",
    W_INTERVENTION_MISMATCH: (
        "L'intervento della fonte differisce da quello richiesto."
    ),
    W_PROTOTYPE_ONLY_QUALIFIERS: (
        "I qualificatori vengono da una sola revisione, non indipendente: sono "
        "mostrati e non sono stati usati per filtrare."
    ),
}


def sentence_for(code: str) -> str:
    return _SENTENCES.get(code, "")


@dataclass(frozen=True)
class NativeExclusion:
    """Un candidato escluso da un vincolo nativo, con tutto il necessario per capire."""

    statement_id: str
    rule: str
    field_name: str
    query_value: Any
    statement_value: Any
    reason_code: str
    biomarker_match_mode: str = ""
    query_gene: str = ""
    query_alteration: str = ""
    statement_gene: str = ""
    statement_alteration: str = ""
    disease_match: Mapping[str, Any] = field(default_factory=dict)
    explanation_codes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "statement_id": self.statement_id,
            "rule": self.rule,
            "field": self.field_name,
            "query_value": self.query_value,
            "statement_value": self.statement_value,
            "reason_code": self.reason_code,
            "biomarker_match_mode": self.biomarker_match_mode,
            "query_gene": self.query_gene,
            "query_alteration": self.query_alteration,
            "statement_gene": self.statement_gene,
            "statement_alteration": self.statement_alteration,
            "disease_match": dict(self.disease_match),
            "explanation_codes": list(self.explanation_codes),
            "bucket": BUCKET_REJECTED_NATIVE,
        }


@dataclass(frozen=True)
class QualifiedRetrievalResult:
    """Un risultato, con il suo punteggio scomposto e i suoi limiti dichiarati."""

    query_id: str
    statement_id: str
    rank: int = 0
    total_score: float = 0.0
    native_score: float = 0.0
    qualified_score: float = 0.0
    score_breakdown: Sequence[Mapping[str, Any]] = ()
    graph_evidence_ids: tuple[str, ...] = ()
    disease_match: Mapping[str, Any] = field(default_factory=dict)
    native_matches: Mapping[str, Any] = field(default_factory=dict)
    qualified_matches: Mapping[str, Any] = field(default_factory=dict)
    mismatches: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    evidence_context: str = "unknown"
    support_type: str = ""
    candidate_link_status: str = ""
    assertion_polarity: str = ""
    direction: str = ""
    source_ids: tuple[str, ...] = ()
    active_profile_unit_ids: tuple[str, ...] = ()
    source_basis: str = "unknown"
    review_status: str = ""
    propagation_eligibility: str = ""
    hard_filterable: bool = False
    terminology_mappings: Sequence[Mapping[str, Any]] = ()
    unresolved_dimensions: tuple[str, ...] = ()
    case_level_information: Mapping[str, Any] = field(default_factory=dict)
    negative_evidence_information: Mapping[str, Any] = field(default_factory=dict)
    provenance_references: Sequence[Mapping[str, Any]] = ()
    explanation_codes: tuple[str, ...] = ()
    explanation: str = ""
    bucket: str = BUCKET_RANKED

    def as_dict(self) -> dict[str, Any]:
        return {
            "result_version": RESULT_VERSION,
            "query_id": self.query_id,
            "statement_id": self.statement_id,
            "graph_evidence_ids": list(self.graph_evidence_ids),
            "disease_match": dict(self.disease_match),
            "rank": self.rank,
            "total_score": round(self.total_score, 6),
            "native_score": round(self.native_score, 6),
            "qualified_score": round(self.qualified_score, 6),
            "score_breakdown": [dict(item) for item in self.score_breakdown],
            "native_matches": dict(self.native_matches),
            "qualified_matches": dict(self.qualified_matches),
            "mismatches": list(self.mismatches),
            "warnings": list(self.warnings),
            "evidence_context": self.evidence_context,
            "support_type": self.support_type,
            "candidate_link_status": self.candidate_link_status,
            "assertion_polarity": self.assertion_polarity,
            "direction": self.direction,
            "source_ids": list(self.source_ids),
            "active_profile_unit_ids": list(self.active_profile_unit_ids),
            "source_basis": self.source_basis,
            "review_status": self.review_status,
            "propagation_eligibility": self.propagation_eligibility,
            "hard_filterable": self.hard_filterable,
            "terminology_mappings": [dict(item) for item in self.terminology_mappings],
            "unresolved_dimensions": list(self.unresolved_dimensions),
            "case_level_information": dict(self.case_level_information),
            "negative_evidence_information": dict(self.negative_evidence_information),
            "provenance_references": [dict(item) for item in self.provenance_references],
            "explanation_codes": list(self.explanation_codes),
            "explanation": self.explanation,
            "bucket": self.bucket,
        }


def build_explanation(
    *,
    native_matches: Mapping[str, Any],
    warnings: Sequence[str],
    eligibility: str,
    evidence_context: str,
) -> tuple[tuple[str, ...], str]:
    """Codici e testo, entrambi deterministici.

    La prima frase dice sempre **perche' il risultato e' stato mantenuto**, e non
    e' un dettaglio di cortesia: un elenco di limiti senza la ragione della
    presenza si legge come un elenco di motivi per scartare.
    """
    matched = sorted(name for name, value in native_matches.items() if value)
    if matched:
        head = (
            "Evidenza mantenuta perche' "
            + " e ".join(_MATCH_LABELS.get(name, name) for name in matched)
            + " corrispondono."
        )
    else:
        head = (
            "Evidenza mantenuta come candidato: nessun vincolo nativo la esclude."
        )

    codes = tuple(dict.fromkeys(warnings))
    body = [sentence_for(code) for code in codes if sentence_for(code)]

    if eligibility == "prototype_only" and W_PROTOTYPE_ONLY_QUALIFIERS not in codes:
        body.append(sentence_for(W_PROTOTYPE_ONLY_QUALIFIERS))
        codes = codes + (W_PROTOTYPE_ONLY_QUALIFIERS,)

    return codes, " ".join([head, *body]).strip()


_MATCH_LABELS: Mapping[str, str] = {
    "biomarker": "il biomarcatore",
    "disease": "la malattia",
    "intervention": "l'intervento",
    "direction": "la direzione",
    "assertion_polarity": "la polarita'",
    "evidence_scope": "lo scope dell'evidenza",
}


__all__ = [
    "RESULT_VERSION",
    "RESULT_BUCKETS",
    "BUCKET_RANKED",
    "BUCKET_RETAINED_WITH_WARNING",
    "BUCKET_AUDIT_ONLY",
    "BUCKET_REJECTED_NATIVE",
    "WARNING_CODES",
    "AUDIT_ONLY_WARNINGS",
    "NATIVE_EXCLUSION_CODES",
    "W_PRECLINICAL_ONLY",
    "W_CLINICAL_ONLY",
    "W_ABSTRACT_ONLY_SOURCE",
    "W_UNRESOLVED_UNIT",
    "W_NOT_SEPARABLE",
    "W_CASE_LEVEL",
    "W_NAMED_PATIENT_SUBSET",
    "W_NO_FREQUENCY_INFERENCE",
    "W_TERMINOLOGY_PENDING",
    "W_EVIDENCE_STRENGTH_MISMATCH",
    "W_NEGATIVE_EXPERIMENT",
    "W_CANDIDATE_PARTIAL",
    "W_CANDIDATE_AMBIGUOUS",
    "W_CANDIDATE_CONFLICTING",
    "W_CANDIDATE_INVALID",
    "W_BIOMARKER_ROLE_MISSING",
    "W_SOURCE_BASIS_LIMITATION",
    "W_QUALIFIER_UNREVIEWED",
    "W_QUALIFIER_MISMATCH_NOT_FILTERED",
    "W_DISEASE_MISMATCH",
    "W_INTERVENTION_MISMATCH",
    "W_PROTOTYPE_ONLY_QUALIFIERS",
    "X_BIOMARKER_MISMATCH",
    "X_DISEASE_MISMATCH",
    "X_DIRECTION_MISMATCH",
    "X_POLARITY_MISMATCH",
    "X_SCOPE_MISMATCH",
    "X_INTERVENTION_MISMATCH",
    "NativeExclusion",
    "QualifiedRetrievalResult",
    "sentence_for",
    "build_explanation",
]
