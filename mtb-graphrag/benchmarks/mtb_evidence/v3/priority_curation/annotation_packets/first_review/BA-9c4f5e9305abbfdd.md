# Revisione BA-9c4f5e9305abbfdd — first_review

## Fonte

- **Titolo:** AZD9291, an irreversible EGFR TKI, overcomes T790M-mediated resistance to EGFR inhibitors in lung cancer.
- **PMID:** 24893891
- **Locator:** https://pubmed.ncbi.nlm.nih.gov/24893891/
- **Tipi di pubblicazione:** Journal Article, Research Support, N.I.H., Extramural, Research Support, Non-U.S. Gov't
- **Abstract disponibile:** sì

## Domanda sulla struttura delle coorti

> Quante coorti descrive questa fonte? Se piu' di una, quali proposizioni appartengono a ciascuna? Se non e' determinabile, indica `not_separable`.

- Stato automatico: `insufficient_source_information`
- Marcatori di piu' bracci: —
- Marcatori di braccio unico: —
- Comparatore rilevato: no

Gli statement attribuiscono alla fonte piu' interventi o piu' malattie, ma l'abstract non contiene marcatori di struttura. L'assenza di marcatori non dimostra che la coorte sia unica.

## Proposizioni candidate

| statement | intervento | classificazione automatica | supporto |
| --- | --- | --- | --- |
| `ES-V2-evidence-4293` | erlotinib | `candidate_not_determinable` | `unsupported_by_primary_source` |
| `ES-V2-evidence-4294` | osimertinib | `candidate_not_determinable` | `unsupported_by_primary_source` |
| `ES-V2-evidence-963` | osimertinib | `candidate_not_determinable` | `unsupported_by_primary_source` |

## Rilevazioni automatiche

**Rilevate ma NON emesse — da verificare sulla fonte:**

- `setting` ⇒ `advanced`? — «advanced» (UNLABELLED)

**Rilevazioni discordanti, nessun valore proposto:** `evidence_design`

Le rilevazioni non emesse provengono da corrispondenze lessicali che possono descrivere i campioni invece dello studio. Vanno confermate sulla fonte.

## Estratti

- **UNLABELLED** — «…t-generation EGFR tyrosine kinase inhibitors (EGFR TKI) provide significant clinical benefit in patients with advanced EGFR-mutant (EGFRm(+)) non-small cell lung cancer (NSCLC). Patients ultimately develop disease progression, o…»
- **UNLABELLED** — «…ained tumor regression in EGFR-mutant tumor xenograft and transgenic models. The treatment of 2 patients with advanced EGFRm(+) T790M(+) NSCLC is described as proof of principle.»
- **UNLABELLED** — «…ntly inhibits signaling pathways and cellular growth in both EGFRm(+) and EGFRm(+)/T790M(+) mutant cell lines in vitro, with lower activity against wild-type EGFR lines, translating into profound and sustained tumor regression i…»
- **UNLABELLED** — «…e drug potently inhibits signaling pathways and cellular growth in both EGFRm(+) and EGFRm(+)/T790M(+) mutant cell lines in vitro, with lower activity against wild-type EGFR lines, translating into profound and sustained tumor reg…»
- **UNLABELLED** — «…y against wild-type EGFR lines, translating into profound and sustained tumor regression in EGFR-mutant tumor xenograft and transgenic models. The treatment of 2 patients with advanced EGFRm(+) T790M(+) NSCLC is described as proo…»
- **SIGNIFICANCE** — «…mutant EGFR while harboring less activity toward wild-type EGFR. AZD9291 is showing promising responses in a phase I trial even at the first-dose level, with first published clinical proof-of-principle validation being present…»

## Campi da confermare

| campo | indicazione |
| --- | --- |
| `disease` | Malattia studiata, con la denominazione della fonte. |
| `histology` | Istologia, se la fonte la specifica. |
| `population` | Popolazione arruolata. |
| `stage` | Stadio di malattia. |
| `setting` | Adiuvante, neoadiuvante, metastatico, perioperatorio, altro. |
| `therapy_line` | Linea di terapia. |
| `resection_status` | Stato di resezione. |
| `intervention` | Interventi somministrati in questo braccio. |
| `regimen` | Regime completo, incluse le combinazioni. |
| `comparator` | Braccio di confronto, se esiste. |
| `prior_therapies` | Terapie precedenti richieste o ammesse. |
| `biomarker_requirements` | Alterazioni richieste per l'arruolamento. |
| `inclusion_criteria` | Criteri di inclusione, in sintesi. |
| `exclusion_criteria` | Criteri di esclusione, in sintesi. |
| `study_design` | Disegno dello studio. |
| `evidence_scope` | Ambito dell'evidenza. |
| `cohort_notes` | Note sulla struttura delle coorti. |

## Istruzioni

1. Leggi la fonte primaria. Non compilare nulla da memoria.
2. Compila un campo solo se la fonte lo afferma. Se non lo afferma, lascia `unknown`.
3. Se la fonte descrive piu' coorti e non sai a quale appartiene una proposizione, usa `not_separable`. Non sceglierne una.
4. `unknown` e `not_separable` non sono la stessa cosa: il primo dice che non lo sappiamo, il secondo che la fonte non lo distingue.
5. Per ogni campo compilato indica sezione o tabella da cui viene il valore.
6. Le rilevazioni automatiche allegate sono proposte da verificare, non risposte. Alcune sono note per essere sbagliate.

---

Questo pacchetto non contiene il clinical gold, la terapia attesa, le metriche
della pipeline, le decisioni dell'audit ne' l'indicazione di quale risposta
migliori il sistema. Se fosse presente anche solo una di queste, la revisione
non sarebbe indipendente.

