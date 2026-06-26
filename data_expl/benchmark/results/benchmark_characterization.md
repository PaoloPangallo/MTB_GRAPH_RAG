# Caratterizzazione metodologica del benchmark MTB

> Report generato automaticamente il 2026-06-25 15:33.
> **Fonte:** `benchmark_papers_summary_30_v2.csv` (30 casi).
> **Metodo:** analisi programmatica — nessuna modifica al CSV.
> **Neo4j:** query dirette su GraphRAGTesi.
> **NCBI:** verifica PMID via E-utilities esummary.

---
## §1 — Composizione e bilanciamento

**Numero totale di casi:** 30

### Distribuzione per `alteration_type`

| Valore | n | % |
|--------|---|---|
| point_mutation | 14 | 46.7% |
| fusion | 6 | 20.0% |
| atypical | 4 | 13.3% |
| cna | 3 | 10.0% |
| biomarker | 2 | 6.7% |
| itd | 1 | 3.3% |

### Distribuzione per `tumor`

| Valore | n | % |
|--------|---|---|
| NSCLC | 10 | 33.3% |
| Colorectal Cancer | 3 | 10.0% |
| CML | 2 | 6.7% |
| GIST | 2 | 6.7% |
| AML | 2 | 6.7% |
| Solid Tumor | 2 | 6.7% |
| Gastric Cancer | 2 | 6.7% |
| Melanoma | 1 | 3.3% |
| Breast Cancer HER2+ | 1 | 3.3% |
| Ovarian Cancer | 1 | 3.3% |
| Breast Cancer HR+ | 1 | 3.3% |
| Prostate Cancer | 1 | 3.3% |
| Cholangiocarcinoma | 1 | 3.3% |
| Thyroid Cancer | 1 | 3.3% |

### Distribuzione per `gene`

| Valore | n | % |
|--------|---|---|
| BRAF | 4 | 13.3% |
| EGFR | 3 | 10.0% |
| ERBB2 | 3 | 10.0% |
| ALK | 2 | 6.7% |
| ABL1 | 2 | 6.7% |
| KIT | 2 | 6.7% |
| KRAS | 2 | 6.7% |
| BRCA1 | 1 | 3.3% |
| PIK3CA | 1 | 3.3% |
| FLT3 | 1 | 3.3% |
| RET | 1 | 3.3% |
| NTRK1 | 1 | 3.3% |
| MMR | 1 | 3.3% |
| BRCA2 | 1 | 3.3% |
| TMB | 1 | 3.3% |
| IDH1 | 1 | 3.3% |
| FGFR2 | 1 | 3.3% |
| MET | 1 | 3.3% |
| ROS1 | 1 | 3.3% |

### Distribuzione per `escat`

| Valore | n | % |
|--------|---|---|
| I-A | 25 | 83.3% |
| I-B | 4 | 13.3% |
| non determinato | 1 | 3.3% |

### Distribuzione per `kb_coverage`

| Valore | n | % |
|--------|---|---|
| COVERED | 30 | 100.0% |

### Distribuzione per `category`

| Valore | n | % |
|--------|---|---|
| baseline | 11 | 36.7% |
| new_target | 8 | 26.7% |
| resistance | 4 | 13.3% |
| off_label | 4 | 13.3% |
| tumor_agnostic | 2 | 6.7% |
| biomarker | 1 | 3.3% |

### Categorie singleton (n=1)

Una categoria con un solo caso non permette analisi stratificata affidabile.

