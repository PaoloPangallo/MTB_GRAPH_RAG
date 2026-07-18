# Strand E — Scaling della profondità dei salti (deep-hop)

Esperimento aggiuntivo per la tesi **mtb-graphrag**. Misura come recall terminale e
completezza della catena si comportano quando la profondità del ragionamento clinico
cresce da 1 a 8 salti, confrontando GraphRAG con tre RAG (BM25, ibrido, denso MiniLM).

## Risultato in una riga

GraphRAG domina ad ogni profondità; la **completezza della catena** è la metrica che
separa i paradigmi: GraphRAG degrada con grazia (1,00 → 0,71) perché ogni cammino è
completo per costruzione, mentre il RAG denso resta sotto 0,20 dovendo coprire ogni salto
in modo indipendente.

## File

| File | Descrizione |
|------|-------------|
| `08_profondita_salti.py` | Script standalone riproducibile (SEED=20240517, offline, nessun LLM). |
| `benchmark_deep_hops.csv` | 637 domande annidate: ancora, profondità, terminale gold, catena-ponte (JSON), domanda in italiano. |
| `deep_hops_sweep.csv` | Recall per sistema × profondità × metrica (terminale + catena). |
| `fig13_profondita_salti.png` | Figura principale a doppio pannello (recall terminale + chain-recall). |
| `deep_hops_fanout.png` | Covariata: passaggi distinti che testimoniano la catena vs profondità. |
| `analisi_profondita_salti.md` | Analisi discorsiva completa con tabelle. |
| `capitolo_profondita_salti.tex` / `.pdf` | Capitolo di tesi (LaTeX + PDF, 4 pagine). |

## Come rieseguire

```bash
python 08_profondita_salti.py
```

Richiede i checkpoint sul disco di lavoro: `kb_graph.gpickle`, `rag_corpus.pkl`,
`corpus_emb.npy`, `benchmark_deep_hops.csv`. Rigenera `deep_hops_sweep.csv`,
`fig13_profondita_salti.png`, `deep_hops_fanout.png`. Lo sweep è verificato bit-identico
alla versione qui inclusa.

## Disegno in breve

- **Spina tipizzata unica**: Gene → Variant → MolecularProfile → Evidence → Drug →
  CompanionDiagnostic → Gene′ → Variant′ → MolecularProfile′.
- **Stesso gene-ancora ad ogni profondità** (91 geni con cammino canonico completo a
  profondità 8) → la profondità è l'unica variabile.
- Profondità 3 esclusa (terminale = Evidence, privo di nome). Profondità usate: 1, 2, 4,
  5, 6, 7, 8.
- Metrica name-in-text (coerente con gli strand B/C/D); router = oracolo.
