# Filone: Efficienza di contesto (sweep del budget)

Pacchetto autonomo che documenta l'esperimento di *sweep del budget di
contesto* per la tesi mtb-graphrag. Risponde all'obiezione: il vantaggio di
efficienza del GraphRAG è un artefatto del budget di 900 parole scelto per il
confronto, o regge concedendo al RAG testuale molto più contesto?

Risposta: regge. Il GraphRAG raggiunge recall dei fatti-gold = 1,00 con ~36
parole; BM25 e ibrido, anche con 2400 parole (≈2,7× il budget della tesi),
saturano a 0,93 e 0,89 senza mai raggiungere il tetto del grafo; il RAG denso
resta sotto 0,40 lungo tutto lo sweep (limite dell'encoder, non del budget).

## Contenuto del pacchetto

| File | Descrizione |
|------|-------------|
| `capitolo_efficienza_contesto.tex` | Capitolo LaTeX autonomo (preambolo completo, compilabile con `tectonic`). |
| `capitolo_efficienza_contesto.pdf` | Capitolo compilato (3 pagine): domanda, metodo, due tabelle, figura, interpretazione. |
| `analisi_efficienza_contesto.md` | Stessa analisi in Markdown, pronta da inserire nel report principale. |
| `fig10_context_budget.png` | Figura a 2 pannelli: (a) curva recall vs parole di contesto in scala log; (b) parole necessarie per soglia di recall. |
| `context_budget_sweep.csv` | Dati grezzi dello sweep: 4 sistemi × 12 budget = 48 righe (recall e parole di contesto medie). |
| `05_sweep_budget_contesto.py` | Script standalone che rigenera sweep e figura dai checkpoint. |

## Riproduzione

```bash
# Richiede i checkpoint prodotti dallo script 01_sistemi_retrieval nella stessa cartella:
#   rag_corpus.pkl, corpus_emb.npy, benchmark_multihop_qa.csv
python 05_sweep_budget_contesto.py
#   -> context_budget_sweep.csv
#   -> fig10_context_budget.png @300dpi

# Compilare il capitolo (richiede fig10_context_budget.png nella stessa cartella):
tectonic capitolo_efficienza_contesto.tex
#   -> capitolo_efficienza_contesto.pdf
```

Lo sweep è interamente **offline**: la metrica è la recall dei fatti-gold nel
contesto assemblato, che è deterministica e non richiede il modello lettore
(nessuna chiave Ollama necessaria).

## Dipendenze

pandas, numpy, rank-bm25, sentence-transformers, scikit-learn, matplotlib.
Python 3.12.