| Dimensione | Valore singleton | n totale categorie |
|------------|-----------------|-------------------|
| alteration_type | itd | 6 |
| tumor | Melanoma | 14 |
| tumor | Breast Cancer HER2+ | 14 |
| tumor | Ovarian Cancer | 14 |
| tumor | Breast Cancer HR+ | 14 |
| tumor | Prostate Cancer | 14 |
| tumor | Cholangiocarcinoma | 14 |
| tumor | Thyroid Cancer | 14 |
| gene | BRCA1 | 19 |
| gene | PIK3CA | 19 |
| gene | FLT3 | 19 |
| gene | RET | 19 |
| gene | NTRK1 | 19 |
| gene | MMR | 19 |
| gene | BRCA2 | 19 |
| gene | TMB | 19 |
| gene | IDH1 | 19 |
| gene | FGFR2 | 19 |
| gene | MET | 19 |
| gene | ROS1 | 19 |
| escat | non determinato | 3 |
| kb_coverage | *(nessuna)* | 1 |
| category | biomarker | 6 |

**Totale categorie singleton across all dimensions:** 22

### Sbilanciamenti rilevanti

- **`alteration_type`**: il valore più frequente è `point_mutation` (n=14, 47%) vs il meno frequente `itd` (n=1). Rapporto 14.0:1.
- **`tumor`**: il valore più frequente è `NSCLC` (n=10, 33%) vs il meno frequente `Thyroid Cancer` (n=1). Rapporto 10.0:1.
- **`gene`**: il valore più frequente è `BRAF` (n=4, 13%) vs il meno frequente `ROS1` (n=1). Rapporto 4.0:1.
- **`escat`**: il valore più frequente è `I-A` (n=25, 83%) vs il meno frequente `non determinato` (n=1). Rapporto 25.0:1.
- **`category`**: il valore più frequente è `baseline` (n=11, 37%) vs il meno frequente `biomarker` (n=1). Rapporto 11.0:1.

## §2 — Tracciabilità delle annotazioni

### Campi di provenance delle annotazioni

**Colonne nel CSV:** 18 totali.

**Campi di provenance presenti:** 0 — **nessuno**

**Campi di provenance assenti (cercati):** `annotation_source`, `annotator_id`, `guideline_reference`, `escat_source`, `drug_source`, `annotation_date`

> [!IMPORTANT]
> Il CSV non contiene nessun campo che documenti la fonte delle annotazioni (`expected_drug`, `escat`). Non è possibile distinguere programmaticamente se un'annotazione è trascritta da una fonte esterna (label FDA/EMA, linea guida ESMO/IASLC) o è giudizio dell'annotatore. La tracciabilità è ricostruibile solo indirettamente.

### Verifica PMID via NCBI E-utilities

