"""Approvazione dell'autore sulla revisione documentale di PMID 23344087.

Terza e ultima fonte del batch clinico/preclinico. Come le due precedenti, la
decisione e' umana: l'ha presa Paolo Pangallo, autore della tesi, con assistenza
LLM nella preparazione documentale. Identita' del revisore e stati proibiti
vengono da `author_approval`, la granularita' da `evidence_granularity`: la
regola sui casi singoli e' stata scritta per PMID 22235099 e qui viene **riusata**,
non riscritta.

Cio' che distingue questa fonte dalle altre due e' quanto documento esiste. Il
full text e' dichiarato «Subscription required» da Europe PMC: non e' in PMC, non
e' open access, non c'e' via pubblica di accesso. La revisione ha letto 1683
caratteri di abstract e sei locator, tutti `exact`.

Da qui discendono tre cose che non vanno confuse fra loro:

- lo split clinico/preclinico e' **confermato**. L'abstract nomina esplicitamente
  sia i sette pazienti sia gli esperimenti in vitro, e nomina entrambi come
  lavoro proprio;
- la **composizione** della parte preclinica non lo e'. SNU-2535, H3122 CR1 e i
  cloni mutanti esistono tutti nell'abstract; la loro relazione no. Il fondo
  cellulare dei cloni non e' scritto da nessuna parte;
- quindi le tre unita' proposte non diventano tre unita' attive. Due delle tre
  proposte descrivevano una struttura che l'abstract non risolve, e attivarle
  avrebbe registrato come letto qualcosa che nessuno ha letto.

`not_separable` e non `unknown`. La differenza porta informazione: `unknown`
direbbe che il valore forse esiste e va cercato, `not_separable` dice che i
componenti sono confermati e la loro relazione non e' ricostruibile dal documento
disponibile.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from backend.pipeline.evidence.evidence_granularity import (
    GRANULARITY_CASE,
    GRANULARITY_COHORT,
    SCOPE_SINGLE_PATIENT,
    constraints_for,
)
from backend.pipeline.evidence.profile_unit import (
    UNIT_TYPE_CLINICAL_COHORT,
    UNIT_TYPE_PRECLINICAL,
)
from backend.pipeline.evidence.source_basis import (
    ABSTRACT_ONLY,
    CONFIDENCE_PARTIAL,
    NOT_SEPARABLE,
    constraints_for_basis,
)
from benchmarks.mtb_evidence.evaluation.author_approval import (
    APPROVE_WITH_CORRECTIONS,
    AUTHOR_DECISIONS,
    FORBIDDEN_STATUSES,
    REVIEW_METHOD,
    REVIEWER_ID,
    REVIEWER_ROLE,
    StatementRevision,
)

APPROVAL_VERSION = "author_approval/1.2"

# Ri-esportati: le tre fasi devono leggere l'identita' del revisore dallo stesso
# posto, altrimenti possono divergere senza che nulla lo segnali.
__all__ = [
    "APPROVAL_VERSION",
    "FORBIDDEN_STATUSES",
    "REVIEWER_ID",
    "REVIEWER_ROLE",
    "REVIEW_METHOD",
    "StatementRevision",
    "APPROVED_UNITS",
    "APPROVED_UNIT_IDS",
    "AUTHOR_DECISION",
    "CANONICAL_SOURCE_ID",
    "DETECTOR_REFERENCE_CASE",
    "DOCUMENT_HASH",
    "FULL_TEXT_ACCESS",
    "LIMITATIONS",
    "PARENT_UNIT_ID",
    "REJECTED_PROPOSALS",
    "SOURCE_BASIS_FACTS",
    "SOURCE_PMID",
    "STATEMENT_REVISIONS",
    "STRUCTURAL_DECISION",
    "TERMINOLOGY_MAPPINGS",
    "ApprovedUnit",
]

# =============================================================================
# La fonte
# =============================================================================

SOURCE_PMID = "23344087"
SOURCE_PMC = ""
CANONICAL_SOURCE_ID = "PMID:23344087"
SOURCE_REPORT = "SOURCE_REVIEW_PMID-23344087.md"
SOURCE_PACKET_ID = "AA-PMID-23344087"
PARENT_UNIT_ID = "PU-PMID-23344087-cohort-1"

SOURCE_TITLE = (
    "Heterogeneity of genetic changes associated with acquired crizotinib "
    "resistance in ALK-rearranged lung cancer."
)

# Hash dell'abstract, non del full text: il full text non esiste in questo
# repository e non e' stato letto da nessuno.
DOCUMENT_HASH = "23bc0f21fcbfb22ce3902d1ca802e6a2607e4b63a45dd1507c3a5c1f3199d296"
LOCATOR_COUNT = 6
LOCATOR_MATCH_TYPES: Mapping[str, int] = {"exact": 6}
AVAILABILITY = ABSTRACT_ONLY

# La dichiarazione va conservata verbatim: se un giorno il full text diventasse
# accessibile, questo record dice che cosa era vero quando la decisione e' stata
# presa, e quindi perche' era prudente.
FULL_TEXT_ACCESS: Mapping[str, Any] = {
    "full_text_publicly_available": False,
    "europe_pmc_status": "subscription required",
    "in_pmc": False,
    "open_access": False,
    "public_access_route": "none",
    "full_text_stored": False,
    "full_text_redistributed": False,
    "figures_and_tables_observable": False,
    "systems_consulted": ["pubmed_efetch", "europe_pmc"],
    "declaration": (
        "full text dichiarato «Subscription required» da Europe PMC: non e' in "
        "PMC, non e' open access, nessuna via pubblica di accesso"
    ),
}

SOURCE_BASIS_FACTS: Mapping[str, Any] = {
    **constraints_for_basis(ABSTRACT_ONLY),
    "availability": AVAILABILITY,
    "abstract_hash": DOCUMENT_HASH,
    "abstract_hash_matches": True,
    "abstract_length": 1683,
    "abstract_sections": ["BACKGROUND", "METHODS", "RESULTS", "CONCLUSIONS"],
    "locators_verified": LOCATOR_COUNT,
    "locator_match_type_counts": dict(LOCATOR_MATCH_TYPES),
    **dict(FULL_TEXT_ACCESS),
}

# =============================================================================
# La decisione strutturale
# =============================================================================

AUTHOR_DECISION = APPROVE_WITH_CORRECTIONS
STRUCTURAL_DECISION = "audit_split_partially_supported"
CLINICAL_PRECLINICAL_SPLIT = "confirmed"

AUDIT_PROPOSED_UNITS = 2
SOURCE_REVIEW_PROPOSED_UNITS = 3
AUTHOR_APPROVED_ACTIVE_UNITS = 2

CLINICAL_UNIT_COUNT = 1
PRECLINICAL_UNIT_COUNT = 1

DECISION_RATIONALE = (
    "L'abstract nomina esplicitamente la coorte clinica e gli esperimenti in "
    "vitro, entrambi come lavoro della fonte: lo split clinico/preclinico e' "
    "confermato. Non e' confermata la composizione della parte preclinica. "
    "SNU-2535, H3122 CR1 e i cloni mutanti sono tutti nominati, ma il fondo "
    "cellulare dei cloni non compare e la loro relazione con SNU-2535 resta "
    "indeterminata. Due unita' precliniche distinte avrebbero registrato come "
    "letta una separazione che nessuno ha letto: restano una sola unita', "
    "dichiarata non separabile al proprio interno."
)

PARENT_STATE = "superseded_by_reviewed_restructure"

# =============================================================================
# Le unita'
# =============================================================================

CLINICAL_COHORT_ID = "PU-PMID-23344087-clinical-cohort"
PRECLINICAL_PANEL_ID = "PU-PMID-23344087-preclinical-unresolved-panel"

ENGINEERED_CLONES_PROPOSAL_ID = "PU-PMID-23344087-engineered-clones"
PATIENT_DERIVED_PROPOSAL_ID = "PU-PMID-23344087-patient-derived"

APPROVED_UNIT_IDS = (CLINICAL_COHORT_ID, PRECLINICAL_PANEL_ID)

# Le due proposte che descrivevano una composizione che l'abstract non sostiene.
REJECTED_PROPOSALS = (ENGINEERED_CLONES_PROPOSAL_ID, PATIENT_DERIVED_PROPOSAL_ID)
REJECTION_STATUS = "rejected_as_active_unit_due_to_insufficient_source_resolution"

# La proposta clinica viene promossa senza cambiare identita': l'abstract la
# sostiene per intero.
PROMOTED_PROPOSALS = (CLINICAL_COHORT_ID,)
PROMOTION_STATUS = "superseded_by_author_approved_unit"

EXPERIMENT_ROLE_OBSERVATION = "clinical_observation"
EXPERIMENT_ROLE_UNRESOLVED_PANEL = "unresolved_in_vitro_resistance_panel"

POLARITY_SUPPORTS = "supports"


@dataclass(frozen=True)
class ApprovedUnit:
    """Una unita' approvata, e da quali proposte source-checked deriva."""

    profile_unit_id: str
    unit_type: str
    source_proposal_ids: tuple[str, ...]
    cohort_id: str
    cohort_label: str
    cohort_note: str
    experiment_role: str
    assertion_polarity: str
    statement_ids: tuple[str, ...] = ()
    overrides: Mapping[str, Any] = field(default_factory=dict)
    role_fields: Mapping[str, Any] = field(default_factory=dict)
    corrections: tuple[str, ...] = ()


