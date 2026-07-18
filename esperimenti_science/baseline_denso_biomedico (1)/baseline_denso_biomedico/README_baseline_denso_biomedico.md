# Baseline denso biomedico — pacchetto riproducibile

Esperimento della tesi **mtb-graphrag** (Priorità 1): il divario del RAG denso
è dell'encoder generico o del metodo? Si sostituisce `all-MiniLM-L6-v2` con
encoder biomedici e si ripete lo stesso sweep di budget con la stessa metrica
(recall dei fatti-gold, deterministica e offline).

## Risultato in una riga

L'encoder biomedico **retrieval-tuned** (`S-PubMedBert-MS-MARCO`) più che
raddoppia la recall a budget 900 (0,293 → 0,639), ma resta sotto BM25/ibrido e
lontano dal GraphRAG (1,00). Il controllo con PubMedBERT **grezzo** (0,144)
dimostra che a recuperare il divario è il **fine-tuning per il retrieval**, non
il vocabolario biomedico in sé.

## Contenuto del pacchetto

| File | Descrizione |
|---|---|
| `06_baseline_denso_biomedico.py` | Script standalone: codifica il corpus con gli encoder biomedici (se i `.npy` mancano), calcola lo sweep e rigenera figura + CSV. |
| `biomedical_dense_sweep.csv` | 72 righe (6 sistemi × 12 budget): `system, budget, retr_recall, mean_ctx_words`. |
| `fig11_biomedical_dense.png` | Figura a 2 pannelli: (a) curve recall vs contesto; (b) barre a budget 900 con i due effetti annotati. |
| `analisi_baseline_denso_biomedico.md` | Analisi discorsiva con tabelle e tre conclusioni. |
| `capitolo_baseline_denso_biomedico.tex` | Capitolo LaTeX (compila standalone con `tectonic`). |
| `capitolo_baseline_denso_biomedico.pdf` | PDF compilato (3 pagine). |

## Riproduzione

```bash
python 06_baseline_denso_biomedico.py
tectonic capitolo_baseline_denso_biomedico.tex
```

Lo script cerca i checkpoint `corpus_emb_pubmedbert_msmarco.npy` e
`corpus_emb_pubmedbert_raw.npy`; se assenti, li ricalcola (su CPU ~35 min per
l'encoder MS-MARCO, ~50 min per il grezzo). Richiede inoltre i checkpoint già
prodotti dagli script precedenti: `rag_corpus.pkl`, `corpus_emb.npy`,
`benchmark_multihop_qa.csv`, `context_budget_sweep.csv`.

## Encoder usati

- `all-MiniLM-L6-v2` — generico, retrieval-tuned (incumbent, 384-dim)
- `pritamdeka/S-PubMedBert-MS-MARCO` — biomedico + fine-tuning retrieval (768-dim)
- `microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext` — biomedico grezzo, mean-pooling (768-dim)

## Metrica

Recall dei fatti-gold nel contesto assemblato: per ogni domanda si accumulano
i passaggi meglio classificati fino a saturare il budget di parole, poi si
conta quanti nomi-gold (geni, farmaci, varianti) compaiono nel testo. È
identica a quella dello script `05_sweep_budget_contesto.py`, così i sistemi
sono direttamente confrontabili.