| case_id | PMID | Esiste su PubMed? | Titolo NCBI (troncato) | Titolo CSV match? |
|---------|------|-------------------|----------------------|------------------|
| BENCH-001 | 37937763 | ✅ Sì | Osimertinib with or without Chemotherapy in EGFR-Mutated Adv... | ✅ |
| BENCH-002 | 28586279 | ✅ Sì | Alectinib versus Crizotinib in Untreated ALK-Positive Non-Sm... | ✅ |
| BENCH-003 | 21639808 | ✅ Sì | Improved survival with vemurafenib in melanoma with BRAF V60... | ✅ |
| BENCH-004 | 26874901 | ✅ Sì | Neratinib after trastuzumab-based adjuvant therapy in patien... | ✅ |
| BENCH-005 | 30345884 | ✅ Sì | Maintenance Olaparib in Patients with Newly Diagnosed Advanc... | ✅ |
| BENCH-006 | 11423618 | ✅ Sì | Clinical resistance to STI-571 cancer therapy caused by BCR-... | ✅ |
| BENCH-007 | 31566309 | ✅ Sì | Encorafenib, Binimetinib, and Cetuximab in BRAF V600E-Mutate... | ✅ |
| BENCH-008 | 31091374 | ✅ Sì | Alpelisib for PIK3CA-Mutated, Hormone Receptor-Positive Adva... | ✅ |
| BENCH-009 | 14645423 | ✅ Sì | Kinase mutations and imatinib response in patients with meta... | ✅ |
| BENCH-010 | 31665578 | ✅ Sì | Gilteritinib or Chemotherapy for Relapsed or Refractory FLT3... | ✅ |
| BENCH-011 | 27959700 | ✅ Sì | Osimertinib or Platinum-Pemetrexed in EGFR T790M-Positive Lu... | ✅ |
| BENCH-012 | 34096690 | ✅ Sì | Sotorasib for Lung Cancers with KRAS p.G12C Mutation. | ✅ |
| BENCH-013 | 30892989 | ✅ Sì | ALK Resistance Mutations and Efficacy of Lorlatinib in Advan... | ❌ |
| BENCH-014 | 24180494 | ✅ Sì | A phase 2 trial of ponatinib in Philadelphia chromosome-posi... | ✅ |
| BENCH-015 | 32846060 | ✅ Sì | Efficacy of Selpercatinib in RET Fusion-Positive Non-Small-C... | ✅ |
| BENCH-016 | 29466156 | ✅ Sì | Efficacy of Larotrectinib in TRK Fusion-Positive Cancers in ... | ✅ |
| BENCH-017 | 33264544 | ✅ Sì | Pembrolizumab in Microsatellite-Instability-High Advanced Co... | ✅ |
| BENCH-018 | 37870968 | ✅ Sì | Sotorasib plus Panitumumab in Refractory Colorectal Cancer w... | ✅ |
| BENCH-019 | 16624552 | ✅ Sì | KIT mutations and dose selection for imatinib in patients wi... | ✅ |
| BENCH-020 | 27283860 | ✅ Sì | Dabrafenib plus trametinib in patients with previously treat... | ✅ |
| BENCH-021 | 20728210 | ✅ Sì | Trastuzumab in combination with chemotherapy versus chemothe... | ✅ |
| BENCH-022 | 32343890 | ✅ Sì | Olaparib for Metastatic Castration-Resistant Prostate Cancer... | ✅ |
| BENCH-023 | 32919526 | ✅ Sì | Association of tumour mutational burden with outcomes in pat... | ✅ |
| BENCH-024 | 29151359 | ✅ Sì | Osimertinib in Untreated EGFR-Mutated Advanced Non-Small-Cel... | ✅ |
| BENCH-025 | 29860938 | ✅ Sì | Durable Remissions with Ivosidenib in IDH1-Mutated Relapsed ... | ✅ |
| BENCH-026 | 32203698 | ✅ Sì | Pemigatinib for previously treated, locally advanced or meta... | ✅ |
| BENCH-027 | 32877583 | ✅ Sì | Capmatinib in MET Exon 14-Mutated or MET-Amplified Non-Small... | ✅ |
| BENCH-028 | 25264305 | ✅ Sì | Crizotinib in ROS1-rearranged non-small-cell lung cancer. | ✅ |
| BENCH-029 | 29072975 | ✅ Sì | Dabrafenib and Trametinib Treatment in Patients With Locally... | ✅ |
| BENCH-030 | 32469182 | ✅ Sì | Trastuzumab Deruxtecan in Previously Treated HER2-Positive G... | ✅ |

**Riepilogo verifica PMID:**
- PMID verificati: 30/30
- Esistenti su PubMed: 30/30
- Titolo CSV coerente con titolo NCBI: 29/30


### Tracciabilità di `expected_drug`

Per ogni caso, il farmaco atteso può essere verificato indirettamente controllando se il titolo del paper di riferimento (PMID) menziona il farmaco.

