# Dataset Benchmark — Casi Molecular Tumor Board
# Per la validazione del sistema GraphRAG agentico
# Formato: Case_ID | Tumore | Gene | Variante | Farmaco_MTB | ESCAT_Tier | Fonte | PMID | Note

## STRUTTURA CAMPI
# case_id: identificatore univoco
# tumor_type: tipo tumorale
# gene: gene HUGO symbol
# variant: nome variante (CIViC-style)
# mtb_recommendation: farmaco raccomandato dal MTB
# escat_tier: tier ESCAT (I, II, III, IV)
# escat_subclass: sottoclasse ESCAT (es. I-A = approvato stessa indicazione, I-B = approvato altra indicazione)
# source: articolo di riferimento
# pmid: PubMed ID
# notes: note cliniche rilevanti

---

## CASO 1
case_id: BENCH-001
tumor_type: Non-Small Cell Lung Cancer (NSCLC)
gene: EGFR
variant: L858R
mtb_recommendation: Osimertinib
escat_tier: I
escat_subclass: I-A (approvato FDA/EMA in prima linea per EGFR mutato)
source: "Implementing ESCAT in a Comprehensive Profiling Program — JCO Precision Oncology 2022"
pmid: 36395468
notes: >
  Variante puntiforme nell'esone 21 di EGFR. Osimertinib (inibitore EGFR di terza generazione)
  è approvato FDA in prima linea per NSCLC con mutazione EGFR (exon 19 del o L858R).
  Studio FLAURA. Evidenza di livello A in CIViC. Caso gold standard per la validazione.
  Il sistema deve identificare: Afatinib, Dacomitinib, Osimertinib, Erlotinib, Gefitinib
  come farmaci sensibili con evidenza A.

## CASO 2
case_id: BENCH-002
tumor_type: Non-Small Cell Lung Cancer (NSCLC)
gene: ALK
variant: Fusion
mtb_recommendation: Alectinib
escat_tier: I
escat_subclass: I-A (approvato FDA/EMA in prima linea ALK+)
source: "ESCAT framework — Mateo et al. Ann Oncol 2018 + ALEX trial data"
pmid: 30285222
notes: >
  Riarrangiamento EML4-ALK (fusione). Alectinib approvato FDA in prima linea per NSCLC ALK+
  (studio ALEX). Alternativa: Crizotinib (seconda scelta), Brigatinib, Lorlatinib.
  Il sistema deve identificare la fusione ALK come Tier I e raccomandare un ALK-inibitore
  di seconda generazione come primo scelta.

## CASO 3
case_id: BENCH-003
tumor_type: Melanoma
gene: BRAF
variant: V600E
mtb_recommendation: Dabrafenib + Trametinib
escat_tier: I
escat_subclass: I-A (approvato FDA/EMA combinazione BRAF+MEK inibitore)
source: "ESCAT implementation Gustave Roussy — JCO PO 2022"
pmid: 36395468
notes: >
  Mutazione puntiforme BRAF V600E in melanoma metastatico. Combinazione dabrafenib+trametinib
  (o vemurafenib+cobimetinib) approvata FDA. Il sistema deve identificare V600E come Tier I
  nel melanoma ma anche segnalare che la stessa variante conferisce RESISTENZA a cetuximab/
  panitumumab nel carcinoma colorettale (esempio di importanza della specificità tumorale).

## CASO 4
case_id: BENCH-004
tumor_type: Breast Cancer (HER2+)
gene: ERBB2
variant: Amplification
mtb_recommendation: Trastuzumab + Pertuzumab
escat_tier: I
escat_subclass: I-A (approvato FDA/EMA HER2+ breast cancer)
source: "MTB in metastatic breast cancer — EIO — Breast Cancer Res Treat 2024"
pmid: 39476201
notes: >
  Amplificazione ERBB2 (HER2) nel carcinoma mammario metastatico. Trastuzumab+pertuzumab
  (doppio blocco HER2) o T-DM1/T-DXd approvati FDA. Companion diagnostic: test IHC/FISH
  HER2 obbligatorio prima della prescrizione.
  Il sistema deve identificare ERBB2 Amplification come Tier I e raccomandare anti-HER2.

