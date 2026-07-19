# Script di riproducibilita

Questa cartella raccoglie i 15 script consegnati insieme agli artefatti della
tesi. Sono separati dal backend applicativo: non vengono importati dall'API e
non sono necessari per eseguire la demo comparativa.

## Gruppi

- `04_`--`10_`: studi secondari, robustezza, profondita, multi-answer e router.
- `run_reader_*`: esecuzioni dei reader nelle diverse condizioni.
- `run_router_generico.py`: valutazione del router.
- `run_parafrasi_generico.py`: robustezza alle parafrasi.
- `_encode_raw_pubmedbert.py`: generazione portabile degli embedding.
- `_run_sweep_1k.py`: orchestrazione dello sweep sul sottoinsieme da 1000 casi.

## Artefatti richiesti

Gli script non costituiscono da soli una replica completa. In base
all'esperimento possono essere necessari `kb_graph.gpickle`, `rag_corpus.pkl`,
matrici `.npy`, benchmark CSV e un endpoint LLM configurato. Gli artefatti
pesanti non devono essere aggiunti direttamente a Git: usare una release,
Git LFS o un archivio esterno, pubblicando checksum e licenza.

## Esempio PubMedBERT

```bash
python _encode_raw_pubmedbert.py \
  --corpus /percorso/rag_corpus.pkl \
  --output /percorso/corpus_emb_pubmedbert_raw.npy
```

Nessuno script deve contenere credenziali, dati identificativi di pazienti o
path assoluti legati a una singola macchina.
