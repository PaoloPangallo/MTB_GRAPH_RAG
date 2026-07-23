"""Reperti della lettura delle tre fonti primarie.

Questo modulo contiene **cio' che le fonti dicono**, letto sui documenti e
ancorato a locator citabili. Non contiene inferenze sul gold, non guarda le
terapie attese e non conosce il clinical gold.

La separazione dai programmi e' deliberata. Uno script puo' verificare che un
locator esista nel documento e puo' contare le unita' proposte; non puo'
stabilire che le cellule Ba/F3 e le cellule NIH3T3 siano due modelli distinti,
ne' che una frase contenente «in vitro» stia citando il lavoro di altri invece
di descrivere un esperimento proprio. Quella distinzione qui e' scritta a mano
dopo aver letto le fonti, e ogni affermazione porta il locator che la sostiene.

Ogni `query` di locator e' stata verificata come corrispondenza esatta nel
documento normalizzato prima di essere scritta qui.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from backend.pipeline.evidence.profile_unit import (
    NOT_APPLICABLE,
    UNIT_TYPE_CLINICAL_CASE,
    UNIT_TYPE_CLINICAL_COHORT,
    UNIT_TYPE_PRECLINICAL_COMPARATIVE,
    UNIT_TYPE_PRECLINICAL_ENGINEERED,
    UNIT_TYPE_PRECLINICAL_PATIENT_DERIVED,
    UNKNOWN,
)
from benchmarks.mtb_evidence.evaluation.clinical_preclinical_review import (
    AUDIT_SPLIT_CONFIRMED_MORE,
    AUDIT_SPLIT_NOT_SUPPORTED,
    AUDIT_SPLIT_PARTIALLY_SUPPORTED,
    CANDIDATE_AMBIGUOUS,
    CANDIDATE_PARTIAL,
    CANDIDATE_VALID,
    CLINICAL_WITH_PRECLINICAL_VALIDATION,
    DIRECT_CLINICAL_SUPPORT,
    MAPPING_REQUIRES_VERIFICATION,
    MATCH_EXACT,
)


@dataclass(frozen=True)
class Locator:
    """Una frase della fonte che sostiene una affermazione dell'audit."""

    locator_id: str
    query: str
    section_hint: str
    expected_match: str = MATCH_EXACT
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "locator_id": self.locator_id,
            "query": self.query,
            "section_hint": self.section_hint,
            "expected_match": self.expected_match,
            "note": self.note,
        }


@dataclass(frozen=True)
class ProposedUnit:
    """Una unita' epistemica che la fonte sostiene.

    I campi assenti non sono omessi: `unknown` dice che la fonte potrebbe averlo
    detto e non l'ha detto (o non l'abbiamo letto), `not_applicable` dice che la
    domanda non si pone per questo tipo di unita'.
    """

    unit_id: str
    unit_type: str
    label: str
    locator_ids: tuple[str, ...]
    statement_candidates: tuple[str, ...] = ()
    disease: str = UNKNOWN
    biomarker_requirements: tuple[str, ...] = ()
    intervention: tuple[str, ...] = ()
    comparator: str = UNKNOWN
    population: str = UNKNOWN
    evidence_design: str = UNKNOWN
    therapy_line: str = UNKNOWN
    prior_therapies: tuple[str, ...] = ()
    n_subjects: str = UNKNOWN
    model_type: str = NOT_APPLICABLE
    cell_line: tuple[str, ...] = ()
    assay: str = NOT_APPLICABLE
    endpoint: str = UNKNOWN
    outcomes: str = UNKNOWN
    resistance_qualifier: str = UNKNOWN
    not_separable: tuple[str, ...] = ()
    rationale: str = ""


@dataclass(frozen=True)
class StatementFinding:
    """A quale unita' appartiene uno statement, e con quale forza."""

    statement_id: str
    proposed_unit_ids: tuple[str, ...]
    support_type: str
    candidate_link_status: str
    directness: str
    clinical_support: str
    preclinical_support: str
    locator_ids: tuple[str, ...]
    conflict_dimensions: tuple[str, ...] = ()
    non_propagation_rules: tuple[str, ...] = ()
    rationale: str = ""


@dataclass(frozen=True)
class TerminologyFinding:
    """Una differenza fra il termine della fonte e quello dello statement."""

    original_source_term: str
    normalized_term: str
    mapping_type: str
    mapping_source: str
    mapping_status: str
    literal_string_present: bool
    review_required: bool
    locator_ids: tuple[str, ...] = ()
    rationale: str = ""


@dataclass(frozen=True)
class SourceFinding:
    """Tutto cio' che la lettura di una fonte ha stabilito."""

    parent_unit_id: str
    canonical_source_id: str
    pmid: str
    pmc_id: str
    availability: str
    decision: str
    decision_rationale: str
    audit_unit_count: int
    document_map: Mapping[str, Any]
    answers: Mapping[str, str]
    locators: tuple[Locator, ...]
    units: tuple[ProposedUnit, ...] = ()
    statements: tuple[StatementFinding, ...] = ()
    terminology: tuple[TerminologyFinding, ...] = ()
    shared_dimensions: tuple[str, ...] = ()
    not_separable_dimensions: tuple[str, ...] = ()
    residual_risk: str = ""
    limitations: tuple[str, ...] = ()

    @property
    def reviewed_unit_count(self) -> int:
        return len(self.units)


