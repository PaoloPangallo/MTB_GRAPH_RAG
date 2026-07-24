"""Approvazione dell'autore sulla revisione documentale di PMID 22235099.

Come per PMID 31358542, la decisione e' umana: l'ha presa Paolo Pangallo, autore
della tesi, con assistenza LLM nella preparazione documentale. Il modulo la
registra e non la produce, ed e' la ragione per cui i suoi valori sono scritti a
mano. Identita' del revisore, decisioni ammesse e stati proibiti sono importati
da `author_approval`: sono gli stessi, e duplicarli permetterebbe a due fasi di
divergere senza che nulla lo segnali.

La differenza rispetto alla fonte precedente e' l'esito. La', lo split proposto
era stato **respinto**. Qui e' confermato, e la correzione riguarda il numero:
l'audit proponeva due unita', la revisione documentale ne proponeva cinque,
l'autore ne approva **quattro**.

Il taglio da cinque a quattro non e' un arrotondamento. Ba/F3 e NIH3T3 sono due
fondi cellulari e due saggi diversi, ma rispondono alla stessa domanda su G1269A
e danno la stessa risposta: sono due esecuzioni di una validazione, non due
validazioni. Tenerle separate farebbe contare due volte una conferma sola. Le
altre tre restano distinte perche' le domande sono diverse — una coorte di
pazienti, un modello derivato da paziente che ha perso il bersaglio, un
esperimento con esito negativo — e perche' fondere il negativo con i positivi lo
trasformerebbe nel suo contrario.

Tre correzioni del report vanno lette nel dettaglio, e sono documentate qui
accanto ai valori che producono: la consolidazione, la granularita' di
ES-V2-evidence-766 (due pazienti nominati, non uno) e la composizione della
coorte (dodici resistenze acquisite e due intrinseche, non quattordici
acquisite).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from backend.pipeline.evidence.evidence_granularity import (
    GRANULARITY_CASE,
    GRANULARITY_COHORT,
    GRANULARITY_NAMED_PATIENT_SUBSET,
    SCOPE_NAMED_PATIENTS_SUBSET,
    SCOPE_SINGLE_PATIENT,
    constraints_for,
)
from backend.pipeline.evidence.profile_unit import (
    UNIT_TYPE_CLINICAL_COHORT,
    UNIT_TYPE_PRECLINICAL_ENGINEERED,
    UNIT_TYPE_PRECLINICAL_PATIENT_DERIVED,
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

APPROVAL_VERSION = "author_approval/1.1"

# Ri-esportati da `author_approval`: le fasi devono leggerli dallo stesso posto,
# altrimenti due approvazioni possono dichiarare revisori diversi senza che nulla
# lo segnali.
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
    "CONSOLIDATION",
    "DETECTOR_REFERENCE_CASE",
    "DOCUMENT_HASH",
    "ES766_DISCREPANCY",
    "LIMITATIONS",
    "PARENT_UNIT_ID",
    "REPLACED_PROPOSALS",
    "RETAINED_PROPOSALS",
    "SOURCE_PMC",
    "SOURCE_PMID",
    "STATEMENT_REVISIONS",
    "STRUCTURAL_DECISION",
    "TERMINOLOGY_MAPPING",
    "ApprovedUnit",
]

# =============================================================================
# La fonte
# =============================================================================

SOURCE_PMID = "22235099"
SOURCE_PMC = "PMC3311875"
CANONICAL_SOURCE_ID = "PMID:22235099"
SOURCE_REPORT = "SOURCE_REVIEW_PMID-22235099.md"
SOURCE_PACKET_ID = "AA-PMID-22235099"
PARENT_UNIT_ID = "PU-PMID-22235099-cohort-1"

# Verificati sul batch source-checked prima di scrivere qualunque cosa. Sono qui
# perche' un test possa confrontarli con l'artefatto invece di fidarsi.
DOCUMENT_HASH = "ff9615e75fe8e274c9cc9656bfee3b4b55d867306102f995bd45c6c6086b3e32"
LOCATOR_COUNT = 12
LOCATOR_MATCH_TYPES: Mapping[str, int] = {"exact": 12}

# =============================================================================
# La decisione strutturale
# =============================================================================

AUTHOR_DECISION = APPROVE_WITH_CORRECTIONS
STRUCTURAL_DECISION = "audit_split_confirmed_with_more_units"
CLINICAL_PRECLINICAL_SPLIT = "confirmed"

AUDIT_PROPOSED_UNITS = 2
SOURCE_REVIEW_PROPOSED_UNITS = 5
AUTHOR_APPROVED_UNITS = 4

CLINICAL_UNIT_COUNT = 1
PRECLINICAL_UNIT_COUNT = 3

DECISION_RATIONALE = (
    "Lo split clinico/preclinico e' confermato: la fonte contiene esperimenti "
    "propri, non citati. Due unita' non bastavano — i sistemi preclinici sono "
    "distinti per fondo cellulare, saggio e direzione del risultato — ma cinque "
    "erano troppe: Ba/F3 e NIH3T3 validano la stessa proposizione su G1269A con "
    "due esecuzioni convergenti, e contarle separatamente farebbe sembrare due "
    "conferme cio' che ne e' una."
)

PARENT_STATE = "superseded_by_reviewed_restructure"

# =============================================================================
# Le unita'
# =============================================================================

CLINICAL_COHORT_ID = "PU-PMID-22235099-clinical-cohort"
ENGINEERED_MODELS_ID = "PU-PMID-22235099-engineered-isogenic-models"
CUTO1_ID = "PU-PMID-22235099-cuto1-comparative"
H3122_KRAS_ID = "PU-PMID-22235099-h3122-kras-engineered"

BAF3_PROPOSAL_ID = "PU-PMID-22235099-baf3-engineered"
NIH3T3_PROPOSAL_ID = "PU-PMID-22235099-nih3t3-engineered"

APPROVED_UNIT_IDS = (
    CLINICAL_COHORT_ID,
    ENGINEERED_MODELS_ID,
    CUTO1_ID,
    H3122_KRAS_ID,
)

# I ruoli epistemici che il brief chiedeva di esprimere come `unit_type`. Non lo
# sono: `UNIT_TYPES` descrive **che cosa** e' l'unita', e «validazione
# funzionale» o «esperimento negativo» dicono a che cosa serve, che e' un'altra
# domanda. Coniare un tipo per ogni combinazione moltiplicherebbe il vocabolario
# e renderebbe `is_preclinical` dipendente dall'esito dell'esperimento.
EXPERIMENT_ROLE_FUNCTIONAL_VALIDATION = "functional_validation"
EXPERIMENT_ROLE_NEGATIVE = "negative_experiment"
EXPERIMENT_ROLE_COMPARATIVE = "comparative_pharmacology"
EXPERIMENT_ROLE_OBSERVATION = "clinical_observation"

POLARITY_SUPPORTS = "supports"
POLARITY_DOES_NOT_SUPPORT = "does_not_support"


@dataclass(frozen=True)
class ApprovedUnit:
    """Una unita' approvata, e da quali proposte source-checked deriva.

    `source_proposal_ids` e' una tupla e non una stringa perche' una unita' puo'
    derivare da piu' proposte: e' esattamente il caso della consolidazione, e un
    campo singolo l'avrebbe resa irrappresentabile.
    """

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
# Il riarrangiamento di ALK era requisito di arruolamento; tutto il resto e'
# reperto successivo. Tenerli nello stesso campo li renderebbe indistinguibili, e
# un reperto letto come requisito farebbe sembrare selezionata una popolazione
# che non lo era.
CLINICAL_COHORT = ApprovedUnit(
    profile_unit_id=CLINICAL_COHORT_ID,
    unit_type=UNIT_TYPE_CLINICAL_COHORT,
    source_proposal_ids=(CLINICAL_COHORT_ID,),
    cohort_id="cohort",
    cohort_label="coorte clinica: 14 pazienti ALK+ ri-biopsiati alla progressione su crizotinib",
    cohort_note=(
        "prima revisione approvata. La coorte e' una serie osservazionale di "
        "ri-biopsie: il riarrangiamento di ALK e' il criterio di arruolamento, le "
        "alterazioni di resistenza sono reperti successivi, e le osservazioni su "
        "singoli pazienti non sono proprieta' della coorte."
    ),
    experiment_role=EXPERIMENT_ROLE_OBSERVATION,
    assertion_polarity=POLARITY_SUPPORTS,
    statement_ids=("ES-V2-evidence-4288", "ES-V2-evidence-764", "ES-V2-evidence-766"),
    role_fields={
        # Le due meta' che il campo `biomarker_requirements` da solo confonde.
        # Il ruolo va dichiarato: senza, `rule_observed_biomarker_to_requirement`
        # non puo' distinguere un requisito da un reperto, e ha ragione a fermarsi.
        "biomarker_role": "enrolment_criterion",
        "enrollment_biomarker": ["ALK rearrangement"],
        "enrollment_biomarker_assay": "FISH break-apart",
        "acquired_resistance_findings": [
            "ALK L1196M",
            "ALK G1269A",
            "copy number gain del riarrangiamento di ALK",
            "EGFR L858R",
            "EGFR S768I",
            "KRAS G12C",
        ],
        "acquired_findings_are_enrolment_criteria": False,
        # L'intervento e' verificato sulla fonte, ma non e' l'intervento di uno
        # studio interventistico: e' la terapia rispetto alla quale la resistenza
        # e' emersa. Cancellarlo perderebbe un valore verificato; lasciarlo senza
        # ruolo lo farebbe leggere come il braccio di un trial.
        "intervention_role": "prior_or_reference_therapy_not_study_intervention",
        "intervention_attribution": (
            "crizotinib e' la terapia rispetto alla quale e' emersa la resistenza, "
            "non l'intervento assegnato da questo disegno osservazionale"
        ),
        # `prior_therapies` resta vuoto: rappresentare crizotinib come terapia
        # precedente richiede di fissare rispetto a **cosa** e' precedente, e la
        # fonte non lo dice in una forma che il modello attuale registri senza
        # inferenza. Il farmaco resta comunque nel record, in `intervention`.
        "prior_therapy_candidate": "crizotinib",
        "prior_therapy_decision": "not_recorded_without_further_inference",
        "n_subjects": "14 ri-biopsiati, 11 con materiale valutabile",
        "resistance_subgroups": {
            "acquired_resistance_patients": 12,
            "intrinsic_resistance_patients": 2,
        },
        "case_level_observations_present": True,
        "case_level_observations_are_cohort_properties": False,
    },
    corrections=(
        "il report descriveva la popolazione come «14 pazienti con resistenza "
        "acquisita»: la fonte ne conta 12 acquisite e 2 intrinseche, e la "
        "formulazione aggregata avrebbe reso acquisita una resistenza che non lo era",
    ),
)

# --- unita' 2: i modelli isogenici ingegnerizzati -----------------------------
CONSOLIDATION_RATIONALE = (
    "stessa alterazione principale (G1269A su fondo di fusione EML4-ALK), stesso "
    "farmaco (crizotinib), stessa proposizione biologica, stessa direzione del "
    "risultato, stessi statement candidati. Due fondi cellulari e due saggi "
    "diversi rendono la conferma piu' solida, non doppia: sono due esecuzioni di "
    "una validazione."
)

ENGINEERED_MODELS = ApprovedUnit(
    profile_unit_id=ENGINEERED_MODELS_ID,
    unit_type=UNIT_TYPE_PRECLINICAL_ENGINEERED,
    source_proposal_ids=(BAF3_PROPOSAL_ID, NIH3T3_PROPOSAL_ID),
    cohort_id="engineered-isogenic",
    cohort_label=(
        "modelli isogenici ingegnerizzati con i costrutti EML4-ALK wild-type, "
        "G1269A, C1156Y e L1196M: Ba/F3 e NIH3T3"
    ),
    cohort_note=(
        "consolidazione approvata dall'autore delle due proposte source-checked "
        "Ba/F3 e NIH3T3. Convalidano la stessa proposizione con due sistemi "
        "convergenti: separarle farebbe contare due volte una conferma sola."
    ),
    experiment_role=EXPERIMENT_ROLE_FUNCTIONAL_VALIDATION,
    assertion_polarity=POLARITY_SUPPORTS,
    statement_ids=("ES-V2-evidence-764",),
    overrides={
        "evidence_design": (
            "validazione funzionale su modelli isogenici ingegnerizzati: "
            "proliferazione con IC50 su Ba/F3 e crescita in soft agar con "
            "immunoblot su NIH3T3"
        ),
    },
    role_fields={
        "model_instances": [
            {
                "model_name": "Ba/F3",
                "model_type": "linea cellulare murina ingegnerizzata (Ba/F3)",
                "assay": "proliferazione a 72 ore, IC50",
                "endpoint": "cellule vitali rispetto al controllo non trattato",
                "source_proposal_id": BAF3_PROPOSAL_ID,
                "source_locators": ["A-pre-baf3", "A-pre-baf3-result"],
            },
            {
                "model_name": "NIH3T3",
                "model_type": "fibroblasti murini ingegnerizzati (NIH3T3)",
                "assay": (
                    "formazione di colonie in soft agar; immunoblot di ALK, ERK, "
                    "STAT3, AKT fosforilati"
                ),
                "endpoint": "conta delle colonie; livelli di fosforilazione",
                "source_proposal_id": NIH3T3_PROPOSAL_ID,
                "source_locators": ["A-pre-nih3t3"],
            },
        ],
        "model_instance_count": 2,
        # Il costrutto, non un requisito di arruolamento: `biomarker_requirements`
        # resta vuoto perche' un modello non arruola nessuno.
        "model_biomarker": "ALK G1269A in ALK fusion context",
        "model_biomarker_role": "engineered_construct",
        "support_role": "functional validation of a clinically observed resistance alteration",
        "clinical_response_observed": False,
        "resistance_qualifier": "resistenza relativa, intermedia fra C1156Y e L1196M",
        "resistance_is_complete": False,
        "clinical_population_inherited": False,
        "consolidation_rationale": CONSOLIDATION_RATIONALE,
    },
    corrections=(
        "le proposte source-checked Ba/F3 e NIH3T3 sono sostituite da una sola "
        "unita' epistemica",
    ),
)

# --- unita' 3: CUTO-1 ---------------------------------------------------------
# Deriva dal paziente #10 e non e' il paziente #10. La relazione e' `derivato
# da`, non `uguale a`, e la differenza e' l'intera ragione per cui l'unita'
# esiste separata: il modello ha perso il bersaglio che il paziente aveva.
CUTO1 = ApprovedUnit(
    profile_unit_id=CUTO1_ID,
    unit_type=UNIT_TYPE_PRECLINICAL_PATIENT_DERIVED,
    source_proposal_ids=(CUTO1_ID,),
    cohort_id="comparative",
    cohort_label="CUTO-1 (derivata dal paziente #10) confrontata con H3122 e H2228",
    cohort_note=(
        "unita' preclinica autonoma, non un prolungamento del caso clinico. La "
        "relazione col paziente #10 e' di derivazione: nessun qualificatore "
        "clinico attraversa il confine."
    ),
    experiment_role=EXPERIMENT_ROLE_COMPARATIVE,
    assertion_polarity=POLARITY_SUPPORTS,
    role_fields={
        "model_name": "CUTO-1",
        "model_context": "patient-derived cellular model",
        "derived_from_clinical_case": "patient_10",
        "derivation_relation": "clinical_case -> derived_model",
        "derivation_is_identity": False,
        "comparator_models": ["H3122", "H2228"],
        "ALK_rearrangement_in_clinical_sample": "present",
        "ALK_rearrangement_in_CUTO1_model": "lost_or_not_detected",
        # Onesta' sul supporto: la perdita del riarrangiamento e' asserita dalla
        # revisione source-checked, ma nessuno dei 12 locator verificati la
        # ancora a una frase propria. Registrarla senza dirlo la farebbe sembrare
        # verificata quanto il resto.
        "ALK_loss_locator_status": "asserted_by_source_checked_review_without_dedicated_locator",
        "ALK_loss_requires_locator_verification": True,
        "cross_context_biomarker_propagation": "forbidden",
        "inherited_from_clinical_case": [],
        "not_inherited_from_clinical_case": [
            "biomarker",
            "population",
            "setting",
            "therapy_line",
            "stage",
            "other_alterations",
        ],
        "clinical_response_observed": False,
    },
    corrections=(
        "ri-tipizzata da `preclinical_in_vitro_comparative_pharmacology` a "
        "`preclinical_patient_derived_model`: l'origine da paziente e' la "
        "proprieta' che ne governa i divieti di propagazione",
    ),
)

# --- unita' 4: H3122 con KRAS G12V, esito negativo ---------------------------
H3122_KRAS = ApprovedUnit(
    profile_unit_id=H3122_KRAS_ID,
    unit_type=UNIT_TYPE_PRECLINICAL_ENGINEERED,
    source_proposal_ids=(H3122_KRAS_ID,),
    cohort_id="engineered-kras",
    cohort_label="H3122 con KRAS G12V introdotto, contro vettore vuoto",
    cohort_note=(
        "esperimento con esito negativo, conservato come unita' propria. Fuso con "
        "i modelli positivi diventerebbe il suo contrario: sembrerebbe che KRAS "
        "G12V abbia mostrato resistenza, mentre argomenta che non la conferisce."
    ),
    experiment_role=EXPERIMENT_ROLE_NEGATIVE,
    assertion_polarity=POLARITY_DOES_NOT_SUPPORT,
    role_fields={
        "model": "H3122 engineered with KRAS G12V",
        "hypothesis_tested": "KRAS G12V confers crizotinib resistance",
        "result_direction": "no_significant_difference",
        "result_interpretation": (
            "experiment does not support KRAS G12V as a crizotinib-resistance "
            "mechanism in this model"
        ),
        "negative_result": True,
        "negative_result_preserved": True,
        "must_not_be_read_as": "KRAS G12V -> resistance to crizotinib",
        "cohort_generalizable": False,
        "clinical_response_observed": False,
        "visible_in_prototype": True,
    },
)

APPROVED_UNITS = (CLINICAL_COHORT, ENGINEERED_MODELS, CUTO1, H3122_KRAS)

# --- storico ------------------------------------------------------------------

REPLACEMENT_STATUS = "replaced_by_author_approved_consolidation"

# Le due proposte che la consolidazione sostituisce. Restano nel repository:
# cancellarle renderebbe invisibile che la revisione documentale aveva proposto
# cinque unita', e la differenza fra cinque e quattro e' la decisione stessa.
REPLACED_PROPOSALS = (BAF3_PROPOSAL_ID, NIH3T3_PROPOSAL_ID)

# Le tre proposte che l'approvazione promuove senza modificarne l'identita'.
RETAINED_PROPOSALS = (CLINICAL_COHORT_ID, CUTO1_ID, H3122_KRAS_ID)

CONSOLIDATION: Mapping[str, Any] = {
    "consolidated_unit_id": ENGINEERED_MODELS_ID,
    "replaced_proposal_ids": list(REPLACED_PROPOSALS),
    "replaced_count": len(REPLACED_PROPOSALS),
    "resulting_count": 1,
    "model_instance_count": 2,
    "shared_alteration": "ALK G1269A in ALK fusion context",
    "shared_intervention": "crizotinib",
    "shared_proposition": (
        "G1269A conferisce resistenza al crizotinib in un contesto di fusione ALK"
    ),
    "shared_result_direction": "resistance_relative_not_complete",
    "shared_statement_candidates": ["ES-V2-evidence-764"],
    "rationale": CONSOLIDATION_RATIONALE,
    "history_preserved": True,
    "replacement_status": REPLACEMENT_STATUS,
}

# =============================================================================
# Gli statement
# =============================================================================

# --- ES-V2-evidence-764: l'unico che fonde i due piani -----------------------
REVISION_764 = StatementRevision(
    statement_id="ES-V2-evidence-764",
    previous_candidate_status="candidate_valid",
    first_review_status="candidate_valid",
    link_status="valid_link",
    supported_dimensions=(
        "disease",
        "biomarker",
        "intervention",
        "clinical resistance context",
        "preclinical functional validation",
    ),
    unsupported_dimensions=("completeness of resistance",),
    rationale=(
        "G1269A e' osservata in due pazienti (#6, #7) alla progressione su "
        "crizotinib, e il suo ruolo funzionale e' validato su due modelli "
        "isogenici. E' l'unico statement della fonte in cui osservazione clinica e "
        "validazione preclinica coesistono, e per questo e' anche l'unico in cui "
        "possono confondersi: la validazione mostra resistenza in coltura, non "
        "risposta clinica."
    ),
    extra={
        "support_type": "clinical_observation_with_preclinical_validation",
        # Separati e non fusi. Un solo campo di supporto renderebbe la validazione
        # funzionale indistinguibile da un esito clinico.
        "clinical_support": {
            "kind": "observed resistance-associated alteration",
            "detail": "due pazienti (#6, #7) con G1269A alla progressione su crizotinib",
            "profile_unit_id": CLINICAL_COHORT_ID,
            "source_locators": ["A-clin-g1269a"],
        },
        "preclinical_support": {
            "kind": "functional validation in engineered models",
            "detail": (
                "Ba/F3 e NIH3T3 con il costrutto G1269A mostrano resistenza al "
                "crizotinib rispetto al wild-type"
            ),
            "profile_unit_id": ENGINEERED_MODELS_ID,
            "source_locators": ["A-pre-baf3-result", "A-pre-nih3t3"],
        },
        "preclinical_validation_is_clinical_response": False,
        "resistance_qualifier": "relative_resistance",
        "non_propagation_rules": [
            "relative_versus_complete_resistance",
            "clinical_population_to_model",
        ],
        **constraints_for(GRANULARITY_COHORT),
        "population_scope": "cohort",
        "profile_unit_ids": [CLINICAL_COHORT_ID, ENGINEERED_MODELS_ID],
        "previous_profile_unit_ids": [
            CLINICAL_COHORT_ID,
            BAF3_PROPOSAL_ID,
            NIH3T3_PROPOSAL_ID,
        ],
    },
)

# --- ES-V2-evidence-4288: un paziente, e resta un paziente -------------------
REVISION_4288 = StatementRevision(
    statement_id="ES-V2-evidence-4288",
    previous_candidate_status="candidate_partial",
    first_review_status="candidate_partial",
    link_status="partial_link",
    supported_dimensions=("disease", "biomarker", "intervention"),
    unsupported_dimensions=("population", "frequency"),
    rationale=(
        "EGFR L858R alla progressione e' documentata in un solo paziente (#9), e la "
        "lesione ri-biopsiata aveva perso il riarrangiamento di ALK. Trattarla come "
        "proprieta' della coorte estenderebbe a quattordici pazienti cio' che si e' "
        "visto in uno."
    ),
    extra={
        "support_type": "direct_clinical_support",
        **constraints_for(GRANULARITY_CASE),
        "population_scope": SCOPE_SINGLE_PATIENT,
        "case_identifier": "patient_9",
        "case_identifier_verified": True,
        "case_identifier_locators": ["A-clin-egfr"],
        "cohort_size": 14,
        "subset_size": 1,
        "non_propagation_rules": ["case_report_to_population"],
        "profile_unit_ids": [CLINICAL_COHORT_ID],
    },
)

# --- ES-V2-evidence-766: due pazienti nominati, non uno ----------------------
# Il brief chiedeva `case_identifier = patient_8`. Il locator dice altro, e la
# differenza non e' un dettaglio: `case_level` significa «un paziente», e qui
# sono due. Il livello `named_patient_subset` esiste per non dover scegliere fra
# dire una cosa falsa e non dire niente.
ES766_DISCREPANCY: Mapping[str, Any] = {
    "statement_id": "ES-V2-evidence-766",
    "expected_by_brief": {
        "evidence_granularity": GRANULARITY_CASE,
        "population_scope": SCOPE_SINGLE_PATIENT,
        "case_identifier": "patient_8",
    },
    "found_in_source": {
        "locator_id": "A-clin-cng",
        "quote": (
            "Two patients demonstrated a marked increase in abnormal signal copy "
            "number (#7 at 5-fold and #8 at >4 fold), consistent with CNG of the "
            "ALK gene fusion"
        ),
        "statement_biomarker": "EML4::ALK Fusion AND ALK Amplification",
        "patients_named": ["patient_7", "patient_8"],
    },
    "resolution": (
        "lo statement copre il reperto CNG su due pazienti nominati, non il caso "
        "del solo paziente #8. Il CNG **isolato** — senza mutazione concomitante "
        "del dominio chinasico — poggia sul solo #8, perche' #7 portava anche "
        "G1269A. Nessun identificatore e' inventato: entrambi compaiono "
        "letteralmente nel locator verificato."
    ),
    "granularity_applied": GRANULARITY_NAMED_PATIENT_SUBSET,
    "case_identifier_invented": False,
    "author_approved": True,
}

REVISION_766 = StatementRevision(
    statement_id="ES-V2-evidence-766",
    previous_candidate_status="candidate_partial",
    first_review_status="candidate_partial",
    link_status="partial_link",
    supported_dimensions=("disease", "intervention", "clinical resistance context"),
    unsupported_dimensions=("population", "frequency", "biomarker_specificity"),
    rationale=(
        "il copy number gain e' documentato in due pazienti (#7 e #8) su quattordici. "
        "Non e' una proprieta' della coorte e non ne stima una frequenza. Il paziente "
        "#7 portava anche G1269A, quindi il CNG come meccanismo isolato poggia sul "
        "solo #8. In questa fonte non esiste alcun esperimento sul copy number gain: "
        "il supporto preclinico che la letteratura riporta viene da un'altra "
        "pubblicazione, qui citata."
    ),
    extra={
        "support_type": "direct_clinical_support",
        **constraints_for(GRANULARITY_NAMED_PATIENT_SUBSET),
        "population_scope": SCOPE_NAMED_PATIENTS_SUBSET,
        "subset_size": 2,
        "cohort_size": 14,
        "case_identifiers": ["patient_7", "patient_8"],
        "case_identifiers_verified": True,
        "case_identifier_locators": ["A-clin-cng"],
        "isolated_cng_case_identifier": "patient_8",
        "isolated_cng_rationale": (
            "il paziente #7 portava anche G1269A: il CNG come meccanismo isolato "
            "resta documentato in un solo paziente"
        ),
        # Gli stessi due fatti in forma generica, perche' il costruttore delle
        # annotazioni non deve conoscere il nome di un biomarcatore per riportarli.
        "narrowest_case_identifier": "patient_8",
        "narrowest_case_rationale": (
            "uno dei due pazienti portava anche una mutazione del dominio chinasico: "
            "il meccanismo isolato resta documentato in un solo paziente"
        ),
        "preclinical_support_in_this_source": False,
        "non_propagation_rules": [
            "in_vitro_to_clinical_benefit",
            "case_report_to_population",
        ],
        "terminology_mapping_status": "requires_terminology_verification",
        "brief_discrepancy": dict(ES766_DISCREPANCY),
        "profile_unit_ids": [CLINICAL_COHORT_ID],
    },
)

STATEMENT_REVISIONS = (REVISION_4288, REVISION_764, REVISION_766)

CANDIDATE_VALID_COUNT = 1
CANDIDATE_PARTIAL_COUNT = 2
CASE_LEVEL_STATEMENT_COUNT = 1
NAMED_PATIENT_SUBSET_STATEMENT_COUNT = 1
NON_GENERALIZABLE_STATEMENT_COUNT = 2

# =============================================================================
# Terminologia
# =============================================================================

# Il mapping resta **non verificato**, e non perche' manchi il tempo di
# verificarlo: la fonte definisce il CNG come piu' del doppio delle copie medie,
# mentre «amplification» in oncologia ha una soglia diversa e piu' alta. Promuovere
# il mapping a sinonimo verificato userebbe il grafo come prova di se stesso.
TERMINOLOGY_MAPPING: Mapping[str, Any] = {
    "canonical_source_id": CANONICAL_SOURCE_ID,
    "statement_id": "ES-V2-evidence-766",
    "source_term": "copy number gain of the ALK gene fusion",
    "statement_term": "ALK Amplification",
    "mapping_type": "biomarker_strength_normalization",
    "mapping_status": "requires_terminology_verification",
    "literal_equivalence": False,
    "literal_string_present_in_source": False,
    "literal_string_present_for_exact_statement_term": False,
    "source_supports_broader_concept": True,
    "source_supports_exact_normalized_term": "not_verified",
    "uncertain_dimension": "biomarker_specificity",
    "promoted_to_verified_synonym": False,
    "kg_used_as_sole_authority": False,
    "mapping_source": "statement del KG, confrontato con la definizione della fonte",
    "source_locators": ["A-clin-cng"],
    "rationale": (
        "la fonte definisce il CNG come «piu' del doppio» delle copie medie; "
        "«amplification» ha in oncologia una soglia diversa e piu' alta, e la "
        "stringa non compare nel documento. Il grafo congelato non puo' essere "
        "l'unica autorita' della propria normalizzazione."
    ),
    "review_required": True,
    "supersedes_status": "requires_terminology_verification",
}

# =============================================================================
# Il rilevatore
# =============================================================================

CONFIRMED_MIXTURE = "confirmed_clinical_preclinical_mixture"

# Il principio che il caso stabilisce. Speculare a quello di PMID 31358542: la',
# un segnale presente senza evidenza propria; qui, evidenza propria presente ma
# contata male. Vedere la struttura e contarne le parti sono due capacita'
# diverse, e nessuna soglia converte la prima nella seconda.
DETECTOR_PRINCIPLE = "detecting_a_mixture != counting_its_parts"

DETECTOR_REFERENCE_CASE: Mapping[str, Any] = {
    "detector_reference_case": True,
    "reference_case_type": CONFIRMED_MIXTURE,
    "detector_original_verdict": "split_required",
    "reviewed_verdict": "split_required_with_more_units",
    "reference_case_status": "first_review_confirmed",
    "use_as_regression_case": True,
    "use_for_detector_performance_estimation": False,
    "detector_presence_signal_correct": True,
    "detector_granularity_prediction_correct": False,
    "detector_promoted": False,
    "detector_predicted_unit_count": AUDIT_PROPOSED_UNITS,
    "source_review_proposed_unit_count": SOURCE_REVIEW_PROPOSED_UNITS,
    "author_approved_unit_count": AUTHOR_APPROVED_UNITS,
    "principle": DETECTOR_PRINCIPLE,
    "correct_signals": [
        "preclinical.baf3",
        "preclinical.cell_lines",
        "preclinical.in_vitro",
        "clinical.patients",
        "clinical.phase",
    ],
    "wrong_signals": [],
    "missing_signals": ["molteplicita' dei modelli preclinici"],
    "own_preclinical_methods_present": True,
    "own_preclinical_figures_present": True,
    "own_preclinical_results_present": True,
    "rationale": (
        "il rilevatore ha visto entrambe le componenti, e le ha viste bene. Non ha "
        "visto che i sistemi preclinici erano piu' di uno, perche' nessun segnale "
        "conta i modelli distinti: il verdetto era giusto, il numero no. Un caso "
        "positivo confermato non promuove il rilevatore — un solo caso non misura "
        "nulla — e una previsione di struttura corretta con granularita' sbagliata "
        "e' il modo in cui questo rilevatore fallisce quando ha ragione."
    ),
}

# =============================================================================
# Limiti
# =============================================================================

LIMITATIONS = (
    "la revisione e' documentale e non clinica: l'autore non e' un clinico",
    "la preparazione del materiale e' assistita da LLM, quindi la prima revisione "
    "non e' indipendente",
    "il numero esatto di pazienti per ciascun meccanismo si legge nelle tabelle, "
    "non nel testo corrente: i conteggi qui registrati vengono dalle frasi ancorate "
    "a locator",
    "la perdita del riarrangiamento di ALK in CUTO-1 e' asserita dalla revisione "
    "source-checked e non ancorata a un locator proprio",
    "il mapping copy number gain / amplification resta non verificato: nessuna "
    "soglia condivisa e' stata confrontata",
    "un solo caso non permette di stimare precision, recall o accuratezza del "
    "rilevatore",
    "le osservazioni su singoli pazienti restano dentro l'unita' della coorte: la "
    "granularita' le distingue, ma non esiste una unita' separata per ciascuna",
)

RESIDUAL_RISK = (
    "la coorte clinica contiene osservazioni a livello di singolo paziente (#9 per "
    "EGFR, #8 per il CNG isolato) che non sono proprieta' della coorte. La "
    "granularita' dichiarata le protegge; una lettura che la ignorasse le "
    "propagherebbe."
)

# Guardia di coerenza del modulo: se qualcuno cambia la decisione senza cambiare
# il vocabolario, il fallimento e' all'import e non tre artefatti piu' tardi.
if AUTHOR_DECISION not in AUTHOR_DECISIONS:  # pragma: no cover - invariante
    raise RuntimeError(f"decisione non ammessa: {AUTHOR_DECISION!r}")
if len(APPROVED_UNITS) != AUTHOR_APPROVED_UNITS:  # pragma: no cover - invariante
    raise RuntimeError("il numero di unita' approvate non coincide con la decisione")