# --- unita' 1: la coorte clinica ---------------------------------------------
CLINICAL_COHORT = ApprovedUnit(
    profile_unit_id=CLINICAL_COHORT_ID,
    unit_type=UNIT_TYPE_CLINICAL_COHORT,
    source_proposal_ids=(CLINICAL_COHORT_ID,),
    cohort_id="cohort",
    cohort_label="coorte clinica: 7 pazienti ALK+ con resistenza acquisita al crizotinib",
    cohort_note=(
        "prima revisione approvata sull'abstract. Il riarrangiamento di ALK "
        "precede il trattamento ed e' criterio di ingresso; le mutazioni di "
        "resistenza sono reperti successivi. Linea di terapia, setting e stadio "
        "non sono ignoti per caso: l'abstract non li riporta affatto."
    ),
    experiment_role=EXPERIMENT_ROLE_OBSERVATION,
    assertion_polarity=POLARITY_SUPPORTS,
    statement_ids=("ES-V2-evidence-765", "ES-V2-evidence-767"),
    role_fields={
        # Le due meta' che `biomarker_requirements` da solo confonde. Il ruolo e'
        # gia' dichiarato nella proposta source-checked e viene conservato.
        "biomarker_role": "enrolment_criterion",
        "enrollment_biomarker": ["ALK rearrangement"],
        "enrollment_biomarker_precedes_treatment": True,
        "acquired_findings": [
            "ALK L1196M",
            "ALK G1269A",
            "ALK gene copy number gain",
            "EGFR L858R",
        ],
        "acquired_findings_are_enrolment_criteria": False,
        # L'intervento e' letterale nell'abstract, ma il disegno e'
        # osservazionale: crizotinib e' la terapia rispetto alla quale la
        # resistenza e' emersa, non un braccio assegnato.
        "intervention_role": "prior_or_reference_therapy_not_study_intervention",
        "intervention_attribution": (
            "crizotinib e' la terapia rispetto alla quale i sette pazienti hanno "
            "sviluppato resistenza acquisita; l'abstract non descrive alcuna "
            "assegnazione di trattamento all'interno di questo disegno"
        ),
        # Non dedotto. L'abstract non distingue formalmente terapia precedente,
        # trattamento dello studio e contesto di resistenza: registrarlo come
        # terapia precedente sceglierebbe una delle tre letture.
        "prior_therapy_candidate": "crizotinib",
        "prior_therapy_decision": "not_recorded_without_further_inference",
        "n_subjects": "7",
        "time_to_resistance": "mediana 6 mesi (range 4-12)",
        "patients_with_secondary_alk_mutations": 3,
        "patients_with_copy_number_gain": 1,
        "case_level_observations_present": True,
        "case_level_observations_are_cohort_properties": False,
        # Perche' `not_separable` e non `unknown`: l'abstract non riporta queste
        # dimensioni affatto, e la proposta source-checked lo aveva gia' deciso.
        "dimensions_not_reported_by_abstract": ["therapy_line", "setting", "stage"],
    },
)