# =============================================================================
# PMID 22235099 — Doebele et al., Clin Cancer Res 2012 (PMC3311875)
# «Mechanisms of Resistance to Crizotinib in Patients with ALK Gene Rearranged
# Non-Small Cell Lung Cancer»
#
# L'audit aveva proposto due unita'. Il full text ne mostra cinque: una coorte
# clinica e **quattro** sistemi preclinici distinti, che rispondono a domande
# diverse e usano fondi cellulari diversi. Fonderli in una unita' «preclinica»
# farebbe sembrare che l'esperimento su KRAS abbia mostrato resistenza, mentre
# ha mostrato il contrario.
# =============================================================================

_A_LOCATORS = (
    Locator(
        "A-clin-cohort",
        "Fourteen ALK + patients underwent 15 re-biopsy procedures",
        "Results / Re-biopsy of patients following progression on crizotinib",
    ),
    Locator(
        "A-clin-evaluable",
        "Eleven patients had material evaluable for molecular analysis",
        "Abstract / Results",
    ),
    Locator(
        "A-clin-g1269a",
        "Two patients (#6 and 7) demonstrated the presence of a novel mutation that encodes a G1269A substitution",
        "Results / ALK kinase domain mutations",
    ),
    Locator(
        "A-clin-cng",
        "Two patients demonstrated a marked increase in abnormal signal copy number",
        "Results / Copy number gain of the ALK gene rearrangement",
    ),
    Locator(
        "A-clin-egfr",
        "demonstrated the presence of an EGFR exon 21 mutation encoding the L858R substitution",
        "Results / EGFR mutations as a mechanism of crizotinib resistance",
    ),
    Locator(
        "A-pre-baf3",
        "Ba/F3 cells expressing wild-type EML4-ALK",
        "Figure 1 legend / Results",
        note="il modello ingegnerizzato su fondo Ba/F3, dipendente da IL-3",
    ),
    Locator(
        "A-pre-baf3-result",
        "The G1269A mutation induced crizotinib resistance that was intermediate between the previously identified mutations",
        "Results / ALK kinase domain mutations",
        note="risultato del saggio Ba/F3: resistenza intermedia, non completa",
    ),
    Locator(
        "A-pre-nih3t3",
        "Similar results were obtained when these constructs were introduced into the NIH3T3 cell line and colony formation was measured in soft agar",
        "Results / ALK kinase domain mutations",
    ),
    Locator(
        "A-pre-cuto1",
        "H3122, H2228, and CUTO-1 cells (from patient #10) were treated with the indicated concentration of crizotinib",
        "Figure 3 legend",
    ),
    Locator(
        "A-pre-cuto1-origin",
        "Primary cell lines were derived from patients by placing fresh tumor tissue",
        "Materials and Methods / Cell lines and Reagents",
    ),
    Locator(
        "A-pre-kras",
        "H3122 cells with expression of KRAS G12V or empty vector were treated with the indicated concentration of crizotinib",
        "Figure 3 legend",
    ),
    Locator(
        "A-pre-kras-negative",
        "was not significantly different from H3122 harboring the empty vector",
        "Results / KRAS mutations as a mechanism for crizotinib resistance",
        note="esito negativo: l'esperimento non riproduce resistenza",
    ),
)

