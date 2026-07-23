# PMID:22235099 — revisione documentale

**Decisione strutturale: `audit_split_confirmed_with_more_units`**

lo split clinico/preclinico e' confermato, ma due unita' non bastano: la componente preclinica sono quattro sistemi distinti, con fondi cellulari e saggi diversi, e uno di essi ha dato esito negativo

## 1-2. Fonte e disponibilita'

- PMID: `22235099` · PMC: `PMC3311875`
- Disponibilita': **full_text**
- Locator verificati: **12/12** ({'exact': 12})
- Hash del documento: `ff9615e75fe8e274c9cc9656bfee3b4b…`
- Full text conservato: **no**

## 3. Mappa clinico-preclinica

- Parte clinica: la serie di 14 pazienti ri-biopsiati e le analisi molecolari sui loro campioni
- Parte preclinica: quattro sistemi: Ba/F3 ingegnerizzate, NIH3T3 ingegnerizzate, CUTO-1 contro H3122 e H2228, H3122 con KRAS G12V
- Il preclinico valida il clinico? si', per G1269A: la mutazione e' vista in due pazienti e poi validata su Ba/F3 e NIH3T3
- Farmaci di laboratorio somministrati ai pazienti? si', crizotinib in entrambi i contesti; nessun altro farmaco e' stato testato in laboratorio
- Alterazioni: requisito o reperto? il riarrangiamento di ALK era requisito di arruolamento; tutte le alterazioni di resistenza sono reperti successivi

## 4-6. Split proposto e unita'

L'audit proponeva **2** unita'. La lettura ne sostiene **5**.

| Unita' | Tipo | Statement candidati |
| --- | --- | --- |
| `PU-PMID-22235099-baf3-engineered` | preclinical_engineered_model | `ES-V2-evidence-764` |
| `PU-PMID-22235099-clinical-cohort` | clinical_observational_cohort | `ES-V2-evidence-4288`, `ES-V2-evidence-764`, `ES-V2-evidence-766` |
| `PU-PMID-22235099-cuto1-comparative` | preclinical_in_vitro_comparative_pharmacology | — |
| `PU-PMID-22235099-h3122-kras-engineered` | preclinical_engineered_model | — |
| `PU-PMID-22235099-nih3t3-engineered` | preclinical_engineered_model | `ES-V2-evidence-764` |

## 7-9. Qualificatori, provenienza, locator

Ogni dimensione nota porta la sua provenienza; la completezza e' verificata dal
costruttore, che solleva se un valore noto resta senza locator.

- Campi `unknown`: `biomarker_requirements`, `comparator`, `exclusion_criteria`, `inclusion_criteria`, `prior_therapies`, `regimen`, `resection_status`, `setting`, `stage`, `therapy_line`
- Campi `not_applicable`: `disease`, `exclusion_criteria`, `inclusion_criteria`, `population`, `prior_therapies`, `resection_status`, `setting`, `stage`, `therapy_line`
- Dimensioni non separabili: —

## 10. Statement

| Statement | Supporto | Stato candidato | Unita' |
| --- | --- | --- | --- |
| `ES-V2-evidence-4288` | direct_clinical_support | **candidate_partial** | `PU-PMID-22235099-clinical-cohort` |
| `ES-V2-evidence-764` | clinical_observation_with_preclinical_validation | **candidate_valid** | `PU-PMID-22235099-clinical-cohort`, `PU-PMID-22235099-baf3-engineered`, `PU-PMID-22235099-nih3t3-engineered` |
| `ES-V2-evidence-766` | direct_clinical_support | **candidate_partial** | `PU-PMID-22235099-clinical-cohort` |

## 11. Terminologia

| Fonte | Statement | Stato |
| --- | --- | --- |
| «copy number gain (CNG) of the ALK gene fusion» | «ALK Amplification» | **requires_terminology_verification** |

## 12. Propagazione

- Regole eseguite: 14
- Violazioni: **0**
- Propagabile: **no** — nessuna proposta lo e' prima dell'approvazione

## 13-15. Limiti

- il numero esatto di pazienti per ciascun meccanismo si legge nelle tabelle, non nel testo corrente

Rischio residuo: la coorte clinica contiene osservazioni a livello di singolo paziente (#9 per EGFR, #8 per il CNG isolato) che non sono proprieta' della coorte

## 16. Domande per l'autore

1. Quattro unita' precliniche sono la granularita' giusta, o Ba/F3 e NIH3T3 vanno tenute insieme come «modelli isogenici ingegnerizzati»?
2. L'esperimento su H3122 con KRAS G12V ha esito negativo: va conservato come unita' propria, o registrato come nota della coorte clinica?
3. CUTO-1 deriva dal paziente #10 ma ha perso il riarrangiamento di ALK: e' una unita' preclinica autonoma o un prolungamento del caso clinico?
4. ES-V2-evidence-4288 poggia su un solo paziente. Va marcato case-level per impedirne la propagazione alla coorte?

## 17. Stato

```
review_status                      = source_checked_review_proposal
human_reviewed                     = false
first_review_complete              = false
is_evaluable                       = false
requires_author_approval           = true
requires_second_independent_review = true
```

Una seconda revisione indipendente resta necessaria: questa fase ha letto la
fonte, non l'ha giudicata.

