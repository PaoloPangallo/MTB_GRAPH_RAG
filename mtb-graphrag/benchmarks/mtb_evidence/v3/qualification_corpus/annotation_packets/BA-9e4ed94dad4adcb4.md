# Annotazione BA-9e4ed94dad4adcb4

## Fonte

- **Titolo:** Phase I Dose-Escalation Study of JNJ-42756493, an Oral Pan-Fibroblast Growth Factor Receptor Inhibitor, in Patients With Advanced Solid Tumors.
- **PMID:** 26324363
- **DOI:** —
- **NCT:** —
- **Rivista:** Journal of clinical oncology : official journal of the American Society of Clinical Oncology
- **Anno:** 2015
- **Locator:** https://pubmed.ncbi.nlm.nih.gov/26324363/

## Proposizioni candidate

| statement | malattia | biomarcatore | intervento | direzione |
| --- | --- | --- | --- | --- |
| `ES-V2-evidence-1917` | Transitional Cell Carcinoma | FGFR2::BICC1 Fusion | erdafitinib | sensitivity |
| `ES-V2-evidence-1918` | Cancer | FGFR2::v Fusion | erdafitinib | sensitivity |
| `ES-V2-evidence-1920` | Endometrial Cancer | FGFR2::BICC1 Fusion | erdafitinib | sensitivity |
| `ES-V2-evidence-4861` | Adrenal Carcinoma | FGFR3::TACC3 Fusion AND FGFR2::CCDC6 Fusion | erdafitinib | sensitivity |

## Campi da compilare

| campo | indicazione |
| --- | --- |
| `disease` | Malattia studiata, con la denominazione usata dalla fonte. |
| `biomarker_requirements` | Alterazioni richieste per l'arruolamento. |
| `intervention` | Farmaci o interventi somministrati in questo braccio. |
| `regimen` | Regime completo, incluse le combinazioni. |
| `comparator` | Braccio di confronto, se esiste. |
| `population` | Popolazione arruolata. |
| `stage` | Stadio di malattia. |
| `setting` | Setting: adiuvante, neoadiuvante, metastatico, altro. |
| `therapy_line` | Linea di terapia. |
| `prior_therapies` | Terapie precedenti richieste o ammesse. |
| `resection_status` | Stato di resezione, se la fonte lo specifica. |
| `inclusion_criteria` | Criteri di inclusione, in sintesi. |
| `exclusion_criteria` | Criteri di esclusione, in sintesi. |
| `evidence_design` | Disegno dello studio. |

## Problemi rilevati automaticamente

- nessuna lettura umana della fonte primaria
- possibili coorti multiple: 4 denominazioni di malattia distinte

## Istruzioni

1. Leggi la fonte primaria. Non compilare nulla da memoria.
2. Compila un campo solo se la fonte lo afferma. Se non lo afferma, lascia `unknown`: un campo mancante blocca un filtro, un campo sbagliato produce una raccomandazione applicata al paziente sbagliato.
3. Per ogni campo compilato indica il locator dello span (sezione, tabella, paragrafo). Un valore senza locator non e' verificabile.
4. Se la fonte descrive piu' coorti, compila una unita' per coorte. Se le coorti non sono separabili con i dati disponibili, non sceglierne una: marca `cohort_not_separable` e spiega il problema.
5. Non dedurre da titolo o abstract cio' che il testo non afferma.

---

Questo pacchetto non contiene il clinical gold, le terapie attese, le metriche
del sistema ne' una decisione KEEP/AMEND/REJECT. E' deliberato: sapere quale
valore migliora il sistema renderebbe l'annotazione non indipendente.