_A_UNITS = (
    ProposedUnit(
        "PU-PMID-22235099-clinical-cohort",
        UNIT_TYPE_CLINICAL_COHORT,
        "coorte clinica: 14 pazienti ALK+ ri-biopsiati alla progressione su crizotinib",
        ("A-clin-cohort", "A-clin-evaluable"),
        statement_candidates=(
            "ES-V2-evidence-4288",
            "ES-V2-evidence-764",
            "ES-V2-evidence-766",
        ),
        disease="Lung Non-small Cell Carcinoma",
        biomarker_requirements=("ALK gene rearrangement",),
        intervention=("crizotinib",),
        population="pazienti ALK+ NSCLC con progressione radiologica in corso di crizotinib",
        evidence_design="serie osservazionale di ri-biopsie entro uno studio di fase I",
        n_subjects="14 ri-biopsiati, 11 con materiale valutabile",
        outcomes="tempo mediano su crizotinib 8.9 mesi (range 3.8-21.1) prima della progressione",
        rationale=(
            "l'arruolamento richiedeva il riarrangiamento di ALK; le alterazioni di "
            "resistenza sono reperti successivi e non criteri di inclusione"
        ),
    ),
    ProposedUnit(
        "PU-PMID-22235099-baf3-engineered",
        UNIT_TYPE_PRECLINICAL_ENGINEERED,
        "Ba/F3 con EML4-ALK wild-type e mutanti G1269A, C1156Y, L1196M",
        ("A-pre-baf3", "A-pre-baf3-result"),
        statement_candidates=("ES-V2-evidence-764",),
        disease=NOT_APPLICABLE,
        intervention=("crizotinib",),
        comparator="EML4-ALK wild-type e vettore vuoto",
        model_type="linea cellulare murina ingegnerizzata (Ba/F3)",
        cell_line=("Ba/F3",),
        assay="proliferazione a 72 ore, IC50",
        endpoint="cellule vitali rispetto al controllo non trattato",
        evidence_design="farmacologia in vitro su modello isogenico",
        resistance_qualifier="resistenza relativa, intermedia fra C1156Y e L1196M",
        rationale=(
            "e' il sistema che valida G1269A come mutazione di resistenza; il fondo "
            "Ba/F3 dipende da IL-3 e non e' un modello di NSCLC"
        ),
    ),
    ProposedUnit(
        "PU-PMID-22235099-nih3t3-engineered",
        UNIT_TYPE_PRECLINICAL_ENGINEERED,
        "NIH3T3 con gli stessi costrutti EML4-ALK: crescita in soft agar e immunoblot",
        ("A-pre-nih3t3",),
        statement_candidates=("ES-V2-evidence-764",),
        disease=NOT_APPLICABLE,
        intervention=("crizotinib",),
        comparator="EML4-ALK wild-type e vettore vuoto",
        model_type="fibroblasti murini ingegnerizzati (NIH3T3)",
        cell_line=("NIH3T3",),
        assay="formazione di colonie in soft agar; immunoblot di ALK, ERK, STAT3, AKT fosforilati",
        endpoint="conta delle colonie; livelli di fosforilazione",
        evidence_design="crescita ancoraggio-indipendente e analisi molecolare in vitro",
        rationale=(
            "fondo cellulare e saggio diversi da Ba/F3: la conferma vale perche' sono "
            "due sistemi, e fonderli la farebbe contare una volta sola"
        ),
    ),
    ProposedUnit(
        "PU-PMID-22235099-cuto1-comparative",
        UNIT_TYPE_PRECLINICAL_COMPARATIVE,
        "CUTO-1 (derivata dal paziente #10) confrontata con H3122 e H2228",
        ("A-pre-cuto1", "A-pre-cuto1-origin"),
        disease=NOT_APPLICABLE,
        intervention=("crizotinib",),
        comparator="H3122 e H2228, linee EML4-ALK positive note",
        model_type="linea derivata dal paziente confrontata con linee di riferimento",
        cell_line=("CUTO-1", "H3122", "H2228"),
        assay="proliferazione a 72 ore",
        endpoint="cellule vitali rispetto al controllo non trattato",
        evidence_design="farmacologia comparativa in vitro",
        resistance_qualifier="resistenza marcata rispetto alle due linee di riferimento",
        rationale=(
            "deriva da un paziente della coorte ma non e' il paziente: ha perso il "
            "riarrangiamento di ALK e porta KRAS G12C"
        ),
    ),
    ProposedUnit(
        "PU-PMID-22235099-h3122-kras-engineered",
        UNIT_TYPE_PRECLINICAL_ENGINEERED,
        "H3122 con KRAS G12V introdotto, contro vettore vuoto",
        ("A-pre-kras", "A-pre-kras-negative"),
        disease=NOT_APPLICABLE,
        intervention=("crizotinib",),
        comparator="H3122 con vettore vuoto",
        model_type="linea NSCLC EML4-ALK positiva ingegnerizzata",
        cell_line=("H3122",),
        assay="proliferazione a 72 ore, IC50",
        endpoint="IC50 rispetto al vettore vuoto",
        evidence_design="farmacologia in vitro su modello isogenico",
        resistance_qualifier="nessuna resistenza indotta: IC50 non diversa dal controllo",
        rationale=(
            "esito **negativo**, e per questo va tenuto separato: fuso in una unita' "
            "preclinica unica farebbe sembrare che l'esperimento su KRAS abbia "
            "mostrato resistenza, mentre argomenta contro"
        ),
    ),
)

_A_STATEMENTS = (
    StatementFinding(
        "ES-V2-evidence-764",
        (
            "PU-PMID-22235099-clinical-cohort",
            "PU-PMID-22235099-baf3-engineered",
            "PU-PMID-22235099-nih3t3-engineered",
        ),
        CLINICAL_WITH_PRECLINICAL_VALIDATION,
        CANDIDATE_VALID,
        "direct",
        "due pazienti (#6, #7) con G1269A alla progressione su crizotinib",
        "Ba/F3 e NIH3T3 con il costrutto G1269A mostrano resistenza al crizotinib",
        ("A-clin-g1269a", "A-pre-baf3-result", "A-pre-nih3t3"),
        non_propagation_rules=(
            "relative_versus_complete_resistance",
            "clinical_population_to_model",
        ),
        rationale=(
            "e' l'unico dei sette statement in cui osservazione clinica e validazione "
            "funzionale coesistono nella stessa fonte. La resistenza mostrata in vitro "
            "e' pero' **intermedia**, non completa, e lo statement non lo dice"
        ),
    ),
    StatementFinding(
        "ES-V2-evidence-766",
        ("PU-PMID-22235099-clinical-cohort",),
        DIRECT_CLINICAL_SUPPORT,
        CANDIDATE_PARTIAL,
        "direct",
        "due pazienti (#7, #8) con aumento del numero di copie del riarrangiamento",
        "nessuno: in questa fonte non esiste un esperimento sul copy number gain",
        ("A-clin-cng",),
        conflict_dimensions=("biomarker",),
        non_propagation_rules=("in_vitro_to_clinical_benefit", "case_report_to_population"),
        rationale=(
            "il supporto preclinico al CNG che la letteratura riporta e' di un'altra "
            "pubblicazione, citata qui. Inoltre uno dei due pazienti (#7) portava "
            "anche G1269A, quindi il CNG isolato si appoggia a un solo paziente"
        ),
    ),
    StatementFinding(
        "ES-V2-evidence-4288",
        ("PU-PMID-22235099-clinical-cohort",),
        DIRECT_CLINICAL_SUPPORT,
        CANDIDATE_PARTIAL,
        "direct",
        "un paziente (#9) con EGFR L858R comparso alla progressione",
        "nessuno in questa fonte",
        ("A-clin-egfr",),
        conflict_dimensions=("population",),
        non_propagation_rules=("case_report_to_population",),
        rationale=(
            "un solo paziente, e la lesione ri-biopsiata aveva perso il riarrangiamento "
            "di ALK. Trattarlo come proprieta' della coorte estenderebbe a 14 pazienti "
            "cio' che si e' visto in uno"
        ),
    ),
)

