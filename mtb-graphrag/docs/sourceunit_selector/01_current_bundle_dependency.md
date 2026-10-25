# La dipendenza attuale dai bundle congelati

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

## 1. I tre punti in cui il gold entra nel runtime

| File | Riga | Cosa fa |
|---|---|---|
| `retrieval/kg_retrieval.py` | 139 | copia `source_unit_ids` del bundle nell'associazione, troncati a `MAX_SOURCE_UNITS_PER_DOCUMENT` |
| `retrieval/paper_selection.py` | 35-36 | risolve quegli id contro le unità disponibili; se nessuna ha testo, esclude il bundle |
| `orchestrator.py` | 543, 595 | raccoglie gli id richiesti e costruisce `paper_units` per l'enricher |

Il flusso è quindi: **il pilot ha scelto una volta quali passaggi contano, e il
runtime da allora li rilegge**.

## 2. Perché ha funzionato finora

Il corpus è chiuso. I 25 bundle coprono 25 documenti già presenti nella cache, e
per ciascuno esiste una lista curata di unità. Finché il documento è uno di
quelli, la lista c'è.

Non è un difetto di progetto: è la conseguenza di un pilot che ha congelato
deliberatamente i propri artefatti per renderli riproducibili.

## 3. Perché non regge su un documento nuovo

`bundle["source_unit_ids"]` contiene identificatori
`SU-<sha256(document_id, unit_type, text, offset)>`. Sono legati al contenuto
esatto di quel documento. Per un articolo mai visto:

- non esiste alcun bundle;
- non esiste alcuna lista;
- `resolved_units` è vuota;
- il bundle esce con `TEXT_NOT_AVAILABLE_IN_CACHE`;
- l'enricher non viene mai chiamato.

La pipeline non fallisce con un errore: **tace**. È il modo peggiore in cui un
componente mancante può manifestarsi.

## 4. Dimensione del problema

| Fascia documento | Bundle | Unità nel documento |
|---|---:|---|
| piccolo (<20 unità) | 16 | 6-17 |
| medio (20-99) | 2 | 20-99 |
| grande (100+) | 7 | fino a **473** |

Sui documenti piccoli la selezione conta poco: prendere le prime quattro unità
di un record ClinicalTrials significa quasi sempre prendere quelle giuste. È sui
sette documenti grandi che il problema è reale, e sono esattamente i full text
PMC — cioè il materiale con più valore probatorio.

## 5. Il gold, e cosa non è

I 76 identificatori dei bundle sono l'unico riferimento disponibile su quali
passaggi fossero rilevanti. Vengono usati **solo per valutare**, mai in
inferenza.

Ma non sono una verità sulla rilevanza: sono la scelta che il pilot fece, con la
sua granularità. Il corpus lo mostra:

| unit_type | unità nel corpus | quante sono gold | tasso |
|---|---:|---:|---:|
| `FULLTEXT_SENTENCE` | 1595 | 5 | 0.31% |
| `FULLTEXT_PARAGRAPH` | 211 | 14 | 6.64% |
| `ABSTRACT_SENTENCE` | 187 | 22 | 11.76% |
| `ABSTRACT` | 13 | 13 | 100% |
| `FULLTEXT_SECTION` | 115 | 0 | 0% |

Il pilot preferiva unità coarse e auto-contenute. Riprodurre il gold significa
quindi in parte riprodurre quella preferenza, non solo trovare i passaggi
giusti. La valutazione ne tiene conto misurando anche i *near miss*: unità scelte
il cui testo coincide con una gold a un diverso livello di taglio.