# --- unita' 2: il pannello preclinico non risolto ----------------------------
# `preclinical_in_vitro` e' il tipo generico gia' presente nel vocabolario.
# `preclinical_engineered_model` o `preclinical_patient_derived_model` direbbero
# di che cosa e' fatto il pannello, che e' esattamente la cosa che l'abstract non
# dice: il tipo affermerebbe piu' della fonte.
PRECLINICAL_PANEL = ApprovedUnit(
    profile_unit_id=PRECLINICAL_PANEL_ID,
    unit_type=UNIT_TYPE_PRECLINICAL,
    source_proposal_ids=(PATIENT_DERIVED_PROPOSAL_ID, ENGINEERED_CLONES_PROPOSAL_ID),
    cohort_id="preclinical-panel",
    cohort_label=(
        "pannello preclinico in vitro non risolto: SNU-2535, H3122 CR1 e i cloni "
        "mutanti L1196M e G1269A"
    ),
    cohort_note=(
        "una sola unita', dichiarata non separabile al proprio interno. I tre "
        "componenti sono confermati dall'abstract; la loro relazione no. Attivare "
        "due unita' distinte avrebbe registrato come letta una separazione che "
        "nessuno ha letto."
    ),
    experiment_role=EXPERIMENT_ROLE_UNRESOLVED_PANEL,
    assertion_polarity=POLARITY_SUPPORTS,
    statement_ids=("ES-V2-evidence-765",),
    overrides={
        "evidence_design": (
            "esperimenti in vitro di citotossicita' e sensibilita' al crizotinib, "
            "con confronto fra cellule NSCLC naive e resistenti"
        ),
        "comparator": "cellule NSCLC crizotinib-naive",
    },
    role_fields={
        "model_components": ["SNU-2535", "H3122 CR1", "mutant clones"],
        "model_component_count_known": False,
        "preclinical_model_composition": NOT_SEPARABLE,
        "cellular_background_of_mutant_clones": "unknown",
        "component_to_statement_mapping": NOT_SEPARABLE,
        # Le quattro affermazioni che l'abstract non sostiene, elencate perche' un
        # test possa cercarle invece di fidarsi che non compaiano.
        "not_asserted": [
            "tutti i cloni derivano da SNU-2535",
            "tutti i cloni derivano da H3122 CR1",
            "SNU-2535 e i cloni sono la stessa unita' sperimentale",
            "il numero dei sistemi preclinici distinti e' noto",
        ],
        "clones_derived_from_snu2535": "not_asserted_by_source",
        "clones_derived_from_h3122_cr1": "not_asserted_by_source",
        "snu2535_and_clones_same_experimental_unit": "not_asserted_by_source",
        "distinct_preclinical_system_count": "unknown",
        # Le due intensita' che l'abstract distingue e che il pannello conserva
        # separate: SNU-2535 «resistant», i cloni «less sensitive».
        "component_observations": [
            {
                "component": "SNU-2535",
                "origin": "derivata da un paziente che portava la mutazione G1269",
                "observation": "resistant to crizotinib treatment similar to H3122 CR1 cells",
                "intensity": "resistant",
                "source_locators": ["B-pre-snu2535"],
            },
            {
                "component": "L1196M and G1269A mutant clones",
                "origin": "fondo cellulare non riportato dall'abstract",
                "observation": (
                    "less sensitive to crizotinib; ALK downstream signals "
                    "ineffectively suppressed"
                ),
                "intensity": "relative_reduced_sensitivity",
                "source_locators": ["B-pre-clones"],
            },
        ],
        "clinical_response_observed": False,
        "clinical_population_inherited": False,
        # Resta non propagabile anche dopo una eventuale seconda revisione: la
        # composizione interna e' il problema, e una seconda lettura dello stesso
        # abstract non la risolverebbe.
        "propagation_blocked_beyond_second_review": True,
        "propagation_unblock_conditions": [
            "la composizione interna del pannello viene risolta su full text",
            "una decisione finale autorizza esplicitamente una propagazione solo "
            "a livello di fonte",
        ],
    },
    corrections=(
        "le proposte source-checked `patient-derived` e `engineered-clones` non "
        "diventano unita' attive: l'abstract conferma i componenti, non la loro "
        "separazione",
    ),
)