## CASO 5
case_id: BENCH-005
tumor_type: Ovarian Cancer
gene: BRCA1
variant: Mutation
mtb_recommendation: Olaparib
escat_tier: I
escat_subclass: I-A (approvato FDA in mantenimento BRCA-mutato)
source: "Real-world MTB outcomes — JCO Precision Oncology 2024 + SOLO-2 trial"
pmid: 32068947
notes: >
  Mutazione germinale BRCA1 in carcinoma ovarico platino-sensibile recidivante.
  Olaparib (PARP inibitore) approvato FDA in mantenimento dopo risposta al platino.
  Alternativa: Niraparib (approvato anche senza selezione BRCA in mantenimento).
  Il sistema deve identificare BRCA1 Mutation come Tier I e raccomandare un PARP inibitore.

## CASO 6
case_id: BENCH-006
tumor_type: Chronic Myeloid Leukemia (CML)
gene: ABL1
variant: BCR-ABL1 Fusion
mtb_recommendation: Imatinib
escat_tier: I
escat_subclass: I-A (approvato FDA — caso storico della targeted therapy)
source: "CIViC Evidence Level A — BCR::ABL1 + Imatinib — PMID 11423618"
pmid: 11423618
notes: >
  Fusione BCR::ABL1 nella CML. Imatinib (inibitore tirosina chinasi BCR-ABL) è il caso
  storico paradigmatico della oncologia di precisione: primo farmaco molecolare approvato.
  Alternative di seconda generazione: dasatinib, nilotinib (per resistenza o intolleranza).
  Il sistema deve identificare BCR-ABL1 come Tier I e raccomandare un TKI BCR-ABL.

## CASO 7
case_id: BENCH-007
tumor_type: Colorectal Cancer (mCRC)
gene: BRAF
variant: V600E
mtb_recommendation: Encorafenib + Cetuximab
escat_tier: I
escat_subclass: I-A (approvato FDA 2020 per mCRC BRAF V600E in seconda linea)
source: "WIN-MTB-2023001 — Oncotarget 2025 + BEACON-CRC trial"
pmid: 31566309
notes: >
  BRAF V600E in mCRC è una variante con prognosi peggiore rispetto al melanoma.
  Dal 2020 la combinazione encorafenib+cetuximab è approvata FDA (studio BEACON-CRC).
  ATTENZIONE: questo stesso paziente aveva anche MET amplification che richiedeva
  considerazione separata. Caso WIN-MTB-2023001 documentato su Oncotarget 2025.
  Il sistema deve distinguere la stessa variante (BRAF V600E) in contesti tumorali diversi:
  Tier I melanoma (dabrafenib+trametinib), Tier I CRC (encorafenib+cetuximab).

## CASO 8
case_id: BENCH-008
tumor_type: Breast Cancer (HR+/HER2-)
gene: PIK3CA
variant: Mutation
mtb_recommendation: Alpelisib + Fulvestrant
escat_tier: I
escat_subclass: I-A (approvato FDA 2019 per HR+/HER2-/PIK3CA-mutato post-CDK4/6i)
source: "ESCAT in breast cancer — PMC10046335 + SOLAR-1 trial"
pmid: 31091374
notes: >
  Mutazione PIK3CA (frequente nel carcinoma mammario HR+/HER2-) nel setting post-CDK4/6
  inibitore. Alpelisib (inibitore PI3Kα) + fulvestrant approvato FDA 2019 (SOLAR-1).
  Companion diagnostic: test PIK3CA (tessuto o ctDNA).
  Secondo i dati del notebook: PIK3CA ha 76 evidenze Gold (livello A) — caso benchmark ricco.
  Il sistema deve identificare PIK3CA Mutation come Tier I in HR+/HER2- breast cancer.

