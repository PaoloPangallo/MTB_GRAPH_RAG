# Annotazione BA-aafcf903d25ff168

## Fonte

- **Titolo:** Mechanisms of resistance to crizotinib in patients with ALK gene rearranged non-small cell lung cancer.
- **PMID:** 22235099
- **DOI:** —
- **NCT:** —
- **Rivista:** Clinical cancer research : an official journal of the American Association for Cancer Research
- **Anno:** 2012
- **Locator:** https://pubmed.ncbi.nlm.nih.gov/22235099/

## Proposizioni candidate

| statement | malattia | biomarcatore | intervento | direzione |
| --- | --- | --- | --- | --- |
| `ES-V2-evidence-4288` | Lung Non-small Cell Carcinoma | EGFR L858R | crizotinib | resistance |
| `ES-V2-evidence-764` | Lung Non-small Cell Carcinoma | EML4::ALK Fusion AND ALK G1269A | crizotinib | resistance |
| `ES-V2-evidence-766` | Lung Non-small Cell Carcinoma | EML4::ALK Fusion AND ALK Amplification | crizotinib | resistance |

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
