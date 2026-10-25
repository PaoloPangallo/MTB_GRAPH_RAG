"""Prima revisione del pacchetto BA-22b14dbcbc62e29b — PMID 22277784.

Annotazione umana registrata come dato, sul modello di `reviewed_profiles.py`.

**Come questa revisione e' stata prodotta, e perche' e' scritto qui.**
E' stata approvata esplicitamente da Paolo Pangallo, autore della tesi, ma
preparata con assistenza di un modello linguistico. Non e' quindi una revisione
clinica, non e' indipendente, e non puo' entrare in nessuna metrica finale di
linking o di accordo. I campi di `REVIEW_METADATA` lo dicono in modo che nessun
artefatto a valle possa perderlo per strada.

Vale come **prima** annotazione. Serve una seconda revisione indipendente, e
preferibilmente clinica, prima che qualunque decisione qui dentro diventi gold.

**Che cosa la revisione ha stabilito.** La fonte descrive quattro cose diverse:
una coorte clinica di 18 pazienti con resistenza acquisita a crizotinib, e tre
serie di esperimenti su cellule Ba/F3 ingegnerizzate. Il profilo unico
`PU-PMID-22277784-cohort-1` le fondeva, e fonderle significa poter attribuire
la popolazione dei 18 pazienti a un esperimento in vitro, oppure il setting
preclinico ai pazienti. Da qui lo split in quattro unita'.
"""

from __future__ import annotations

from typing import Any

PACKET_ID = "BA-22b14dbcbc62e29b"
PMID = "22277784"
CANONICAL_SOURCE_ID = "PMID:22277784"
ORIGINAL_UNIT_ID = "PU-PMID-22277784-cohort-1"
REVIEW_VERSION = "first_review/1.0"

SOURCE_TITLE = (
    "Mechanisms of acquired crizotinib resistance in ALK-rearranged lung cancers."
)

REVIEW_METADATA: dict[str, Any] = {
    "packet_id": PACKET_ID,
    "review_round": "first_review",
    "reviewer_id": "paolo_pangallo",
    "reviewer_role": "thesis_author_non_clinical",
    "review_method": "human_approved_llm_assisted_source_review",
    "independent_review": False,
    "clinical_reviewer": False,
    "review_status": "first_review_complete",
    "requires_second_independent_review": True,
    "is_evaluable_for_final_metrics": False,
    "review_version": REVIEW_VERSION,
    "limitations": (
        "Revisione non indipendente e non clinica, preparata con assistenza LLM e "
        "approvata dall'autore della tesi. Utilizzabile come prima annotazione, "
        "non per metriche finali di linking o accordo."
    ),
}

# Decisione generale sull'unita' originale.
SPLIT_DECISION: dict[str, Any] = {
    "review_decision": "split_required",
    "cohort_resolution": "cohort_resolved_into_clinical_and_preclinical_units",
    "original_profile_unit_id": ORIGINAL_UNIT_ID,
    "original_profile_unit_status": "superseded_by_reviewed_split",
    "is_propagatable": False,
    "superseded_by": (
        "PU-PMID-22277784-clinical-crizotinib-resistant",
        "PU-PMID-22277784-baf3-crizotinib-panel",
        "PU-PMID-22277784-baf3-next-generation-alk-inhibitors",
        "PU-PMID-22277784-baf3-17aag",
    ),
    "rationale": (
        "La fonte descrive una coorte clinica e tre serie di esperimenti in vitro. "
        "Un profilo unico permetterebbe di attribuire la popolazione dei 18 pazienti "
        "a un esperimento su linee cellulari, o il setting preclinico ai pazienti."
    ),
}

