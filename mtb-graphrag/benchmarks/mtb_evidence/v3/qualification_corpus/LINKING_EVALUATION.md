# Valutazione del linking statement-profilo

Il linker valutato e' quello reale della pipeline, non una sua riscrittura:
una copia divergerebbe, e la valutazione misurerebbe la copia.

## Prediction del linker

| Stato | Coppie |
| --- | ---: |
| `conflicting_match` | 2 |
| `exact_source_match` | 8 |

## Gold

- Record di gold: 161
- Prediction con un record di gold corrispondente: 10 / 10
- **Valutabili: 0**
- Provvisori: 161
- Congelati: 0
- Coppie con due revisioni reali: 0
- Accordo fra annotatori: `not_evaluable`

## Metriche

| Metrica | Valore |
| --- | --- |
| linking precision | `not_evaluable` |
| linking recall | `not_evaluable` |
| linking F1 | `not_evaluable` |
| exact-match precision | `not_evaluable` |
| partial-link accuracy | `not_evaluable` |
| invalid-link rejection | `not_evaluable` |
| ambiguity detection | `not_evaluable` |
| conflict detection | `not_evaluable` |
| dimension-level precision | `not_evaluable` |
| dimension-level recall | `not_evaluable` |

## Perche' i valori sono `not_evaluable`

Non perche' il linker abbia fallito, ma perche' non esiste ancora un
riferimento contro cui misurarlo. Il gold richiede due annotazioni
indipendenti su ogni coppia, e questa fase ha costruito il workflow senza
poterlo eseguire.

La causa e' verificata e non supposta: tutte le 10 prediction del linker hanno un record di gold corrispondente. Le chiavi di join
combaciano, quindi lo zero viene dalle annotazioni mancanti e non da una
valutazione rotta — due situazioni che produrrebbero lo stesso numero.

La strada corta sarebbe copiare le prediction del linker nel gold. Darebbe
precision 1.000 e non significherebbe nulla: misurerebbe la coerenza del
linker con se stesso. `candidate_from_link` esiste proprio per rendere quella
scorciatoia impraticabile — conserva la prediction in una nota, dove e'
leggibile ma non puo' diventare il riferimento.

## Priorita' fra precision e recall

La precisione conta di piu'. Uno statement non qualificato lascia il retriever
al comportamento V2, che e' il punto di partenza noto. Uno statement
qualificato con setting o linea sbagliati produce un filtro che scarta
l'evidenza giusta o ne ammette una inapplicabile, e nessuna metrica a valle
distingue quel caso da una qualificazione corretta.

