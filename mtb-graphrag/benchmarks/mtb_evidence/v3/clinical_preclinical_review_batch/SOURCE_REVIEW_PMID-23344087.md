# PMID:23344087 — revisione documentale

**Decisione strutturale: `audit_split_partially_supported`**

l'abstract nomina esplicitamente sia la coorte clinica sia gli esperimenti in vitro, quindi lo split e' sostenuto. Non e' sostenuta la **composizione** della parte preclinica: i cloni mutanti sono nominati senza il fondo cellulare, e senza full text la loro relazione con SNU-2535 resta indeterminata

## 1-2. Fonte e disponibilita'

- PMID: `23344087`
- Disponibilita': **abstract_only**
- Locator verificati: **6/6** ({'exact': 6})
- Hash del documento: `23bc0f21fcbfb22ce3902d1ca802e6a2…`
- Full text conservato: **no**

## 3. Mappa clinico-preclinica

- Parte clinica: i 7 pazienti con resistenza acquisita e le analisi sui loro campioni
- Parte preclinica: la citotossicita' in vitro su SNU-2535, H3122 CR1 e i cloni mutanti
- Il preclinico valida il clinico? si' per G1269: SNU-2535 viene da un paziente che portava quella mutazione
- Farmaci di laboratorio somministrati ai pazienti? si', crizotinib in entrambi i contesti
- Alterazioni: requisito o reperto? il riarrangiamento di ALK precede il trattamento; le mutazioni di resistenza sono reperti successivi

## 4-6. Split proposto e unita'

L'audit proponeva **2** unita'. La lettura ne sostiene **3**.

| Unita' | Tipo | Statement candidati |
| --- | --- | --- |
| `PU-PMID-23344087-clinical-cohort` | clinical_observational_cohort | `ES-V2-evidence-765`, `ES-V2-evidence-767` |
| `PU-PMID-23344087-engineered-clones` | preclinical_engineered_model | `ES-V2-evidence-765` |
| `PU-PMID-23344087-patient-derived` | preclinical_patient_derived_model | `ES-V2-evidence-765` |

## 7-9. Qualificatori, provenienza, locator

Ogni dimensione nota porta la sua provenienza; la completezza e' verificata dal
costruttore, che solleva se un valore noto resta senza locator.

- Campi `unknown`: `biomarker_requirements`, `comparator`, `exclusion_criteria`, `inclusion_criteria`, `prior_therapies`, `regimen`, `resection_status`
- Campi `not_applicable`: `disease`, `exclusion_criteria`, `inclusion_criteria`, `population`, `prior_therapies`, `resection_status`, `setting`, `stage`, `therapy_line`
- Dimensioni non separabili: `preclinical_model_composition`

## 10. Statement

| Statement | Supporto | Stato candidato | Unita' |
| --- | --- | --- | --- |
| `ES-V2-evidence-765` | clinical_observation_with_preclinical_validation | **candidate_partial** | `PU-PMID-23344087-clinical-cohort`, `PU-PMID-23344087-patient-derived`, `PU-PMID-23344087-engineered-clones` |
| `ES-V2-evidence-767` | direct_clinical_support | **candidate_ambiguous** | `PU-PMID-23344087-clinical-cohort` |

## 11. Terminologia

| Fonte | Statement | Stato |
| --- | --- | --- |
| «ALK gene copy number gain» | «ALK Amplification» | **requires_terminology_verification** |
| «less sensitive to crizotinib» | «resistance» | **requires_terminology_verification** |

## 12. Propagazione

- Regole eseguite: 14
- Violazioni: **0**
- Propagabile: **no** — nessuna proposta lo e' prima dell'approvazione

## 13-15. Limiti

- full text dichiarato «Subscription required» da Europe PMC: non e' in PMC, non e' open access, nessuna via pubblica di accesso
- figure e tabelle non osservabili

Rischio residuo: senza full text non e' possibile sapere quanti sistemi preclinici distinti esistano davvero, ne' su quale fondo cellulare siano costruiti i cloni

## 16. Domande per l'autore

1. Senza full text la composizione preclinica resta indeterminata. Si accetta la proposta a tre unita', o si sospende in attesa dell'accesso?
2. L'abstract dice «less sensitive» dove lo statement dice «resistance». La differenza va registrata come conflitto o come mapping da verificare?
3. L'unico paziente con copy number gain portava anche EGFR L858R: ES-V2-evidence-767 va marcato conflicting invece che ambiguous?

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