_A_TERMINOLOGY = (
    TerminologyFinding(
        "copy number gain (CNG) of the ALK gene fusion",
        "ALK Amplification",
        "concept_broadening",
        "statement del KG",
        MAPPING_REQUIRES_VERIFICATION,
        literal_string_present=False,
        review_required=True,
        locator_ids=("A-clin-cng",),
        rationale=(
            "la fonte definisce il CNG come «piu' del doppio» delle copie medie; "
            "«amplification» ha in oncologia una soglia diversa e piu' alta. Non sono "
            "sinonimi verificati e la stringa «amplification» non compare"
        ),
    ),
)

FINDING_22235099 = SourceFinding(
    parent_unit_id="PU-PMID-22235099-cohort-1",
    canonical_source_id="PMID:22235099",
    pmid="22235099",
    pmc_id="PMC3311875",
    availability="full_text",
    decision=AUDIT_SPLIT_CONFIRMED_MORE,
    decision_rationale=(
        "lo split clinico/preclinico e' confermato, ma due unita' non bastano: la "
        "componente preclinica sono quattro sistemi distinti, con fondi cellulari e "
        "saggi diversi, e uno di essi ha dato esito negativo"
    ),
    audit_unit_count=2,
    document_map={
        "study_objective": "definire i meccanismi molecolari di resistenza al crizotinib in NSCLC ALK+",
        "clinical_cohorts": ["14 pazienti ALK+ ri-biopsiati alla progressione, 11 valutabili"],
        "arms": [],
        "subgroups": ["resistenza intrinseca (2 pazienti)", "resistenza acquisita (12 pazienti)"],
        "population": "NSCLC ALK+ trattati con crizotinib in uno studio di fase I",
        "selection_criteria": "riarrangiamento di ALK accertato con FISH break-apart",
        "treatments_administered": ["crizotinib"],
        "prior_therapies": [UNKNOWN],
        "samples_and_biopsies": [
            "15 procedure di ri-biopsia",
            "FFPE, tessuto congelato, tessuto per l'avvio di linee cellulari",
        ],
        "molecular_alterations": [
            "ALK L1196M",
            "ALK G1269A",
            "copy number gain del riarrangiamento di ALK",
            "EGFR L858R",
            "EGFR S768I",
            "KRAS G12C",
            "KRAS G12V",
            "variante di fusione EML4-ALK E6;A19",
        ],
        "cell_models": ["Ba/F3", "NIH3T3", "H3122", "H2228", "CUTO-1", "293T"],
        "animal_models": [],
        "drugs_tested_in_vitro": ["crizotinib"],
        "drugs_tested_in_vivo": [],
        "molecular_analyses": ["FISH", "RT-PCR", "sequenziamento diretto", "SNaPshot", "STR", "immunoblot"],
        "pharmacological_analyses": ["proliferazione con IC50", "colonie in soft agar"],
        "clinical_outcomes": ["tempo mediano su crizotinib 8.9 mesi (range 3.8-21.1)"],
        "preclinical_endpoints": ["IC50", "conta delle colonie", "livelli di fosfoproteine"],
        "figures_and_tables": [
            "Figure 1A-F",
            "Figure 2A-D",
            "Figure 3A-B",
            "Figure 4A-B",
            "Table 1",
            "Table 2",
            "Supplemental Figures S1-S5",
            "Supplemental Table S1",
        ],
    },
    answers={
        "clinical_part": "la serie di 14 pazienti ri-biopsiati e le analisi molecolari sui loro campioni",
        "preclinical_part": "quattro sistemi: Ba/F3 ingegnerizzate, NIH3T3 ingegnerizzate, CUTO-1 contro H3122 e H2228, H3122 con KRAS G12V",
        "preclinical_validates_clinical": "si', per G1269A: la mutazione e' vista in due pazienti e poi validata su Ba/F3 e NIH3T3",
        "independent_preclinical_experiments": "si': il confronto di fitness fra mutanti e il costrutto C1156Y non corrispondono a nessun paziente della coorte",
        "lab_drugs_given_to_patients": "si', crizotinib in entrambi i contesti; nessun altro farmaco e' stato testato in laboratorio",
        "alterations_enrolment_or_finding": "il riarrangiamento di ALK era requisito di arruolamento; tutte le alterazioni di resistenza sono reperti successivi",
        "clinical_only_dimensions": "linea di terapia, setting, stadio, stato di resezione, terapie precedenti, tempo in trattamento",
        "model_only_dimensions": "identita' della linea cellulare, costrutto, dipendenza da IL-3, IC50, conta delle colonie, saggio",
        "statements_fuse_levels": "si': ES-V2-evidence-764 fonde l'osservazione clinica e la validazione funzionale in un solo statement",
        "directly_supported_statements": "tutti e tre sul piano clinico; solo ES-V2-evidence-764 anche sul piano preclinico",
    },
    locators=_A_LOCATORS,
    units=_A_UNITS,
    statements=_A_STATEMENTS,
    terminology=_A_TERMINOLOGY,
    shared_dimensions=("canonical_source_id", "intervention"),
    not_separable_dimensions=(),
    residual_risk=(
        "la coorte clinica contiene osservazioni a livello di singolo paziente "
        "(#9 per EGFR, #8 per il CNG isolato) che non sono proprieta' della coorte"
    ),
    limitations=(
        "il numero esatto di pazienti per ciascun meccanismo si legge nelle tabelle, "
        "non nel testo corrente",
    ),
)