## CASO 9
case_id: BENCH-009
tumor_type: Gastrointestinal Stromal Tumor (GIST)
gene: KIT
variant: Exon 11 Mutation
mtb_recommendation: Imatinib
escat_tier: I
escat_subclass: I-A (approvato FDA per GIST KIT-mutato)
source: "ESCAT implementation — Gustave Roussy JCO PO 2022"
pmid: 36395468
notes: >
  Mutazione esone 11 di KIT (la più comune in GIST, ~70% dei casi). Imatinib è il gold
  standard approvato in prima linea per GIST KIT-mutato. Per progressione: sunitinib
  (seconda linea) o regorafenib (terza linea). Companion diagnostic: test KIT/PDGFRA
  obbligatorio per la selezione dei pazienti.
  Il sistema deve identificare KIT Exon 11 Mutation come Tier I in GIST.

## CASO 10
case_id: BENCH-010
tumor_type: Acute Myeloid Leukemia (AML)
gene: FLT3
variant: ITD
mtb_recommendation: Midostaurin + Chemioterapia standard
escat_tier: I
escat_subclass: I-A (approvato FDA 2017 per AML FLT3-mutato in prima linea)
source: "RATIFY trial — Stone et al. NEJM 2017 + CIViC Evidence Level A"
pmid: 28644114
notes: >
  Duplicazione interna in tandem (ITD) di FLT3 in AML de novo. Midostaurin (inibitore
  multitarget incluso FLT3) aggiunto alla chemioterapia standard (7+3) approvato FDA 2017
  (studio RATIFY). Per AML in recidiva/refrattaria con FLT3-ITD: gilteritinib (ADMIRAL).
  Il sistema deve identificare FLT3 ITD come Tier I e raccomandare midostaurin in prima linea.

---

## RIEPILOGO DEL DATASET

| Case | Tumore | Gene | Variante | Farmaco MTB | ESCAT |
|------|--------|------|----------|-------------|-------|
| BENCH-001 | NSCLC | EGFR | L858R | Osimertinib | I-A |
| BENCH-002 | NSCLC | ALK | Fusion | Alectinib | I-A |
| BENCH-003 | Melanoma | BRAF | V600E | Dabrafenib+Trametinib | I-A |
| BENCH-004 | Breast HER2+ | ERBB2 | Amplification | Trastuzumab+Pertuzumab | I-A |
| BENCH-005 | Ovarian | BRCA1 | Mutation | Olaparib | I-A |
| BENCH-006 | CML | ABL1 | BCR-ABL1 Fusion | Imatinib | I-A |
| BENCH-007 | mCRC | BRAF | V600E | Encorafenib+Cetuximab | I-A |
| BENCH-008 | Breast HR+ | PIK3CA | Mutation | Alpelisib+Fulvestrant | I-A |
| BENCH-009 | GIST | KIT | Exon 11 Mutation | Imatinib | I-A |
| BENCH-010 | AML | FLT3 | ITD | Midostaurin | I-A |

## NOTE METODOLOGICHE

Tutti i 10 casi sono di ESCAT Tier I-A (approvazione regolatoria nella stessa indicazione).
Questo è intenzionale per la fase iniziale di benchmark: il sistema deve identificare
correttamente i casi più chiari prima di affrontare quelli più complessi (Tier II-III).

Una seconda versione del benchmark (BENCH-v2) potrà includere:
- Casi Tier II (off-label con evidenza forte): es. BRAF V600E in tumore del polmone non-melanoma
- Casi Tier III (trial): varianti con evidenza preliminare
- Casi con profilo molecolare complesso (più varianti concomitanti)
- Casi con resistenza acquisita (es. T790M dopo osimertinib)

Il caso BENCH-007 (BRAF V600E in mCRC) è deliberatamente sovrapponibile con BENCH-003
(BRAF V600E in melanoma) per testare se il sistema distingue correttamente il contesto
tumorale nella raccomandazione terapeutica. Questo è un test critico per il Verifier Agent.