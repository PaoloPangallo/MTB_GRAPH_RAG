# Stabilità primaria: run_index=1 vs run_index=2

Confronto diretto tra le due run sullo stesso trasporto forzato (25
bundle, 100 core-field slot per run).

## Stabilità per bundle

| Categoria | Conteggio |
|---|---:|
| `FULLY_STABLE` | 10 |
| `SEMANTICALLY_STABLE` | 6 |
| `PARTIALLY_STABLE` | 1 |
| `UNSTABLE` | 0 |
| `NOT_COMPARABLE_TRANSPORT` | 8 |

**Zero bundle instabili** (nessun conflitto di valore, nessuna direzione
incompatibile, nessuna perdita di contraddizione, nessun disaccordo
sull'esito positivo/non positivo) sui 17 bundle comparabili. 8/25 bundle
non sono comparabili perché almeno una delle due run non ha prodotto un
transport valido su quel bundle specifico.

## Metriche (sui bundle comparabili, 17)

| Metrica | Valore |
|---|---:|
| Full-slot agreement (100 slot, inclusi assenti) | 67% |
| Active-field agreement (solo campi proposti/accettati in almeno una run) | 43.1% |
| Normalized-value agreement (active) | 19.0% |
| Accepted-field-set agreement | 94.1% |
| Final-status agreement | 100% |
| Validator-outcome agreement | 100% |
| Abstention agreement | 100% |
| Direction agreement (solo bundle dove almeno una run propone direction, n=7) | 42.9% |
| Exact field reproduction (slot) | 8 |
| Equivalent validated support (slot, quote/SourceUnit diversi, stesso valore) | 3 |

## Lettura

L'accordo su *cosa il sistema conclude* è quasi perfetto (status finale,
esito del validatore, astensione: tutti al 100% sui bundle comparabili) —
quando il transport funziona in entrambe le run, il validatore arriva
sistematicamente alla stessa decisione complessiva. L'accordo sul *valore
normalizzato dei singoli campi attivi* è invece basso (19%): la maggior
parte degli slot attivi sono `SAME_AMBIGUITY` (campo proposto ma scartato
in entrambe le run, nessun valore validato da confrontare), non
disaccordi di valore veri e propri (`VALUE_DISAGREEMENT`=0,
`DIRECTION_DISAGREEMENT`=0 su tutti i 100 slot). Il fattore limitante
dominante è l'instabilità del *transport* (8/25 bundle non comparabili,
tasso di validità 88% e 80%), non l'incoerenza semantica quando il
transport funziona.