# =============================================================================
# PMID 23344087 — Kim et al., J Thorac Oncol 2013
# «Heterogeneity of genetic changes associated with acquired crizotinib
# resistance in ALK-rearranged lung cancer»
#
# Full text non accessibile: Europe PMC lo dichiara «Subscription required», non
# e' in PMC ne' open access. La verifica si ferma all'abstract strutturato, che
# pero' nomina esplicitamente entrambe le componenti.
# =============================================================================

_B_LOCATORS = (
    Locator(
        "B-clin-cohort",
        "Tumor samples were derived from seven ALK-positive NSCLC patients who showed acquired resistance to crizotinib",
        "Abstract / Methods",
    ),
    Locator(
        "B-clin-mutations",
        "Three patients harbored secondary ALK mutations, including one patient with both mutations",
        "Abstract / Results",
    ),
    Locator(
        "B-clin-cng",
        "one patient displayed ALK gene copy number gain",
        "Abstract / Results",
        note="un solo paziente, che portava anche EGFR L858R con polisomia elevata",
    ),
    Locator(
        "B-pre-design",
        "In vitro cytotoxicity of crizotinib and ALK downstream signals were compared between crizotinib-naive and -resistant NSCLC cells",
        "Abstract / Methods",
    ),
    Locator(
        "B-pre-snu2535",
        "SNU-2535 cells derived from a patient who harbored the G1269 mutation were resistant to crizotinib treatment",
        "Abstract / Results",
    ),
    Locator(
        "B-pre-clones",
        "L1196M and G1269A mutant clones were less sensitive to crizotinib",
        "Abstract / Results",
        note="«less sensitive»: riduzione relativa di sensibilita', non resistenza completa",
    ),
)

_B_UNITS = (
    ProposedUnit(
        "PU-PMID-23344087-clinical-cohort",
        UNIT_TYPE_CLINICAL_COHORT,
        "coorte clinica: 7 pazienti ALK+ con resistenza acquisita al crizotinib",
        ("B-clin-cohort", "B-clin-mutations", "B-clin-cng"),
        statement_candidates=("ES-V2-evidence-765", "ES-V2-evidence-767"),
        disease="Lung Non-small Cell Carcinoma",
        biomarker_requirements=("ALK gene rearrangement",),
        intervention=("crizotinib",),
        population="pazienti ALK+ NSCLC con resistenza acquisita al crizotinib",
        evidence_design="serie osservazionale su campioni tumorali",
        n_subjects="7",
        outcomes="resistenza acquisita dopo una mediana di 6 mesi (range 4-12)",
        not_separable=("therapy_line", "setting", "stage"),
        rationale="l'abstract non descrive linea, setting ne' stadio: non sono ignoti per caso, non sono proprio riportati",
    ),
    ProposedUnit(
        "PU-PMID-23344087-patient-derived",
        UNIT_TYPE_PRECLINICAL_PATIENT_DERIVED,
        "SNU-2535, derivata da un paziente con mutazione G1269, contro H3122 CR1",
        ("B-pre-snu2535", "B-pre-design"),
        statement_candidates=("ES-V2-evidence-765",),
        disease=NOT_APPLICABLE,
        intervention=("crizotinib",),
        comparator="H3122 CR1, linea resistente di riferimento",
        model_type="linea derivata dal paziente",
        cell_line=("SNU-2535", "H3122 CR1"),
        assay="citotossicita' in vitro",
        endpoint="sopravvivenza cellulare al crizotinib",
        evidence_design="farmacologia in vitro",
        resistance_qualifier="resistente, in modo simile alla linea resistente di riferimento",
    ),
    ProposedUnit(
        "PU-PMID-23344087-engineered-clones",
        UNIT_TYPE_PRECLINICAL_ENGINEERED,
        "cloni mutanti L1196M e G1269A",
        ("B-pre-clones", "B-pre-design"),
        statement_candidates=("ES-V2-evidence-765",),
        disease=NOT_APPLICABLE,
        intervention=("crizotinib",),
        model_type="cloni cellulari con mutazione introdotta",
        assay="citotossicita' in vitro e segnali a valle di ALK",
        endpoint="sensibilita' al crizotinib; soppressione dei segnali a valle",
        evidence_design="farmacologia in vitro su cloni mutanti",
        resistance_qualifier="**meno sensibili**: riduzione relativa, non resistenza completa",
        not_separable=("cell_line",),
        rationale=(
            "l'abstract nomina i cloni ma non il fondo cellulare su cui sono costruiti: "
            "sapere che esistono non basta per sapere che cosa sono"
        ),
    ),
)