APPROVED_UNITS = (CLINICAL_COHORT, PRECLINICAL_PANEL)

REJECTION_RATIONALE = (
    "L'abstract nomina i cloni mutanti senza il fondo cellulare su cui sono "
    "costruiti, e non dice se derivino da SNU-2535, da H3122 CR1 o da altro. "
    "Sapere che i componenti esistono non basta per sapere che cosa sono, ne' "
    "quanti sistemi distinti rappresentino. Due unita' separate avrebbero "
    "attribuito a ciascuna una identita' sperimentale che la fonte non fornisce."
)

# =============================================================================
# Gli statement
# =============================================================================

# --- ES-V2-evidence-765 ------------------------------------------------------
# Clinico e preclinico concordano sulla direzione. Non concordano sull'intensita':
# l'abstract dice «less sensitive» per i cloni, lo statement dice «resistance».
# Non e' un conflitto — la fonte non nega la resistenza — ma non e' nemmeno un
# sinonimo, e le due cose vanno tenute distinte.
REVISION_765 = StatementRevision(
    statement_id="ES-V2-evidence-765",
    previous_candidate_status="candidate_partial",
    first_review_status="candidate_partial",
    link_status="partial_link",
    supported_dimensions=(
        "disease",
        "biomarker",
        "intervention",
        "clinical resistance context",
        "preclinical direction of effect",
    ),
    unsupported_dimensions=(
        "claim strength",
        "preclinical model composition",
        "component to statement mapping",
    ),
    rationale=(
        "G1269A e' osservata in due dei sette pazienti, e l'abstract riporta una "
        "corrispondenza preclinica: SNU-2535, derivata da un paziente con la "
        "mutazione G1269, e' resistente, e i cloni G1269A sono meno sensibili. La "
        "relazione fra caso clinico e componente preclinica esiste. Cio' che non "
        "esiste e' una formulazione non qualificata di resistenza completa: "
        "«less sensitive» non e' «resistance», e senza full text la composizione "
        "del pannello resta non separabile."
    ),
    extra={
        "support_type": "clinical_observation_with_preclinical_validation",
        # Separati e non fusi: la riduzione di sensibilita' in coltura non e' un
        # esito clinico.
        "clinical_support": {
            "kind": "resistance-associated alteration observed in a patient context",
            "detail": "due pazienti con G1269A fra i sette con resistenza acquisita",
            "profile_unit_id": CLINICAL_COHORT_ID,
            "source_locators": ["B-clin-mutations"],
        },
        "preclinical_support": {
            "kind": "reduced crizotinib sensitivity in vitro",
            "detail": (
                "SNU-2535 (da paziente con mutazione G1269) resistente in modo "
                "simile a H3122 CR1; cloni L1196M e G1269A meno sensibili"
            ),
            "profile_unit_id": PRECLINICAL_PANEL_ID,
            "source_locators": ["B-pre-snu2535", "B-pre-clones"],
        },
        "preclinical_validation_is_clinical_response": False,
        # La differenza di forza, registrata come tale.
        "source_term": "less sensitive to crizotinib",
        "statement_term": "resistance",
        "resistance_qualifier": "relative_reduced_sensitivity",
        "complete_resistance": False,
        "mapping_status": "requires_terminology_verification",
        "claim_strength_alignment": "partial",
        "assertion_conflict": False,
        "conflict_dimensions": [],
        "preclinical_model_composition": NOT_SEPARABLE,
        "component_to_statement_mapping": NOT_SEPARABLE,
        "non_propagation_rules": ["relative_versus_complete_resistance"],
        **constraints_for(GRANULARITY_COHORT),
        "population_scope": "cohort",
        "profile_unit_ids": [CLINICAL_COHORT_ID, PRECLINICAL_PANEL_ID],
        "previous_profile_unit_ids": [
            CLINICAL_COHORT_ID,
            PATIENT_DERIVED_PROPOSAL_ID,
            ENGINEERED_CLONES_PROPOSAL_ID,
        ],
        "source_basis": ABSTRACT_ONLY,
        "structural_confidence": CONFIDENCE_PARTIAL,
    },
)