| case_id | expected_drug | Drug menzionato nel titolo CSV? |
|---------|---------------|-------------------------------|
| BENCH-001 | Osimertinib | ✅ |
| BENCH-002 | Alectinib | ✅ |
| BENCH-003 | Vemurafenib | ✅ |
| BENCH-004 | Trastuzumab+Pertuzumab | ❌ |
| BENCH-005 | Olaparib | ✅ |
| BENCH-006 | Imatinib | ❌ |
| BENCH-007 | Encorafenib+Cetuximab | ✅ |
| BENCH-008 | Alpelisib+Fulvestrant | ❌ |
| BENCH-009 | Imatinib | ✅ |
| BENCH-010 | Gilteritinib | ✅ |
| BENCH-011 | Osimertinib | ✅ |
| BENCH-012 | Sotorasib | ✅ |
| BENCH-013 | Lorlatinib | ✅ |
| BENCH-014 | Ponatinib | ✅ |
| BENCH-015 | Selpercatinib | ✅ |
| BENCH-016 | Larotrectinib | ✅ |
| BENCH-017 | Pembrolizumab | ✅ |
| BENCH-018 | Sotorasib+Panitumumab | ✅ |
| BENCH-019 | Sunitinib | ❌ |
| BENCH-020 | Dabrafenib+Trametinib | ✅ |
| BENCH-021 | Trastuzumab | ✅ |
| BENCH-022 | Olaparib | ✅ |
| BENCH-023 | Pembrolizumab | ❌ |
| BENCH-024 | Osimertinib | ✅ |
| BENCH-025 | Ivosidenib | ✅ |
| BENCH-026 | Pemigatinib | ✅ |
| BENCH-027 | Capmatinib | ✅ |
| BENCH-028 | Crizotinib | ✅ |
| BENCH-029 | Dabrafenib+Trametinib | ✅ |
| BENCH-030 | Trastuzumab deruxtecan | ✅ |

**Farmaco menzionato nel titolo del paper:** 25/30 (83%)

I restanti 5 casi hanno un `expected_drug` non direttamente riscontrabile nel titolo. Questo non significa che l'annotazione sia errata — il farmaco potrebbe essere nel corpo del paper — ma la tracciabilità dal CSV non è automatica.

### Tracciabilità di `escat`

Il CSV contiene il valore del tier ESCAT ma non indica da quale regola o linea guida (IASLC, ESMO Scale for Clinical Actionability) è stato derivato.

| Tier ESCAT | n | Fonte derivazione nel CSV? |
|-----------|---|---------------------------|
| I-A | 25 | ❌ Non documentata |
| I-B | 4 | ❌ Non documentata |
| non determinato | 1 | ❌ Non documentata |

**Percentuale di annotazioni con fonte esterna documentata nel CSV:** 0/30 (0%)

### Schema di provenance proposto

Per chiudere il rischio di single-annotator bias, si propone di aggiungere due colonne al CSV:

| Colonna proposta | Descrizione | Esempio |
|-----------------|-------------|---------|
| `escat_source` | Riferimento alla regola/linea guida da cui è derivato il tier | `ESMO ESCAT 2018 Table 1`, `OncoKB Level 1` |
| `drug_source` | Riferimento alla fonte del farmaco atteso | `FDA label 2023`, `EMA EPAR`, `PMID:37937763 Table 2` |

## §3 — Provenienza dei casi

### Distribuzione per rivista

| Rivista | n | % |
|---------|---|---|
| The New England journal of medicine | 21 | 70.0% |
| The Lancet. Oncology | 4 | 13.3% |
| Journal of clinical oncology : official journal of the American Society of Clinical Oncology | 2 | 6.7% |
| Science (New York, N.Y.) | 1 | 3.3% |
| European journal of cancer (Oxford, England : 1990) | 1 | 3.3% |
| Lancet (London, England) | 1 | 3.3% |

### Range temporale

- Anno più vecchio: **2001**
- Anno più recente: **2023**
- Span: **22 anni**

| Anno | n |
|------|---|
| 2001 | 1 |
| 2003 | 1 |
| 2006 | 1 |
| 2010 | 1 |
| 2011 | 1 |
| 2013 | 1 |
| 2014 | 1 |
| 2016 | 2 |
| 2017 | 2 |
| 2018 | 5 |
| 2019 | 3 |
| 2020 | 8 |
| 2021 | 1 |
| 2023 | 2 |

### Disponibilità dei testi

- Abstract disponibile: **30/30**
- Fulltext disponibile: **11/30**
- Con PMC ID: **10/30**

