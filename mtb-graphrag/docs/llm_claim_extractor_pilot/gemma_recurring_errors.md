# Ricorrenza degli errori (run 0 / run 1 / run 2)

Per ogni bundle e tipo di errore, occorrenze su 3 run:
3/3 = `REPEATED_ERROR`, 2/3 = `INTERMITTENT_ERROR`, 1/3 = `ONE_OFF_ERROR`.

| Classificazione | Conteggio |
|---|---:|
| `REPEATED_ERROR` | 21 |
| `INTERMITTENT_ERROR` | 12 |
| `ONE_OFF_ERROR` | 19 |

## Errori sistematici (REPEATED_ERROR, presenti in tutte e 3 le run)

- **Astensione** (`ABSTENTION`): 8 bundle. Il modello si astiene in modo
  consistente sugli stessi bundle in tutte e 3 le run — comportamento
  sistematico, non casuale.
- **Direction errata** (`DIRECTION_ERROR`): 3 bundle.
- **Campo graph-only proposto**: 3 bundle.
- **Negazione persa**: 1 bundle.
- **Quote inesistente proposta** (mai accettata): 2 bundle.
- **"Contraddizione persa"**: 2 bundle (i due bundle baseline
  `CONTRADICTED`). Da leggere con cautela — vedi nota sotto.

### Nota sulla "contraddizione persa"

Questa etichetta qui significa "`final_support_status` non è mai
`CONTRADICTED`" per un bundle con baseline `CONTRADICTED`. Il calcolo
deterministico dello status (`deterministic_support`, invariato) mappa
sempre `ABSTAINED` -> `AMBIGUOUS`, mai -> `CONTRADICTED`, indipendentemente
dal contenuto del documento. Poiché il modello si astiene quasi sempre su
questi 2 bundle (comportamento sicuro, nessun supporto positivo prodotto),
questa ricorrenza è in gran parte un effetto strutturale della pipeline
deterministica, non necessariamente un fallimento di comprensione del
modello — l'astensione stessa è l'esito corretto per il criterio C dello
Stadio 1/2 (nessuna promozione a positivo).

## Errori intermittenti e one-off

Concentrati su bundle con trasporto instabile (`tool_choice ignorato`,
`risposta testuale`) — questi sono per definizione condizionati dalla
riuscita del transport in quella specifica run, quindi la loro
intermittenza riflette principalmente la variabilità del transport, non
del ragionamento del modello.