# --- ES-V2-evidence-767 ------------------------------------------------------
# Ambiguo, non conflittuale. La distinzione non e' di sfumatura: `conflicting`
# direbbe che la fonte contraddice lo statement, e la fonte non lo contraddice.
# Dice meno di quanto lo statement affermi, e in un modo particolare — l'unico
# paziente con copy number gain portava anche EGFR L858R, quindi il contributo
# causale delle due alterazioni non e' separabile.
REVISION_767 = StatementRevision(
    statement_id="ES-V2-evidence-767",
    previous_candidate_status="candidate_ambiguous",
    first_review_status="candidate_ambiguous",
    link_status="ambiguous_link",
    supported_dimensions=("disease", "intervention", "clinical resistance context"),
    unsupported_dimensions=(
        "isolated causal attribution",
        "population",
        "frequency",
        "biomarker_specificity",
    ),
    rationale=(
        "Un solo paziente dei sette ha mostrato copy number gain di ALK, con un "
        "aumento di 4.1 volte rispetto al campione pre-crizotinib. Lo stesso "
        "paziente portava EGFR L858R con polisomia elevata. Attribuire la "
        "resistenza al copy number gain sceglie una delle due spiegazioni senza "
        "che la fonte lo faccia. Non e' un conflitto: la fonte non contraddice lo "
        "statement, non permette di isolarne il meccanismo."
    ),
    extra={
        "support_type": "direct_clinical_support_with_confounded_causal_attribution",
        **constraints_for(GRANULARITY_CASE),
        "population_scope": SCOPE_SINGLE_PATIENT,
        "subset_size": 1,
        "cohort_size": 7,
        # L'abstract dice «one patient» e non lo numera. Inventare un numero
        # sarebbe l'unico modo di far sembrare tracciabile un caso che non lo e'.
        "case_identifier": "unknown",
        "case_identifier_verified": False,
        "case_identifier_reason": (
            "l'abstract dice «one patient» senza numerarlo; nessun identificatore "
            "compare nei sei locator verificati"
        ),
        "case_identifier_locators": ["B-clin-cng"],
        "cooccurring_alterations": ["EGFR L858R"],
        "cooccurrence_detail": "EGFR L858R mutation with high polysomy",
        "causal_attribution": NOT_SEPARABLE,
        "isolated_mechanism_support": False,
        "confounding_status": "molecular_cooccurrence",
        "assertion_conflict": False,
        "conflict_dimensions": [],
        "source_contradicts_statement": False,
        "why_not_conflicting": (
            "`conflicting` direbbe che la fonte nega lo statement. La fonte non lo "
            "nega: non permette di attribuire l'effetto a una delle due "
            "alterazioni co-occorrenti"
        ),
        "preclinical_support_in_this_source": False,
        "cng_fold_increase": "4.1",
        "non_propagation_rules": ["case_report_to_population"],
        "profile_unit_ids": [CLINICAL_COHORT_ID],
        "source_basis": ABSTRACT_ONLY,
        "structural_confidence": CONFIDENCE_PARTIAL,
    },
)

