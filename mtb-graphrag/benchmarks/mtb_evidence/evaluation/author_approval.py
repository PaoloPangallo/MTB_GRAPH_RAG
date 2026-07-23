"""Approvazione dell'autore sulla revisione documentale di PMID 31358542.

La decisione e' umana: l'ha presa Paolo Pangallo, autore della tesi, con
assistenza LLM nella preparazione documentale. Questo modulo la registra, non la
produce — ed e' la ragione per cui i suoi valori sono scritti a mano invece di
essere derivati da uno script.

Tre distinzioni che il modulo tiene separate perche' collassarle renderebbe il
corpus non verificabile:

- `human_reviewed` non e' `clinical_reviewed`. L'autore non e' un clinico, e una
  prima revisione non clinica non puo' valere come validazione clinica.
- `first_review_complete` non e' `independent_review`. Chi ha approvato ha letto
  materiale preparato con assistenza LLM: la seconda revisione serve proprio
  perche' la prima non e' indipendente.
- una revisione completata non e' gold valutabile. `is_evaluable` resta falso
  finche' esiste una sola annotazione.

La revisione ha **respinto** lo split proposto. Il risultato e' una sola unita'
clinica, e la parola «split» non descrive l'esito: descrive la proposta che e'
stata respinta.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

APPROVAL_VERSION = "author_approval/1.0"

# --- identita' e metodo della revisione ---------------------------------------
REVIEWER_ID = "paolo_pangallo"
REVIEWER_ROLE = "thesis_author_non_clinical"
REVIEW_METHOD = "human_approved_llm_assisted_source_review"

# --- decisioni dell'autore ----------------------------------------------------
APPROVE = "approve"
APPROVE_WITH_CORRECTIONS = "approve_with_corrections"
REJECT = "reject"
DEFER_TO_CLINICAL_REVIEWER = "defer_to_clinical_reviewer"
INSUFFICIENT_INFORMATION = "insufficient_information"

AUTHOR_DECISIONS = (
    APPROVE,
    APPROVE_WITH_CORRECTIONS,
    REJECT,
    DEFER_TO_CLINICAL_REVIEWER,
    INSUFFICIENT_INFORMATION,
)

# Stati che nessun percorso di questa fase puo' dichiarare. Elencarli permette a
# un test di cercarli invece di fidarsi che non compaiano.
FORBIDDEN_STATUSES = (
    "clinical_review_complete",
    "independent_review",
    "second_review_complete",
    "adjudicated",
    "frozen",
    "final_gold",
)

# --- caso di riferimento del rilevatore ---------------------------------------
CITATION_CONTEXT_FALSE_POSITIVE = "citation_context_false_positive"

# Il principio che il caso stabilisce, in forma citabile. Non riguarda questa
# fonte: riguarda qualunque rilevatore che confonda la presenza di un termine con
# la produzione dell'evidenza che quel termine nomina.
DETECTOR_PRINCIPLE = "term_present_in_document != evidence_generated_by_current_study"


@dataclass(frozen=True)
class StatementRevision:
    """La decisione di prima revisione su un singolo statement."""

    statement_id: str
    previous_candidate_status: str
    first_review_status: str
    link_status: str
    supported_dimensions: tuple[str, ...]
    unsupported_dimensions: tuple[str, ...]
    rationale: str
    invalid_reason: str = ""
    source_claim_scope: str = ""
    statement_claim_scope: str = ""
    intervention_attribution: str = ""
    extra: Mapping[str, Any] | None = None


# =============================================================================
# La decisione
# =============================================================================

SOURCE_PMID = "31358542"
SOURCE_PMC = "PMC6858956"
CANONICAL_SOURCE_ID = "PMID:31358542"
PARENT_UNIT_ID = "PU-PMID-31358542-cohort-1"
APPROVED_UNIT_ID = "PU-PMID-31358542-clinical-cohort"

AUTHOR_DECISION = APPROVE_WITH_CORRECTIONS
STRUCTURAL_DECISION = "audit_split_not_supported"
CLINICAL_PRECLINICAL_SPLIT = "rejected"
FINAL_NUMBER_OF_PROFILE_UNITS = 1

DECISION_RATIONALE = (
    "La pubblicazione non contiene esperimenti preclinici prodotti dagli autori. "
    "L'unica occorrenza di «in vitro» descrive uno studio citato e non un "
    "esperimento della fonte corrente. La fonte e' registrata come caso "
    "interamente clinico."
)

# --- struttura dei sottogruppi ------------------------------------------------
# Otto sottopopolazioni esistono, e nessuna diventa una unita'. Sono analisi
# sovrapposte della stessa coorte: creare otto unita' moltiplicherebbe lo stesso
# denominatore per otto, e ciascuna sembrerebbe una coorte indipendente.
SUBGROUP_STRUCTURE: Mapping[str, Any] = {
    "analyzed_subgroups_count": 8,
    "subgroup_overlap": True,
    "requires_subgroup_unit_split": False,
    "subgroup_specific_results_globally_propagatable": False,
    "intervention_attribution": "not_separable",
    "rationale": (
        "le sottopopolazioni sono analisi sovrapposte della stessa coorte e non "
        "costituiscono necessariamente coorti indipendenti"
    ),
    "future_split_conditions": (
        "uno statement riguarda esplicitamente un singolo sottogruppo",
        "denominatore e intervento sono separabili",
        "il risultato e' subgroup-specific",
        "la propagazione globale produrrebbe un errore",
    ),
}

# --- campi clinici ------------------------------------------------------------
# Restano ignoti quelli che la fonte non sostiene. Inventarli sarebbe il modo
# piu' rapido di rendere il profilo utilizzabile e sbagliato.
UNKNOWN_FIELDS = (
    "comparator",
    "exclusion_criteria",
    "inclusion_criteria",
    "prior_therapies",
    "regimen",
    "resection_status",
    "setting",
    "stage",
)
NOT_SEPARABLE_FIELDS = ("intervention",)

# --- revisioni degli statement ------------------------------------------------

REVISION_100003 = StatementRevision(
    statement_id="ES-V2-evidence-100003",
    previous_candidate_status="candidate_ambiguous",
    first_review_status="candidate_invalid",
    link_status="invalid_link",
    supported_dimensions=("disease", "biomarker"),
    unsupported_dimensions=("intervention",),
    invalid_reason="aggregate_to_specific_intervention_attribution",
    source_claim_scope="second_generation_alk_tki_class",
    statement_claim_scope="brigatinib",
    intervention_attribution="unsupported_by_this_source",
    rationale=(
        "la fonte riporta la frequenza di G1202R per la classe dei TKI ALK di "
        "seconda generazione; lo statement la attribuisce specificamente a "
        "brigatinib. Non e' `not_determinable`: il full text e' disponibile e la "
        "mancata attribuzione specifica e' verificabile"
    ),
    extra={
        "direct_clinical_support": "false_for_drug_specific_claim",
        "epistemic_note": (
            "lo statement potrebbe essere sostenuto da un'altra fonte; PMID 31358542 "
            "non sostiene la formulazione specifica attribuita a brigatinib"
        ),
    },
)

REVISION_100004 = StatementRevision(
    statement_id="ES-V2-evidence-100004",
    previous_candidate_status="candidate_partial",
    first_review_status="candidate_partial",
    link_status="partial_link",
    supported_dimensions=("disease", "ALK rearrangement", "clinical resistance context"),
    unsupported_dimensions=(
        "individual intervention attribution",
        "exact subgroup denominator",
        "drug-specific frequency",
    ),
    intervention_attribution="not_separable",
    rationale=(
        "la fonte sostiene il contesto clinico generale, ma non permette di "
        "attribuire in modo sicuro il risultato aggregato a uno specifico farmaco "
        "o sottogruppo. Un risultato di classe non si propaga a un farmaco singolo"
    ),
)

STATEMENT_REVISIONS = (REVISION_100003, REVISION_100004)

# --- caso di riferimento ------------------------------------------------------
DETECTOR_REFERENCE_CASE: Mapping[str, Any] = {
    "detector_reference_case": True,
    "reference_case_type": CITATION_CONTEXT_FALSE_POSITIVE,
    "detector_original_verdict": "split_required",
    "reviewed_verdict": "split_not_supported",
    "reference_case_status": "first_review_confirmed",
    "use_as_regression_case": True,
    "use_for_detector_performance_estimation": False,
    "principle": DETECTOR_PRINCIPLE,
    "section": "Discussion",
    "sentence": (
        "Based on in vitro models, a G1269A/I1171S compound mutation may "
        "re-sensitize to ceritinib or brigatinib."
    ),
    "bibliographic_reference": "riferimento 23 della pubblicazione",
    "citation_context": (
        "la frase attribuisce il reperto a «in vitro models» di un lavoro citato, "
        "non a un esperimento della fonte corrente"
    ),
    "own_preclinical_methods_present": False,
    "own_preclinical_figures_present": False,
    "own_preclinical_results_present": False,
    "matched_signal_id": "preclinical.in_vitro",
    "matched_signal_occurrences": 1,
    "rationale": (
        "la presenza lessicale di «in vitro» derivava da una citazione di un lavoro "
        "precedente. Un solo caso non misura il rilevatore, ma mostra un modo di "
        "sbagliare che nessuna soglia corregge"
    ),
}

LIMITATIONS = (
    "la revisione e' documentale e non clinica: l'autore non e' un clinico",
    "la preparazione del materiale e' assistita da LLM, quindi la prima revisione "
    "non e' indipendente",
    "un solo caso non permette di stimare precision, recall o accuratezza del "
    "rilevatore",
    "il rischio residuo della fonte resta di sottogruppo e non e' stato risolto",
)
