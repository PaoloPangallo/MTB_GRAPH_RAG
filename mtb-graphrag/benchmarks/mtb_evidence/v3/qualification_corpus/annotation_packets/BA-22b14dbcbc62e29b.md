# Annotazione BA-22b14dbcbc62e29b

## Fonte

- **Titolo:** Mechanisms of acquired crizotinib resistance in ALK-rearranged lung Cancers.
- **PMID:** 22277784
- **DOI:** —
- **NCT:** —
- **Rivista:** Science translational medicine
- **Anno:** 2012
- **Locator:** https://pubmed.ncbi.nlm.nih.gov/22277784/

## Proposizioni candidate

| statement | malattia | biomarcatore | intervento | direzione |
| --- | --- | --- | --- | --- |
| `ES-V2-evidence-100005` | Non-Small Cell Lung Cancer | ALK G1202R AND v::ALK Fusion | crizotinib | resistance |
| `ES-V2-evidence-1347` | Lung Non-small Cell Carcinoma | EML4::ALK Fusion AND ALK T1151dup | alectinib hydrochloride | resistance |
| `ES-V2-evidence-1348` | Lung Non-small Cell Carcinoma | EML4::ALK Fusion AND ALK T1151dup | alk inhibitor tae684 | resistance |
| `ES-V2-evidence-1352` | Lung Non-small Cell Carcinoma | EML4::ALK Fusion AND ALK G1202R | tanespimycin | sensitivity |
| `ES-V2-evidence-1357` | Lung Adenocarcinoma | ALK G1202R AND v::ALK Fusion | crizotinib | resistance |
| `ES-V2-evidence-440` | Lung Non-small Cell Carcinoma | EML4::ALK Fusion AND ALK Amplification | crizotinib | resistance |
| `ES-V2-evidence-441` | Lung Non-small Cell Carcinoma | EML4::ALK Fusion AND ALK G1202R | crizotinib | resistance |
| `ES-V2-evidence-442` | Lung Non-small Cell Carcinoma | EML4::ALK Fusion AND ALK L1196M | crizotinib | resistance |
| `ES-V2-evidence-443` | Lung Non-small Cell Carcinoma | EML4::ALK Fusion AND ALK S1206Y | crizotinib | resistance |
| `ES-V2-evidence-444` | Lung Non-small Cell Carcinoma | EML4::ALK Fusion AND ALK T1151dup | crizotinib | resistance |

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
- possibili coorti multiple: 4 interventi distinti negli statement; 3 denominazioni di malattia distinte

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