# `value` None significa: nessun valore. `decision` dice **perche'**.
#   confirmed        — la fonte lo afferma
#   partial          — vero del contesto della fonte, non della popolazione studiata
#   unknown          — la fonte non lo afferma
#   not_applicable   — la domanda non si pone per questo tipo di unita'
UNITS: tuple[dict[str, Any], ...] = (
    {
        "profile_unit_id": "PU-PMID-22277784-clinical-crizotinib-resistant",
        "unit_type": "clinical_observational_cohort",
        "cohort_id": "clinical-crizotinib-resistant",
        "cohort_label": "coorte clinica con resistenza acquisita a crizotinib",
        "locators": ("L01-abstract", "L02-methods-results", "L03-table-1"),
        "fields": {
            "disease": {
                "value": "ALK-rearranged non-small cell lung cancer",
                "decision": "confirmed",
            },
            "biomarker_requirements": {
                "value": ("ALK-positive or ALK-rearranged NSCLC",),
                "decision": "confirmed",
                "note": "le mutazioni secondarie non erano requisiti di arruolamento",
            },
            "intervention": {
                "value": None,
                "decision": "not_applicable",
                "note": (
                    "studio osservazionale dei meccanismi di resistenza; crizotinib e' "
                    "terapia precedente, non intervento dello studio"
                ),
            },
            "regimen": {"value": None, "decision": "unknown"},
            "comparator": {"value": None, "decision": "not_applicable"},
            "population": {
                "value": "18 patients with ALK-positive NSCLC and acquired resistance to crizotinib",
                "decision": "confirmed",
            },
            "stage": {"value": None, "decision": "unknown"},
            "setting": {
                "value": "acquired resistance or progression during or after crizotinib treatment",
                "decision": "confirmed",
            },
            "therapy_line": {"value": None, "decision": "unknown"},
            "prior_therapies": {"value": ("crizotinib",), "decision": "confirmed"},
            "resection_status": {"value": None, "decision": "unknown"},
            "inclusion_criteria": {
                "value": (
                    "ALK-positive or ALK-rearranged NSCLC; "
                    "acquired resistance to crizotinib; "
                    "resistant tumor material available for molecular analysis"
                ),
                "decision": "confirmed_as_cohort_definition",
            },
            "exclusion_criteria": {"value": None, "decision": "unknown"},
            "evidence_design": {
                "value": (
                    "observational translational case series with molecular analysis "
                    "of resistant tumor samples"
                ),
                "decision": "confirmed",
            },
        },
        "do_not_propagate": ("stage", "therapy_line", "resection_status", "regimen"),
    },
    {
        "profile_unit_id": "PU-PMID-22277784-baf3-crizotinib-panel",
        "unit_type": "preclinical_in_vitro",
        "cohort_id": "baf3-crizotinib-panel",
        "cohort_label": "pannello Ba/F3 esposto a crizotinib",
        "locators": ("L04-figure-1CD", "L08-para-mutations-confer"),
        "fields": {
            "disease": {
                "value": "ALK-rearranged NSCLC",
                "decision": "partial",
                "note": "contesto oncologico della fonte, non popolazione sperimentale",
            },
            "biomarker_requirements": {
                "value": (
                    "EML4-ALK wild type",
                    "EML4-ALK L1196M",
                    "EML4-ALK G1202R",
                    "EML4-ALK S1206Y",
                    "EML4-ALK 1151Tins",
                ),
                "decision": "confirmed",
            },
            "intervention": {"value": ("crizotinib",), "decision": "confirmed"},
            "regimen": {"value": "single-agent in-vitro exposure", "decision": "confirmed"},
            "comparator": {
                "value": "wild-type EML4-ALK Ba/F3 cells; parental Ba/F3 cells",
                "decision": "confirmed",
            },
            "population": {"value": "engineered Ba/F3 cell models", "decision": "confirmed"},
            "stage": {"value": None, "decision": "not_applicable"},
            "setting": {
                "value": "preclinical acquired-resistance modelling",
                "decision": "confirmed",
            },
            "therapy_line": {"value": None, "decision": "not_applicable"},
            "prior_therapies": {"value": None, "decision": "not_applicable"},
            "resection_status": {"value": None, "decision": "not_applicable"},
            "inclusion_criteria": {"value": None, "decision": "not_applicable"},
            "exclusion_criteria": {"value": None, "decision": "not_applicable"},
            "evidence_design": {
                "value": "preclinical in-vitro cell viability and ALK-phosphorylation assays",
                "decision": "confirmed",
            },
        },
        "do_not_propagate": (),
    },
    {
        "profile_unit_id": "PU-PMID-22277784-baf3-next-generation-alk-inhibitors",
        "unit_type": "preclinical_in_vitro_comparative_pharmacology",
        "cohort_id": "baf3-next-generation-alk-inhibitors",
        "cohort_label": "pannello Ba/F3 esposto a inibitori ALK alternativi",
        "locators": ("L09-para-three-alk-inhibitors", "L05-figure-1E", "L06-supp-fig-S2"),
        "fields": {
            "disease": {"value": "ALK-rearranged NSCLC", "decision": "partial"},
            "biomarker_requirements": {
                "value": ("engineered mutant EML4-ALK panel",),
                "decision": "confirmed",
            },
            "intervention": {
                "value": ("NVP-TAE684", "CH5424802", "ASP-3026"),
                "decision": "confirmed",
            },
            "regimen": {"value": "separate single-agent in-vitro assays", "decision": "confirmed"},
            "comparator": {
                "value": "wild-type EML4-ALK Ba/F3 cells; parental Ba/F3 cells",
                "decision": "confirmed",
            },
            "population": {"value": "engineered Ba/F3 cell models", "decision": "confirmed"},
            "stage": {"value": None, "decision": "not_applicable"},
            "setting": {
                "value": "preclinical comparative drug-sensitivity modelling",
                "decision": "confirmed",
            },
            "therapy_line": {"value": None, "decision": "not_applicable"},
            "prior_therapies": {"value": None, "decision": "not_applicable"},
            "resection_status": {"value": None, "decision": "not_applicable"},
            "inclusion_criteria": {"value": None, "decision": "not_applicable"},
            "exclusion_criteria": {"value": None, "decision": "not_applicable"},
            "evidence_design": {
                "value": "comparative preclinical in-vitro pharmacologic assay",
                "decision": "confirmed",
            },
        },
        "do_not_propagate": (),
    },
    {
        "profile_unit_id": "PU-PMID-22277784-baf3-17aag",
        "unit_type": "preclinical_in_vitro",
        "cohort_id": "baf3-17aag",
        "cohort_label": "pannello Ba/F3 esposto a 17-AAG",
        "locators": ("L10-para-hsp90-clients", "L05-figure-1E", "L07-supp-fig-S3C"),
        "fields": {
            "disease": {"value": "ALK-rearranged NSCLC", "decision": "partial"},
            "biomarker_requirements": {
                "value": ("wild-type or mutant EML4-ALK",),
                "decision": "confirmed",
            },
            "intervention": {
                "value": ("17-AAG", "tanespimycin"),
                "decision": "confirmed",
                "note": "conservare il mapping fra nome sperimentale e nome normalizzato",
            },
            "regimen": {"value": "single-agent in-vitro exposure", "decision": "confirmed"},
            "comparator": {
                "value": "wild-type EML4-ALK Ba/F3 cells; parental Ba/F3 cells",
                "decision": "confirmed",
            },
            "population": {"value": "engineered Ba/F3 cell models", "decision": "confirmed"},
            "stage": {"value": None, "decision": "not_applicable"},
            "setting": {"value": "preclinical drug-sensitivity modelling", "decision": "confirmed"},
            "therapy_line": {"value": None, "decision": "not_applicable"},
            "prior_therapies": {"value": None, "decision": "not_applicable"},
            "resection_status": {"value": None, "decision": "not_applicable"},
            "inclusion_criteria": {"value": None, "decision": "not_applicable"},
            "exclusion_criteria": {"value": None, "decision": "not_applicable"},
            "evidence_design": {
                "value": "preclinical in-vitro viability and protein-expression assay",
                "decision": "confirmed",
            },
        },
        "do_not_propagate": (),
    },
)

