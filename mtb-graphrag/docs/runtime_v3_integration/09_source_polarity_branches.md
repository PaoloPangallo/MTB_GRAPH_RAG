# 09 — Rami della polarita' della sorgente

| `source_alignment_status` | Candidate v3 | Trattamento runtime |
|---|---|---|
| `SOURCE_ALIGNED` | 6 420 | document grounding normale |
| `SOURCE_DOES_NOT_SUPPORT` | **873** | ramo negativo/audit, **mai** primary positive |
| `SOURCE_NEUTRAL` | **161** | ramo neutro, non promossa a supporto |
| `SOURCE_CONTRADICTS` | 0 | ramo contraddizione |
| `SOURCE_ALIGNMENT_UNCLEAR` | 0 | ammessa con warning |
| `SOURCE_ALIGNMENT_NOT_AVAILABLE` | 38 688 | ammessa con `SOURCE_POLARITY_UNAVAILABLE` |

## `SOURCE_DOES_NOT_SUPPORT`

* non entra come primary positive;
* entra nel ramo negativo/audit;
* **preserva `graph_direction`** senza invertirla;
* mostra la posizione della fonte.

Il warning emesso e' `GRAPH_DIRECTION_PRESERVED_NOT_INVERTED`: la direzione
proposta dal grafo resta quella, e non diventa il suo opposto.

## `SOURCE_ALIGNMENT_NOT_AVAILABLE`

Il metadato manca — sono le regole non-Evidence (gene-drug, trial, companion
diagnostic). La candidate:

* **non** e' etichettata `SOURCE_ALIGNED`;
* e' ammessa con warning `SOURCE_POLARITY_UNAVAILABLE`;
* porta `DOCUMENT_GROUNDING_STILL_REQUIRED` fra i reason code;
* **non** e' promossa per la sola assenza del metadato.

## Separazione nel dossier

| Ramo |
|---|
| A — positive or normal grounding |
| B — negative / does not support audit |
| C — neutral audit |
| D — source polarity unknown |
| E — unresolved regimen limitations |
| F — compound alteration partial or insufficient match |

Una candidate audit-only **non puo'** entrare nelle evidenze positive: e'
codificato in `AUDIT_ONLY_STATUSES` e verificato da test.

**Limite:** la separazione e' definita e testata a livello di ammissione, ma il
dossier non e' stato costruito con candidate v3
(cfr. `13_runtime_switch_decision.md`).