STATEMENT_REVISIONS = (REVISION_765, REVISION_767)

CANDIDATE_PARTIAL_COUNT = 1
CANDIDATE_AMBIGUOUS_COUNT = 1
CASE_LEVEL_STATEMENT_COUNT = 1

# =============================================================================
# Terminologia
# =============================================================================

MAPPING_CNG: Mapping[str, Any] = {
    "mapping_id": "TM-PMID-23344087-cng",
    "statement_id": "ES-V2-evidence-767",
    "source_term": "ALK gene copy number gain",
    "statement_term": "ALK Amplification",
    "mapping_type": "biomarker_strength_normalization",
    "source_checked_mapping_type": "concept_broadening",
    "mapping_status": "requires_terminology_verification",
    "literal_equivalence": False,
    "literal_string_present_in_source": False,
    "source_supports_broader_concept": True,
    "source_supports_exact_normalized_term": "not_verified",
    "kg_used_as_sole_authority": False,
    "promoted_to_verified_synonym": False,
    # L'abstract usa «amplifications» una volta, nei metodi, per descrivere che
    # cosa e' stato *analizzato*. Nei risultati il reperto e' «copy number gain».
    # Il valore source-native resta quello del reperto.
    "source_native_term": "ALK gene copy number gain",
    "amplification_used_as_source_native": False,
    "uncertain_dimension": "biomarker_specificity",
    "source_locators": ["B-clin-cng"],
    "rationale": (
        "l'abstract riporta il reperto come «copy number gain», quantificato in un "
        "aumento di 4.1 volte rispetto al campione pre-crizotinib. «Amplification» "
        "ha in oncologia una soglia propria, e l'abstract usa quel termine soltanto "
        "nei metodi per dire che cosa e' stato analizzato, non per descrivere il "
        "reperto"
    ),
}

