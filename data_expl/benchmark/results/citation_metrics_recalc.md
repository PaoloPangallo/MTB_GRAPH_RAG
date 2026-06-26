# Ricalcolo delle metriche di citazione per l'ablation study

> Report generato automaticamente.
> Ground truth ESTERNO: PubMed (via NCBI E-utilities).
> Ground truth INTERNO: Grafo Neo4j (GraphRAGTesi).

## Tabella 1: Fabrication Rate (Ground Truth Esterno)

*Metrica KB-indipendente: confrontabile alla pari tra tutte le condizioni. Indica quanti PMID citati non esistono affatto in letteratura.*
*Nota: i PMID che hanno subito timeout NCBI non sono contati nel denominatore.*

| Condizione | PMID Totali Citati | Non verificabili (Rete) | Esistenti su PubMed (NCBI) | Fabbricati (Inventati) | Fabrication Rate |
|------------|-------------------|-------------------------|----------------------------|------------------------|------------------|
| vanilla | 115 | 0 | 111 | 4 | **3.5%** |
| websearch | 134 | 0 | 134 | 0 | **0.0%** |
| rag_testuale | 238 | 0 | 238 | 0 | **0.0%** |
| enricher_only | 104 | 0 | 104 | 0 | **0.0%** |
| full_graphrag | 150 | 0 | 150 | 0 | **0.0%** |

## Tabella 2: KB-Groundedness (Ground Truth Interno)

*Metrica KB-dipendente. Indica la frazione di PMID citati che deriva effettivamente dai nodi Publication presenti nel grafo. Il confronto leale è solo tra `full_graphrag` e `rag_testuale`.*

| Condizione | PMID Totali Citati | Tracciabili nel KG Neo4j | KB-Groundedness | Note |
|------------|-------------------|--------------------------|-----------------|------|
| vanilla | 115 | 0 | **0.0%** | no-KB, riferimento |
| websearch | 134 | 0 | **0.0%** | no-KB, riferimento |
| rag_testuale | 238 | 218 | **91.6%** | Confronto leale |
| enricher_only | 104 | 38 | **36.5%** | no-KB, riferimento |
| full_graphrag | 150 | 150 | **100.0%** | Confronto leale |

### Casi biomarker speciali (full_graphrag)
- **BENCH-017**: 2 PMID citati, di cui 2 collegati nel grafo.
- **BENCH-023**: 6 PMID citati, di cui 6 collegati nel grafo.