| Fonte fulltext | n |
|----------------|---|
| (vuoto) | 19 |
| PMC | 10 |
| Unpaywall (https://hdl.handle.net/20.500.14703/224) | 1 |

### Origine dei casi: letteratura vs sintetici

- Casi con PMID: **30/30**
- Casi con DOI: **30/30**
- Casi con journal: **30/30**
- **Casi sintetici (senza PMID/DOI/journal): 0/30**

Tutti i 30 casi derivano da paper pubblicati su riviste peer-reviewed. Nessun caso è stato costruito ad hoc.

> [!IMPORTANT]
> I casi derivano da letteratura pubblicata (nessun caso sintetico), il che riduce il rischio di *fabrication bias*. Tuttavia, i 30 casi sono stati selezionati in base alla loro copertura nella KB — questo è *selection bias by design* e va dichiarato come scelta metodologica, non come proprietà del dominio.

## §4 — Rischio di tautologia rispetto alla KB

### Campo `kb_coverage` nel CSV

| Valore | n | % |
|--------|---|---|
| COVERED | 30 | 100.0% |

**Casi COVERED:** 30/30 (100%)
**Casi GAP:** 0/30 (0%)

> [!WARNING]
> Il benchmark contiene **0 casi GAP**. Tutti i 30 casi sono classificati come COVERED nella KB. Questo significa che il benchmark non misura il comportamento del sistema in assenza di evidenza, e che un sistema KB-based è favorito per costruzione su tutte le metriche KB-dipendenti.

### Verifica PMID nella KB (query Neo4j diretta)

| case_id | PMID | Presente nella KB? |
|---------|------|--------------------|
| BENCH-001 | 37937763 | ✅ Sì |
| BENCH-002 | 28586279 | ✅ Sì |
| BENCH-003 | 21639808 | ✅ Sì |
| BENCH-004 | 26874901 | ✅ Sì |
| BENCH-005 | 30345884 | ✅ Sì |
| BENCH-006 | 11423618 | ❌ No |
| BENCH-007 | 31566309 | ✅ Sì |
| BENCH-008 | 31091374 | ✅ Sì |
| BENCH-009 | 14645423 | ✅ Sì |
| BENCH-010 | 31665578 | ✅ Sì |
| BENCH-011 | 27959700 | ✅ Sì |
| BENCH-012 | 34096690 | ✅ Sì |
| BENCH-013 | 30892989 | ❌ No |
| BENCH-014 | 24180494 | ❌ No |
| BENCH-015 | 32846060 | ✅ Sì |
| BENCH-016 | 29466156 | ✅ Sì |
| BENCH-017 | 33264544 | ❌ No |
| BENCH-018 | 37870968 | ✅ Sì |
| BENCH-019 | 16624552 | ✅ Sì |
| BENCH-020 | 27283860 | ✅ Sì |
| BENCH-021 | 20728210 | ✅ Sì |
| BENCH-022 | 32343890 | ✅ Sì |
| BENCH-023 | 32919526 | ❌ No |
| BENCH-024 | 29151359 | ❌ No |
| BENCH-025 | 29860938 | ✅ Sì |
| BENCH-026 | 32203698 | ✅ Sì |
| BENCH-027 | 32877583 | ✅ Sì |
| BENCH-028 | 25264305 | ✅ Sì |
| BENCH-029 | 29072975 | ✅ Sì |
| BENCH-030 | 32469182 | ❌ No |

**PMID presenti nella KB:** 23/30
**PMID assenti dalla KB:** 7/30

### Raggiungibilità del path Gene → Drug nella KB

Per ogni caso, verifica se esiste un path `Gene → Variant/MolecularProfile → Evidence → Drug` che arriva all'`expected_drug`.

| case_id | Gene | Tumor | Expected Drug | Path esiste? | Drug nella KB? | Drugs trovati |
|---------|------|-------|---------------|-------------|----------------|--------------|
| BENCH-001 | EGFR | NSCLC | Osimertinib | ✅ | ✅ | AFATINIB, AMIVANTAMAB, ANTI-PD-L1 MONOCLONAL ANTIBODY, ANTI-PD1 MONOCLONAL ANTIBODY, CANERTINIB ... (+27) |
| BENCH-002 | ALK | NSCLC | Alectinib | ✅ | ✅ | ALECTINIB HYDROCHLORIDE, ALK INHIBITOR TAE684, ALVESPIMYCIN, AZD3463, BRIGATINIB ... (+9) |
| BENCH-003 | BRAF | Melanoma | Vemurafenib | ✅ | ✅ | ALPELISIB, ATEZOLIZUMAB, BINIMETINIB, BRAF INHIBITOR, CAPECITABINE ... (+28) |
| BENCH-004 | ERBB2 | Breast Cancer HER2+ | Trastuzumab+Pertuzumab | ✅ | ✅ | AFATINIB, CAPECITABINE, CETUXIMAB, DACOMITINIB, ERLOTINIB ... (+24) |
| BENCH-005 | BRCA1 | Ovarian Cancer | Olaparib | ✅ | ✅ | CARBOPLATIN, CEDIRANIB, CISPLATIN, GEMCITABINE, NIRAPARIB ... (+9) |
| BENCH-006 | ABL1 | CML | Imatinib | ✅ | ✅ | AXITINIB, BAFETINIB, BOSUTINIB, DASATINIB, DEXAMETHASONE ... (+5) |
| BENCH-007 | BRAF | Colorectal Cancer | Encorafenib+Cetuximab | ✅ | ✅ | ALPELISIB, ATEZOLIZUMAB, BINIMETINIB, BRAF INHIBITOR, CAPECITABINE ... (+28) |
| BENCH-008 | PIK3CA | Breast Cancer HR+ | Alpelisib+Fulvestrant | ✅ | ✅ | AKT INHIBITOR MK2206, ALPELISIB, ANTI-EGFR MONOCLONAL ANTIBODY, APITOLISIB, ASPIRIN ... (+37) |
| BENCH-009 | KIT | GIST | Imatinib | ✅ | ✅ | DASATINIB, IMATINIB, MIDOSTAURIN, NILOTINIB, PICTILISIB ... (+5) |
| BENCH-010 | FLT3 | AML | Gilteritinib | ✅ | ✅ | AG 1295, ANTHRACYCLINE ANTINEOPLASTIC ANTIBIOTIC, AS-602868, CRENOLANIB, CYTARABINE HYDROCHLORIDE ... (+17) |
| BENCH-011 | EGFR | NSCLC | Osimertinib | ✅ | ✅ | AFATINIB, AMIVANTAMAB, ANTI-PD-L1 MONOCLONAL ANTIBODY, ANTI-PD1 MONOCLONAL ANTIBODY, CANERTINIB ... (+27) |
| BENCH-012 | KRAS | NSCLC | Sotorasib | ✅ | ✅ | ABEMACICLIB, ADAGRASIB, AFATINIB, AKT INHIBITOR MK2206, ATEZOLIZUMAB ... (+40) |
| BENCH-013 | ALK | NSCLC | Lorlatinib | ✅ | ✅ | ALECTINIB HYDROCHLORIDE, ALK INHIBITOR TAE684, ALVESPIMYCIN, AZD3463, BRIGATINIB ... (+9) |
| BENCH-014 | ABL1 | CML | Ponatinib | ✅ | ✅ | AXITINIB, BAFETINIB, BOSUTINIB, DASATINIB, DEXAMETHASONE ... (+5) |
| BENCH-015 | RET | NSCLC | Selpercatinib | ✅ | ✅ | AGERAFENIB, ALECTINIB HYDROCHLORIDE, EVEROLIMUS, JAK2 INHIBITOR AZD1480, MOTESANIB ... (+5) |
| BENCH-016 | NTRK1 | Solid Tumor | Larotrectinib | ✅ | ✅ | CRIZOTINIB, ENTRECTINIB, LAROTRECTINIB SULFATE, LESTAURTINIB, REPOTRECTINIB ... (+1) |
| BENCH-017 | MMR | Colorectal Cancer | Pembrolizumab | ❌ | ❌ |  |
| BENCH-018 | KRAS | Colorectal Cancer | Sotorasib+Panitumumab | ✅ | ✅ | ABEMACICLIB, ADAGRASIB, AFATINIB, AKT INHIBITOR MK2206, ATEZOLIZUMAB ... (+40) |
| BENCH-019 | KIT | GIST | Sunitinib | ✅ | ✅ | DASATINIB, IMATINIB, MIDOSTAURIN, NILOTINIB, PICTILISIB ... (+5) |
| BENCH-020 | BRAF | NSCLC | Dabrafenib+Trametinib | ✅ | ✅ | ALPELISIB, ATEZOLIZUMAB, BINIMETINIB, BRAF INHIBITOR, CAPECITABINE ... (+28) |
| BENCH-021 | ERBB2 | Gastric Cancer | Trastuzumab | ✅ | ✅ | AFATINIB, CAPECITABINE, CETUXIMAB, DACOMITINIB, ERLOTINIB ... (+24) |
| BENCH-022 | BRCA2 | Prostate Cancer | Olaparib | ✅ | ✅ | CARBOPLATIN, CEDIRANIB, CISPLATIN, GEMCITABINE, INIPARIB ... (+10) |
| BENCH-023 | TMB | Solid Tumor | Pembrolizumab | ✅ | ✅ | ATEZOLIZUMAB, CAMRELIZUMAB, DURVALUMAB, NIVOLUMAB, PD1 INHIBITOR ... (+3) |
| BENCH-024 | EGFR | NSCLC | Osimertinib | ✅ | ✅ | AFATINIB, AMIVANTAMAB, ANTI-PD-L1 MONOCLONAL ANTIBODY, ANTI-PD1 MONOCLONAL ANTIBODY, CANERTINIB ... (+27) |
| BENCH-025 | IDH1 | AML | Ivosidenib | ✅ | ✅ | AGI-5198, DASATINIB, IVOSIDENIB, OLAPARIB, SUNITINIB ... (+3) |
| BENCH-026 | FGFR2 | Cholangiocarcinoma | Pemigatinib | ✅ | ✅ | DERAZANTINIB, DOVITINIB, ERDAFITINIB, FEXAGRATINIB, INFIGRATINIB ... (+4) |
| BENCH-027 | MET | NSCLC | Capmatinib | ✅ | ✅ | CAPMATINIB HYDROCHLORIDE, CARMUSTINE, CETUXIMAB, CRIZOTINIB, ERLOTINIB ... (+13) |
| BENCH-028 | ROS1 | NSCLC | Crizotinib | ✅ | ✅ | ALK INHIBITOR TAE684, AZD3463, BRIGATINIB, CERITINIB, CRIZOTINIB ... (+3) |
| BENCH-029 | BRAF | Thyroid Cancer | Dabrafenib+Trametinib | ✅ | ✅ | ALPELISIB, ATEZOLIZUMAB, BINIMETINIB, BRAF INHIBITOR, CAPECITABINE ... (+28) |
| BENCH-030 | ERBB2 | Gastric Cancer | Trastuzumab deruxtecan | ✅ | ✅ | AFATINIB, CAPECITABINE, CETUXIMAB, DACOMITINIB, ERLOTINIB ... (+24) |

**Path Gene→Drug esiste:** 29/30
**Expected drug raggiungibile:** 29/30

Il 97% degli expected_drug è raggiungibile nella KB. I restanti 1 casi hanno un expected_drug non direttamente raggiungibile dal path standard Gene→Drug.

## §5 — Completezza della catena di provenance

### Anelli presenti nel CSV

| Anello della catena | Campo CSV | Presente? | Casi popolati |
|--------------------|-----------|-----------:|---------------|
| Gene | `gene` | ✅ | 30/30 |
| Variante | `variant` | ✅ | 30/30 |
| Tipo tumore (Disease) | `tumor` | ✅ | 30/30 |
| Farmaco atteso (Drug) | `expected_drug` | ✅ | 30/30 |
| PMID (Publication) | `pmid` | ✅ | 30/30 |
| DOI | `doi` | ✅ | 30/30 |
| Tier ESCAT | `escat` | ✅ | 30/30 |
| Categoria clinica | `category` | ✅ | 30/30 |
| Tipo alterazione | `alteration_type` | ✅ | 30/30 |

### Anelli assenti dal CSV

| Anello della catena | Stato |
|--------------------|----- |
| Evidence (nodo intermedio) | ❌ Non presente nel CSV — esiste solo nel grafo Neo4j |
| CompanionDiagnostic | ❌ Non presente nel CSV |
| Annotator ID | ❌ Non presente nel CSV |
| Annotation source | ❌ Non presente nel CSV |
| Livello di evidenza (A/B) | ❌ Non presente nel CSV — è proprietà del nodo Evidence nel grafo |
| Significance (Sensitivity/Resistance) | ❌ Non presente nel CSV — è proprietà del nodo Evidence nel grafo |
| Contesto clinico (linea, stadio) | ❌ Non presente nel CSV — solo `category` come proxy |

### Completezza per caso

I 6 campi core della catena gold standard sono: `gene`, `variant`, `tumor`, `expected_drug`, `pmid`, `escat`.

**Tutti i 30 casi hanno i 6 campi core popolati.**

## §6 — Limiti metodologici dichiarati

Elenco di fatti misurati che espongono il benchmark a possibili critiche metodologiche. Nessun giudizio di valore.

1. **Selection bias by design.** I 30 casi sono stati selezionati in base alla loro copertura nella KB (tutti COVERED, 0 GAP). Il benchmark non include casi in cui la KB non contiene evidenza. Un sistema KB-based è favorito per costruzione sulle metriche KB-dipendenti (evidence grounding, PMID citation rate). Il benchmark non misura il comportamento del sistema in assenza di informazione.

2. **Assenza di campi di provenance.** Il CSV non contiene colonne che documentino la fonte delle annotazioni `expected_drug` e `escat` (nessun `annotation_source`, `guideline_reference`, `annotator_id`). Non è possibile verificare programmaticamente se le annotazioni sono trascritte da fonti autorevoli o sono giudizio del singolo annotatore. Questo espone alla critica di *single-annotator bias*.

3. **Categorie singleton.** 22 categorie sono rappresentate da un singolo caso, distribuiti così: `alteration_type`: itd; `tumor`: Melanoma, Breast Cancer HER2+, Ovarian Cancer, Breast Cancer HR+, Prostate Cancer, Cholangiocarcinoma, Thyroid Cancer; `gene`: BRCA1, PIK3CA, FLT3, RET, NTRK1, MMR, BRCA2, TMB, IDH1, FGFR2, MET, ROS1; `escat`: non determinato; `category`: biomarker. Nessuna analisi stratificata è affidabile su queste categorie (n=1).

4. **Dimensione campionaria.** N=30. Non è possibile calcolare intervalli di confidenza statisticamente significativi per le metriche stratificate per dimensione (es. performance per tipo di tumore o per tier ESCAT).

5. **Sbilanciamento ESCAT.** Il tier `I-A` rappresenta 25/30 (83%) dei casi. Il benchmark misura prevalentemente la capacità su un singolo livello di evidenza.

6. **Sovra-rappresentazione tumorale.** `NSCLC` rappresenta 10/30 (33%) dei casi.

7. **Nessun inter-annotator agreement.** Il benchmark non documenta se le annotazioni sono state validate da un secondo annotatore o da un comitato. Non è possibile calcolare un Cohen's κ o un Fleiss' κ.

8. **Concentrazione editoriale.** 21/30 (70%) dei paper provengono da *The New England journal of medicine*.