MAPPING_SENSITIVITY: Mapping[str, Any] = {
    "mapping_id": "TM-PMID-23344087-sensitivity",
    "statement_id": "ES-V2-evidence-765",
    "source_term": "less sensitive to crizotinib",
    "statement_term": "resistance",
    "mapping_type": "evidence_strength_normalization",
    "source_checked_mapping_type": "strength_escalation",
    "mapping_status": "requires_terminology_verification",
    "literal_equivalence": False,
    "literal_string_present_in_source": False,
    "source_supports_broader_concept": True,
    "source_supports_exact_normalized_term": "not_verified",
    "kg_used_as_sole_authority": False,
    "promoted_to_verified_synonym": False,
    "resistance_qualifier": "relative_reduced_sensitivity",
    "complete_resistance": False,
    # Il punto che distingue questo mapping dal precedente: non e' un dubbio su
    # quale concetto sia, e' un dubbio su quanto sia forte.
    "assertion_conflict": False,
    "uncertain_dimension": "claim_strength",
    "source_locators": ["B-pre-clones", "B-pre-snu2535"],
    "rationale": (
        "l'abstract distingue due intensita' nella stessa frase: SNU-2535 e' "
        "«resistant», i cloni mutanti sono «less sensitive». Lo statement usa "
        "«resistance» senza qualificatore. La differenza non e' un conflitto — la "
        "fonte non nega la resistenza — ma trasformare una riduzione relativa in "
        "resistenza completa aggiungerebbe forza che la fonte non fornisce"
    ),
}

TERMINOLOGY_MAPPINGS = (MAPPING_CNG, MAPPING_SENSITIVITY)

# =============================================================================
# Il rilevatore
# =============================================================================

PARTIALLY_CONFIRMED_MIXTURE = "partially_confirmed_clinical_preclinical_mixture"

# Il terzo principio della serie, e il piu' scomodo: sui due casi precedenti il
# rilevatore aveva torto sulla presenza (31358542) o sul conteggio (22235099).
# Qui non e' il rilevatore ad avere torto — e' il documento a non bastare.
DETECTOR_PRINCIPLE = "an_unreadable_structure_is_not_a_detector_error"