# Mapping fra codice di sviluppo e nome normalizzato.
#
# `CH5424802` e' il codice con cui la fonte del 2012 chiama il composto poi
# denominato alectinib. Il mapping e' plausibile e ampiamente accettato, ma
# **non e' verificato su una terminologia controllata in questo repository**, e
# la stringa «alectinib hydrochloride» che compare nel grafo V2 non e' presente
# nella fonte. Registrarlo come equivalenza silenziosa farebbe apparire una
# risposta clinica ad alectinib dove esiste un esperimento in vitro su CH5424802.
INTERVENTION_MAPPINGS: tuple[dict[str, Any], ...] = (
    {
        "source_term": "CH5424802",
        "mapped_term": "alectinib",
        "graph_term": "alectinib hydrochloride",
        "mapping_type": "synonym_or_development_code_mapping",
        "mapping_status": "requires_source_or_terminology_verification",
        "literal_string_present_in_source": False,
        "note": (
            "la fonte usa il codice di sviluppo; ne' «alectinib» ne' «alectinib "
            "hydrochloride» compaiono come stringa letterale"
        ),
    },
    {
        "source_term": "17-AAG",
        "mapped_term": "tanespimycin",
        "graph_term": "tanespimycin",
        "mapping_type": "synonym_or_development_code_mapping",
        "mapping_status": "requires_source_or_terminology_verification",
        "literal_string_present_in_source": False,
        "note": "la fonte usa il nome sperimentale 17-AAG",
    },
)