_B_STATEMENTS = (
    StatementFinding(
        "ES-V2-evidence-765",
        (
            "PU-PMID-23344087-clinical-cohort",
            "PU-PMID-23344087-patient-derived",
            "PU-PMID-23344087-engineered-clones",
        ),
        CLINICAL_WITH_PRECLINICAL_VALIDATION,
        CANDIDATE_PARTIAL,
        "direct",
        "due pazienti con G1269A fra i sette con resistenza acquisita",
        "SNU-2535 (da paziente G1269) resistente; cloni G1269A meno sensibili",
        ("B-clin-mutations", "B-pre-snu2535", "B-pre-clones"),
        non_propagation_rules=("relative_versus_complete_resistance",),
        rationale=(
            "clinico e preclinico concordano, ma il preclinico dice «less sensitive». "
            "Lo statement dice «resistance»: la differenza non e' verificabile "
            "sull'abstract e va portata al revisore"
        ),
    ),
    StatementFinding(
        "ES-V2-evidence-767",
        ("PU-PMID-23344087-clinical-cohort",),
        DIRECT_CLINICAL_SUPPORT,
        CANDIDATE_AMBIGUOUS,
        "direct",
        "un solo paziente con copy number gain di ALK (4.1 volte)",
        "nessuno: nessun esperimento sul copy number gain",
        ("B-clin-cng",),
        conflict_dimensions=("biomarker", "population"),
        non_propagation_rules=("case_report_to_population",),
        rationale=(
            "lo stesso unico paziente portava anche EGFR L858R con polisomia elevata. "
            "Attribuire la resistenza al CNG di ALK sceglie una delle due spiegazioni "
            "senza che la fonte lo faccia"
        ),
    ),
)

_B_TERMINOLOGY = (
    TerminologyFinding(
        "ALK gene copy number gain",
        "ALK Amplification",
        "concept_broadening",
        "statement del KG",
        MAPPING_REQUIRES_VERIFICATION,
        literal_string_present=False,
        review_required=True,
        locator_ids=("B-clin-cng",),
        rationale="stesso scarto della fonte 22235099: la fonte dice copy number gain, lo statement dice amplification",
    ),
    TerminologyFinding(
        "less sensitive to crizotinib",
        "resistance",
        "strength_escalation",
        "statement del KG",
        MAPPING_REQUIRES_VERIFICATION,
        literal_string_present=False,
        review_required=True,
        locator_ids=("B-pre-clones",),
        rationale=(
            "una riduzione relativa di sensibilita' non e' una resistenza. La distanza "
            "fra le due formulazioni cambia che cosa si potrebbe raccomandare"
        ),
    ),
)

FINDING_23344087 = SourceFinding(
    parent_unit_id="PU-PMID-23344087-cohort-1",
    canonical_source_id="PMID:23344087",
    pmid="23344087",
    pmc_id="",
    availability="abstract_only",
    decision=AUDIT_SPLIT_PARTIALLY_SUPPORTED,
    decision_rationale=(
        "l'abstract nomina esplicitamente sia la coorte clinica sia gli esperimenti in "
        "vitro, quindi lo split e' sostenuto. Non e' sostenuta la **composizione** della "
        "parte preclinica: i cloni mutanti sono nominati senza il fondo cellulare, e "
        "senza full text la loro relazione con SNU-2535 resta indeterminata"
    ),
    audit_unit_count=2,
    document_map={
        "study_objective": "identificare le alterazioni genetiche associate alla resistenza al crizotinib",
        "clinical_cohorts": ["7 pazienti ALK+ con resistenza acquisita al crizotinib"],
        "arms": [],
        "subgroups": ["5 pazienti con versamento pleurico maligno analizzato per anfiregulina"],
        "population": "NSCLC ALK+ con risposta iniziale e successiva resistenza al crizotinib",
        "selection_criteria": UNKNOWN,
        "treatments_administered": ["crizotinib"],
        "prior_therapies": [UNKNOWN],
        "samples_and_biopsies": ["campioni tumorali", "versamento pleurico"],
        "molecular_alterations": [
            "ALK L1196M (n=2)",
            "ALK G1269A (n=2)",
            "copy number gain di ALK (4.1 volte, n=1)",
            "EGFR L858R con polisomia elevata (n=1)",
        ],
        "cell_models": ["SNU-2535", "H3122 CR1", "cloni mutanti L1196M e G1269A"],
        "animal_models": [],
        "drugs_tested_in_vitro": ["crizotinib"],
        "drugs_tested_in_vivo": [],
        "molecular_analyses": [
            "analisi di mutazioni ALK, EGFR, KRAS",
            "amplificazioni geniche di ALK ed EGFR",
            "segnali a valle di ALK",
        ],
        "pharmacological_analyses": ["citotossicita' in vitro del crizotinib"],
        "clinical_outcomes": ["resistenza acquisita dopo mediana di 6 mesi (range 4-12)"],
        "preclinical_endpoints": ["sopravvivenza cellulare", "soppressione dei segnali a valle"],
        "figures_and_tables": ["non osservabili: solo abstract"],
    },
    answers={
        "clinical_part": "i 7 pazienti con resistenza acquisita e le analisi sui loro campioni",
        "preclinical_part": "la citotossicita' in vitro su SNU-2535, H3122 CR1 e i cloni mutanti",
        "preclinical_validates_clinical": "si' per G1269: SNU-2535 viene da un paziente che portava quella mutazione",
        "independent_preclinical_experiments": "non determinabile sull'abstract",
        "lab_drugs_given_to_patients": "si', crizotinib in entrambi i contesti",
        "alterations_enrolment_or_finding": "il riarrangiamento di ALK precede il trattamento; le mutazioni di resistenza sono reperti successivi",
        "clinical_only_dimensions": "linea di terapia, setting, stadio; nessuna e' riportata",
        "model_only_dimensions": "identita' della linea, clone, saggio di citotossicita'",
        "statements_fuse_levels": "si': ES-V2-evidence-765 poggia su entrambi i piani",
        "directly_supported_statements": "entrambi sul piano clinico; solo ES-V2-evidence-765 anche sul piano preclinico",
    },
    locators=_B_LOCATORS,
    units=_B_UNITS,
    statements=_B_STATEMENTS,
    terminology=_B_TERMINOLOGY,
    shared_dimensions=("canonical_source_id", "intervention"),
    not_separable_dimensions=("preclinical_model_composition",),
    residual_risk=(
        "senza full text non e' possibile sapere quanti sistemi preclinici distinti "
        "esistano davvero, ne' su quale fondo cellulare siano costruiti i cloni"
    ),
    limitations=(
        "full text dichiarato «Subscription required» da Europe PMC: non e' in PMC, "
        "non e' open access, nessuna via pubblica di accesso",
        "figure e tabelle non osservabili",
    ),
)