DETECTOR_REFERENCE_CASE: Mapping[str, Any] = {
    "detector_reference_case": True,
    "reference_case_type": PARTIALLY_CONFIRMED_MIXTURE,
    "detector_original_verdict": "split_required",
    "reviewed_verdict": "split_partially_supported",
    "reference_case_status": "first_review_confirmed",
    "detector_presence_signal_correct": True,
    "detector_granularity_prediction_correct": False,
    "detector_promoted": False,
    "use_as_regression_case": True,
    "use_for_detector_performance_estimation": False,
    "detector_predicted_unit_count": AUDIT_PROPOSED_UNITS,
    "source_review_proposed_unit_count": SOURCE_REVIEW_PROPOSED_UNITS,
    "author_approved_active_unit_count": AUTHOR_APPROVED_ACTIVE_UNITS,
    "principle": DETECTOR_PRINCIPLE,
    "correct_signals": ["preclinical.in_vitro", "clinical.patients"],
    "wrong_signals": [],
    "missing_signals": ["composizione della componente preclinica"],
    "signal_count": 11,
    "detector_score": 14,
    "source_basis": ABSTRACT_ONLY,
    "ground_truth_available": False,
    "ground_truth_unavailable_reason": (
        "senza full text non esiste un numero corretto di unita' contro cui "
        "misurare la previsione"
    ),
    "rationale": (
        "il rilevatore ha identificato correttamente la presenza di una parte "
        "clinica e di una preclinica, e su un solo segnale «in vitro» che questa "
        "volta e' genuino: sta nei metodi dell'abstract e descrive un esperimento "
        "della fonte. Non ha previsto la composizione della parte preclinica, ma "
        "non poteva: l'abstract non la contiene. Il caso e' un positivo "
        "**parziale** e resta un caso di regressione, non una misura: non esiste "
        "un numero corretto di unita' contro cui confrontare la previsione"
    ),
}

# =============================================================================
# Limiti
# =============================================================================

LIMITATIONS = (
    "la revisione e' documentale e non clinica: l'autore non e' un clinico",
    "la preparazione del materiale e' assistita da LLM, quindi la prima revisione "
    "non e' indipendente",
    "la fonte e' disponibile soltanto come abstract: il full text e' dichiarato "
    "«Subscription required» da Europe PMC, non e' in PMC e non e' open access",
    "figure e tabelle non sono osservabili",
    "il fondo cellulare dei cloni mutanti non compare nell'abstract: la "
    "composizione del pannello preclinico resta non separabile",
    "il numero di sistemi preclinici distinti non e' determinabile",
    "il paziente con copy number gain non e' numerato nell'abstract: il case "
    "identifier resta `unknown`",
    "entrambi i mapping terminologici restano non verificati",
    "tre casi confermati non permettono di stimare precision, recall o "
    "accuratezza del rilevatore",
)

RESIDUAL_RISK = (
    "senza full text non e' possibile sapere quanti sistemi preclinici distinti "
    "esistano davvero, ne' su quale fondo cellulare siano costruiti i cloni. Il "
    "pannello unico e' la registrazione onesta di questa ignoranza, non una "
    "affermazione sulla struttura reale della fonte."
)

# Guardie di coerenza del modulo: se qualcuno cambia la decisione senza cambiare
# il vocabolario, il fallimento e' all'import e non tre artefatti piu' tardi.
if AUTHOR_DECISION not in AUTHOR_DECISIONS:  # pragma: no cover - invariante
    raise RuntimeError(f"decisione non ammessa: {AUTHOR_DECISION!r}")
if len(APPROVED_UNITS) != AUTHOR_APPROVED_ACTIVE_UNITS:  # pragma: no cover - invariante
    raise RuntimeError("il numero di unita' attive non coincide con la decisione")
if SOURCE_BASIS_FACTS["full_text_verified"]:  # pragma: no cover - invariante
    raise RuntimeError("una revisione su abstract non puo' dirsi verificata sul full text")
