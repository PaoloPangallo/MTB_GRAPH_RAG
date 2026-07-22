# Annotazione BA-a7be5f0fdfa44bb2

## Fonte

- **Titolo:** EGFR-independent mechanisms of acquired resistance to AZD9291 in EGFR T790M-positive NSCLC patients.
- **PMID:** 26269204
- **DOI:** —
- **NCT:** —
- **Rivista:** Annals of oncology : official journal of the European Society for Medical Oncology
- **Anno:** 2015
- **Locator:** https://pubmed.ncbi.nlm.nih.gov/26269204/

## Proposizioni candidate

| statement | malattia | biomarcatore | intervento | direzione |
| --- | --- | --- | --- | --- |
| `ES-V2-evidence-2157` | Lung Adenocarcinoma | EGFR T790M | osimertinib | sensitivity |

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
