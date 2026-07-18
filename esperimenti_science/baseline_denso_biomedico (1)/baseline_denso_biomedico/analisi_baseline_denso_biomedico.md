# Baseline denso biomedico — il divario del RAG denso è dell'encoder o del retrieval?

## Domanda di ricerca

Nell'esperimento principale e nello sweep di budget, il **RAG denso** con
encoder generico (`all-MiniLM-L6-v2`) resta la configurazione più debole:
recall dei fatti-gold da **0,14** (100 parole) a **0,39** (2400 parole), sempre
molto sotto BM25/ibrido e lontanissima dal tetto del GraphRAG (1,00). Prima di
concludere che «il retrieval denso non funziona su questo corpus» occorre
isolare la causa: è colpa dell'**encoder** (vocabolario generico, non
biomedico) o è un limite **strutturale** del dense retrieval su una base di
conoscenza fatta di fatti brevi e nomi propri (geni, farmaci, varianti)?

Per rispondere ho sostituito l'encoder generico con encoder di **dominio
biomedico**, mantenendo **identica** la metrica (recall dei fatti-gold nel
contesto assemblato, deterministica e offline) e lo **stesso** sweep di budget.

## Sistemi confrontati

| Sistema | Encoder | Natura |
|---|---|---|
| RAG denso (all-MiniLM) | `all-MiniLM-L6-v2` (384-dim) | generico, retrieval-tuned |
| RAG denso (PubMedBERT grezzo) | `microsoft/BiomedNLP-BiomedBERT` (768-dim, mean-pool) | **solo** pre-training di dominio (MLM) |
| RAG denso (PubMedBERT-MS) | `pritamdeka/S-PubMedBert-MS-MARCO` (768-dim) | dominio **+** fine-tuning per il retrieval |

Riferimenti già misurati: GraphRAG (1,00 piatto), BM25, ibrido.

## Risultati

### Recall dei fatti-gold a tre budget

| Sistema | 100 parole | 900 parole | 2400 parole |
|---|---|---|---|
| **GraphRAG** | **1,000** | **1,000** | **1,000** |
| RAG BM25 | 0,541 | 0,835 | 0,934 |
| RAG ibrido | 0,563 | 0,825 | 0,889 |
| **RAG denso (PubMedBERT-MS)** | 0,369 | **0,639** | 0,764 |
| RAG denso (all-MiniLM) | 0,139 | 0,293 | 0,390 |
| RAG denso (PubMedBERT grezzo) | 0,017 | 0,144 | 0,244 |

### Parole di contesto necessarie per raggiungere una soglia di recall

| Sistema | ≥ 60 % | ≥ 70 % | ≥ 80 % |
|---|---|---|---|
| GraphRAG | 36 | 36 | 36 |
| RAG BM25 | 144 | 251 | 575 |
| RAG ibrido | 112 | 226 | 690 |
| RAG denso (PubMedBERT-MS) | 669 | 1543 | mai |
| RAG denso (all-MiniLM) | mai | mai | mai |
| RAG denso (PubMedBERT grezzo) | mai | mai | mai |

## Tre conclusioni

**1. L'encoder biomedico recupera gran parte del divario — ma non tutto.**
Passando da `all-MiniLM` a `S-PubMedBert-MS-MARCO` la recall a budget 900 più
che raddoppia: **0,293 → 0,639** (+0,35). Il denso biomedico raggiunge ≥60 % di
recall (a 669 parole) e ≥70 % (a 1543 parole), soglie che l'encoder generico
non tocca **mai** nell'intero sweep. Il divario del RAG denso, quindi, era in
larga parte un **artefatto dell'encoder**, non un limite assoluto del metodo.

**2. Non è il «vocabolario biomedico» a fare la differenza, ma il
fine-tuning per il retrieval.** Il controllo cruciale è il PubMedBERT
**grezzo** (solo masked-LM su testo biomedico, mean-pooling, nessun
addestramento per la similarità semantica): la sua recall a budget 900 è
**0,144**, cioè **peggiore** persino dell'encoder generico all-MiniLM (0,293).
Il pre-training di dominio da solo, senza obiettivo contrastivo, produce
embedding inadatti al retrieval. È il fine-tuning su coppie query–passaggio
(MS-MARCO) a spostare la recall da 0,144 a 0,639 (+0,50). La lezione
metodologica: per il retrieval conta **come** l'encoder è stato addestrato,
non solo **su quale** dominio.

**3. Anche il miglior encoder denso resta sotto BM25/ibrido e lontano dal
GraphRAG.** A budget 900 il denso biomedico (0,639) non raggiunge né BM25
(0,835) né l'ibrido (0,825), e anche spingendo a 2400 parole (0,764) non tocca
il tetto del grafo (1,00), raggiunto dal GraphRAG con **36 parole**. Su una
base di conoscenza fatta di **nomi propri e fatti brevi** — dove la
corrispondenza esatta di un simbolo genico o di un nome di farmaco è ciò che
conta — il retrieval lessicale e quello strutturato del grafo restano più
adatti della similarità densa, per quanto specializzata.

## Implicazione per la tesi

Questo esperimento chiude una possibile obiezione al confronto principale
(«il RAG denso perde solo perché usa un encoder generico»). La risposta è
articolata: (a) un encoder biomedico **retrieval-tuned** recupera buona parte
del divario e va usato come baseline denso corretto; (b) tuttavia neppure quel
sistema raggiunge la recall del retrieval lessicale, né la compattezza e la
completezza del GraphRAG; (c) il vantaggio del grafo — recall 1,00 con ~36
parole di contesto — non è replicabile alzando la dimensionalità o la
specializzazione dell'encoder denso, perché deriva dal **modo** in cui i fatti
sono collegati, non dalla loro rappresentazione vettoriale.

## Riproducibilità

- **Metrica:** identica a `05_sweep_budget_contesto.py` — recall dei fatti-gold
  nel contesto assemblato con `pack_context` (accumulo fino a saturazione del
  budget). Deterministica, offline, nessuna chiave Ollama.
- **Script:** `06_baseline_denso_biomedico.py` (ricalcola gli embedding se
  mancano; su CPU ~35 min per l'encoder MS-MARCO, ~50 min per il grezzo).
- **Checkpoint:** `corpus_emb_pubmedbert_msmarco.npy`,
  `corpus_emb_pubmedbert_raw.npy` (entrambi 20 679 × 768, float32).
- **Dati:** `biomedical_dense_sweep.csv` (72 righe: 6 sistemi × 12 budget).
- **Figura:** `fig11_biomedical_dense.png` (pannello a: curve recall vs
  contesto; pannello b: barre a budget 900 con i due effetti annotati).