# =============================================================================
# PMID 31358542 — Dagogo-Jack et al., Clin Cancer Res 2019 (PMC6858956)
# «Treatment with Next-Generation ALK Inhibitors Fuels Plasma ALK Mutation
# Diversity»
#
# Il reperto piu' importante del batch. L'audit l'aveva segnalata come
# clinico + preclinico. Il full text contiene **una sola** occorrenza di
# «in vitro», dentro una frase che cita il lavoro di altri. Nessuna linea
# cellulare, nessun xenograft, nessun IC50, nessuna trasfezione: la fonte e'
# interamente clinica, e lo split proposto non ha oggetto.
# =============================================================================

_C_LOCATORS = (
    Locator(
        "C-clin-cohort",
        "We analyzed 106 plasma specimens from 84 patients",
        "Abstract / Methods",
    ),
    Locator(
        "C-clin-g1202r",
        "The most frequently observed ALK mutation was G1202R, detected in 23 (33%) specimens",
        "Results / Resistance to Second-Generation ALK Inhibitors",
        note="il dato e' del gruppo aggregato dei TKI di seconda generazione",
    ),
    Locator(
        "C-clin-ceritinib",
        "At progression after 7 months on ceritinib, ALK V1180L cleared but ALK G1202R was detected",
        "Results",
        note="unico caso in cui G1202R e' legato per nome a ceritinib",
    ),
    Locator(
        "C-clin-brigatinib",
        "Six patients received alectinib followed by brigatinib",
        "Results",
        note="il sottogruppo brigatinib esiste, ma nessun caso G1202R gli e' attribuito per nome",
    ),
    Locator(
        "C-false-positive",
        "Based on in vitro models, a G1269A/I1171S compound mutation may re-sensitize to ceritinib or brigatinib",
        "Discussion",
        note=(
            "unica occorrenza di «in vitro» nella fonte, ed e' una citazione indiretta "
            "(riferimento 23). E' il segnale che ha acceso il falso positivo dell'audit"
        ),
    ),
)

_C_UNITS = (
    ProposedUnit(
        "PU-PMID-31358542-clinical-cohort",
        UNIT_TYPE_CLINICAL_COHORT,
        "coorte clinica: 84 pazienti ALK+ con 106 campioni di plasma",
        ("C-clin-cohort", "C-clin-g1202r"),
        statement_candidates=("ES-V2-evidence-100003", "ES-V2-evidence-100004"),
        disease="Non-Small Cell Lung Cancer",
        biomarker_requirements=("ALK rearrangement",),
        intervention=("ceritinib", "alectinib", "brigatinib", "lorlatinib"),
        population="pazienti con NSCLC ALK+ avanzato trattati con TKI di seconda e terza generazione",
        evidence_design="genotipizzazione su plasma con NGS, confronto con biopsia tissutale",
        n_subjects="84 pazienti, 106 campioni di plasma",
        therapy_line="successiva a crizotinib o a TKI di seconda generazione",
        outcomes="mutazione di ALK rilevata in 46 (66%) di 70 pazienti in progressione su TKI di seconda generazione",
        not_separable=("intervention",),
        rationale=(
            "gli interventi restano non separabili: il dato su G1202R e' riportato per "
            "il **gruppo aggregato** dei TKI di seconda generazione, non farmaco per "
            "farmaco. Separarli richiederebbe di attribuire numeri che la fonte non da'"
        ),
    ),
)

_C_STATEMENTS = (
    StatementFinding(
        "ES-V2-evidence-100004",
        ("PU-PMID-31358542-clinical-cohort",),
        DIRECT_CLINICAL_SUPPORT,
        CANDIDATE_PARTIAL,
        "direct",
        "un caso nominato: G1202R comparso alla progressione dopo 7 mesi di ceritinib",
        "nessuno: la fonte non contiene esperimenti preclinici",
        ("C-clin-ceritinib", "C-clin-g1202r"),
        non_propagation_rules=("cross_cohort_identity",),
        rationale=(
            "il legame con ceritinib esiste per nome in un caso; il dato di frequenza "
            "e' pero' del gruppo aggregato dei TKI di seconda generazione"
        ),
    ),
    StatementFinding(
        "ES-V2-evidence-100003",
        ("PU-PMID-31358542-clinical-cohort",),
        DIRECT_CLINICAL_SUPPORT,
        CANDIDATE_AMBIGUOUS,
        "direct",
        "nessun caso lega per nome G1202R alla progressione su brigatinib; il supporto e' del gruppo aggregato",
        "nessuno: la fonte non contiene esperimenti preclinici",
        ("C-clin-brigatinib", "C-clin-g1202r"),
        conflict_dimensions=("intervention",),
        non_propagation_rules=("cross_cohort_identity",),
        rationale=(
            "brigatinib compare come sottogruppo di sei pazienti, ma la frequenza di "
            "G1202R e' riportata per l'insieme dei TKI di seconda generazione. "
            "Attribuirla a brigatinib propaga una proprieta' del gruppo a un suo "
            "sottoinsieme"
        ),
    ),
)