# Qualificatore di resistenza. La distinzione non e' terminologica: «resistenza
# completa» e «sensibilita' ridotta» portano a decisioni cliniche diverse, e
# collassarle farebbe scartare un farmaco che conserva attivita'.
RELATIVE_REDUCED_SENSITIVITY = "relative_reduced_sensitivity"
COMPLETE_RESISTANCE = "complete_resistance"

STATEMENT_DECISIONS: tuple[dict[str, Any], ...] = (
    {
        "statement_id": "ES-V2-evidence-100005",
        "profile_unit_ids": (
            "PU-PMID-22277784-clinical-crizotinib-resistant",
            "PU-PMID-22277784-baf3-crizotinib-panel",
        ),
        "link_status": "valid_link",
        "rationale": (
            "G1202R supportata come meccanismo di resistenza a crizotinib; "
            "distinguere evidenza clinica e validazione preclinica"
        ),
        "mutation": "G1202R",
    },
    {
        "statement_id": "ES-V2-evidence-1347",
        "profile_unit_ids": ("PU-PMID-22277784-baf3-next-generation-alk-inhibitors",),
        "link_status": "partial_link",
        "rationale": (
            "supporto preclinico per sensibilita' ridotta o resistenza relativa a "
            "CH5424802; non rappresentare come risposta clinica ad alectinib"
        ),
        "intervention_mapping": "CH5424802 -> alectinib",
        "mapping_status": "requires_terminology_verification",
        "resistance_qualifier": RELATIVE_REDUCED_SENSITIVITY,
        "clinical_response_observed": False,
    },
    {
        "statement_id": "ES-V2-evidence-1348",
        "profile_unit_ids": ("PU-PMID-22277784-baf3-next-generation-alk-inhibitors",),
        "link_status": "partial_link",
        "rationale": (
            "NVP-TAE684 conserva attivita' ma mostra potenza ridotta rispetto al wild type"
        ),
        "resistance_qualifier": RELATIVE_REDUCED_SENSITIVITY,
        "clinical_response_observed": False,
    },
    {
        "statement_id": "ES-V2-evidence-1352",
        "profile_unit_ids": ("PU-PMID-22277784-baf3-17aag",),
        "link_status": "valid_link",
        "rationale": (
            "sensibilita' a 17-AAG/tanespimycin in modello cellulare; evidenza "
            "esclusivamente preclinica"
        ),
        "clinical_response_observed": False,
    },
    {
        "statement_id": "ES-V2-evidence-1357",
        "profile_unit_ids": (
            "PU-PMID-22277784-clinical-crizotinib-resistant",
            "PU-PMID-22277784-baf3-crizotinib-panel",
        ),
        "link_status": "valid_link",
        "rationale": (
            "associazione clinica con adenocarcinoma ALK-positive e G1202R, "
            "accompagnata da validazione funzionale"
        ),
        "mutation": "G1202R",
    },
    {
        "statement_id": "ES-V2-evidence-440",
        "profile_unit_ids": ("PU-PMID-22277784-clinical-crizotinib-resistant",),
        "link_status": "valid_link",
        "rationale": (
            "amplificazione del gene di fusione ALK osservata nel contesto di "
            "resistenza acquisita a crizotinib"
        ),
        "mutation": "ALK fusion gene amplification",
    },
    {
        "statement_id": "ES-V2-evidence-441",
        "profile_unit_ids": (
            "PU-PMID-22277784-clinical-crizotinib-resistant",
            "PU-PMID-22277784-baf3-crizotinib-panel",
        ),
        "link_status": "valid_link",
        "rationale": (
            "mutazione secondaria di ALK osservata nella coorte clinica e validata "
            "funzionalmente nel pannello Ba/F3; componente clinica e preclinica "
            "mantenute separate"
        ),
        "mutation": "L1196M",
    },
    {
        "statement_id": "ES-V2-evidence-442",
        "profile_unit_ids": (
            "PU-PMID-22277784-clinical-crizotinib-resistant",
            "PU-PMID-22277784-baf3-crizotinib-panel",
        ),
        "link_status": "valid_link",
        "rationale": (
            "mutazione secondaria di ALK osservata nella coorte clinica e validata "
            "funzionalmente nel pannello Ba/F3; componente clinica e preclinica "
            "mantenute separate"
        ),
        "mutation": "S1206Y",
    },
    {
        "statement_id": "ES-V2-evidence-443",
        "profile_unit_ids": (
            "PU-PMID-22277784-clinical-crizotinib-resistant",
            "PU-PMID-22277784-baf3-crizotinib-panel",
        ),
        "link_status": "valid_link",
        "rationale": (
            "mutazione secondaria di ALK osservata nella coorte clinica e validata "
            "funzionalmente nel pannello Ba/F3; componente clinica e preclinica "
            "mantenute separate"
        ),
        "mutation": "1151Tins",
    },
    {
        "statement_id": "ES-V2-evidence-444",
        "profile_unit_ids": (
            "PU-PMID-22277784-clinical-crizotinib-resistant",
            "PU-PMID-22277784-baf3-crizotinib-panel",
        ),
        "link_status": "valid_link",
        "rationale": (
            "mutazione secondaria di ALK osservata nella coorte clinica e validata "
            "funzionalmente nel pannello Ba/F3; componente clinica e preclinica "
            "mantenute separate"
        ),
        "mutation": "secondary ALK resistance mutation",
    },
)

# Regole di propagazione dichiarate dalla revisione. Sono vincoli, non commenti:
# `build_first_review_artifacts.py` le verifica e fallisce se sono violate.
PROPAGATION_RULES: dict[str, Any] = {
    "clinical_population_must_not_reach": (
        "CH5424802",
        "NVP-TAE684",
        "ASP-3026",
        "17-AAG",
        "tanespimycin",
        "Ba/F3",
    ),
    "preclinical_qualifiers_must_not_reach_patients": (
        "setting",
        "comparator",
        "population",
    ),
    "preclinical_statements_carry": {
        "evidence_design": "preclinical_in_vitro",
        "clinical_response_observed": False,
    },
    "resistance_qualifiers": (RELATIVE_REDUCED_SENSITIVITY, COMPLETE_RESISTANCE),
}