FINDING_31358542 = SourceFinding(
    parent_unit_id="PU-PMID-31358542-cohort-1",
    canonical_source_id="PMID:31358542",
    pmid="31358542",
    pmc_id="PMC6858956",
    availability="full_text",
    decision=AUDIT_SPLIT_NOT_SUPPORTED,
    decision_rationale=(
        "la fonte non contiene evidenza preclinica. L'unica occorrenza di «in vitro» "
        "in tutto il full text sta in una frase che cita modelli di altri (riferimento "
        "23). Nessuna linea cellulare, nessun xenograft, nessun IC50, nessuna "
        "trasfezione: lo split clinico/preclinico proposto dall'audit non ha oggetto"
    ),
    audit_unit_count=2,
    document_map={
        "study_objective": "valutare l'utilita' della genotipizzazione su plasma per identificare mutazioni di resistenza ad ALK alla recidiva",
        "clinical_cohorts": ["84 pazienti, 106 campioni di plasma"],
        "arms": [],
        "subgroups": [
            "70 pazienti in progressione su TKI di seconda generazione",
            "29 pazienti in progressione su lorlatinib",
            "46 pazienti genotipizzati su plasma alla progressione su alectinib",
            "41 biopsie tissutali alla progressione su alectinib",
            "12 pazienti con plasma e tessuto appaiati",
            "6 pazienti alectinib seguito da brigatinib",
            "15 pazienti con lorlatinib dopo un TKI di seconda generazione",
            "19 pazienti con recidiva solo cerebrale o toracica",
        ],
        "population": "NSCLC ALK+ avanzato trattato con TKI di seconda e terza generazione",
        "selection_criteria": "riarrangiamento di ALK e trattamento con TKI di nuova generazione",
        "treatments_administered": ["ceritinib", "alectinib", "brigatinib", "lorlatinib"],
        "prior_therapies": ["crizotinib", "TKI di seconda generazione"],
        "samples_and_biopsies": ["plasma", "biopsie tissutali da lesioni resistenti"],
        "molecular_alterations": [
            "ALK G1202R",
            "ALK I1171X",
            "ALK L1196M",
            "ALK V1180L",
            "ALK D1203N",
            "mutazioni composte",
        ],
        "cell_models": [],
        "animal_models": [],
        "drugs_tested_in_vitro": [],
        "drugs_tested_in_vivo": [],
        "molecular_analyses": ["NGS su plasma (Guardant360)", "NGS mirato su tessuto"],
        "pharmacological_analyses": [],
        "clinical_outcomes": [
            "mutazione di ALK in 46 (66%) di 70 pazienti su TKI di seconda generazione",
            "mutazione di ALK in 22 (76%) di 29 pazienti su lorlatinib",
        ],
        "preclinical_endpoints": [],
        "figures_and_tables": [
            "Figure 1-4",
            "Table 1",
            "Supplementary Figure 1",
            "Supplementary Table 4",
        ],
    },
    answers={
        "clinical_part": "tutta la fonte",
        "preclinical_part": "nessuna",
        "preclinical_validates_clinical": "non applicabile: non esiste una parte preclinica",
        "independent_preclinical_experiments": "nessuno",
        "lab_drugs_given_to_patients": "non applicabile: nessun farmaco e' stato testato in laboratorio",
        "alterations_enrolment_or_finding": "il riarrangiamento di ALK precede il trattamento; le mutazioni di resistenza sono reperti alla recidiva",
        "clinical_only_dimensions": "tutte le dimensioni cliniche valgono per i pazienti; non c'e' un modello a cui potrebbero passare",
        "model_only_dimensions": "nessuna",
        "statements_fuse_levels": "no: entrambi gli statement sono clinici",
        "directly_supported_statements": "entrambi, ma il legame con il singolo farmaco e' piu' debole di quanto lo statement suggerisca",
    },
    locators=_C_LOCATORS,
    units=_C_UNITS,
    statements=_C_STATEMENTS,
    terminology=(),
    shared_dimensions=("canonical_source_id",),
    not_separable_dimensions=("intervention",),
    residual_risk=(
        "il rischio residuo non e' clinico/preclinico ma di sottogruppo: otto "
        "sottopopolazioni sovrapposte, e i dati aggregati per i TKI di seconda "
        "generazione possono essere attribuiti al singolo farmaco per errore"
    ),
    limitations=(),
)


FINDINGS: tuple[SourceFinding, ...] = (
    FINDING_22235099,
    FINDING_23344087,
    FINDING_31358542,
)

FINDINGS_BY_UNIT: dict[str, SourceFinding] = {
    finding.parent_unit_id: finding for finding in FINDINGS
}


def all_locators() -> list[tuple[str, Locator]]:
    """Tutti i locator del batch, con l'unita' di appartenenza."""
    return [
        (finding.parent_unit_id, locator)
        for finding in FINDINGS
        for locator in finding.locators
    ]
