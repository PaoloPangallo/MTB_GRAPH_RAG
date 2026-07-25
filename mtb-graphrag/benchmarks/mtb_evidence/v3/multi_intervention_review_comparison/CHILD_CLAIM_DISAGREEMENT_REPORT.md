# Child claim: da 11 a 8 e da 9 a 3

`comparison_type = first_review_vs_blinded_non_independent_replicate`

Le due revisioni leggono la stessa fonte quasi sempre allo stesso modo, e propongono
numeri di figli molto diversi. La ragione non e' documentale.

## I due percorsi

**Prima revisione: 11 risultati separati, 8 figli.** Undici associazioni classificate
`directly_tested_with_separate_result`; tre appartengono a `evidence:3811`, il cui gruppo
e' chiuso come `insufficient_for_atomicity_decision`, quindi non generano nulla. Restano 8.

**Replica: 9 risultati separati, 3 figli.** Nove associazioni con risultato separato — le
stesse undici meno le tre di `evidence:3811`, piu' erlotinib in `evidence:11240`, letto sul
braccio placebo + erlotinib. Di queste nove, sei riguardano l'intervento gia' portato dal
parent e ne raffinano il locator invece di creare un claim. Restano 3.

## Dove nasce la differenza

I figli proposti da entrambe sono 3. Quelli proposti solo dalla prima revisione
sono 5, e sono **tutti** figli sull'intervento del parent. Quelli proposti
solo dalla replica sono 0.

Non e' un disaccordo sulla lettura della fonte: su quelle cinque associazioni le due
revisioni concordano su classificazione, direzione, polarita' e risultato. Divergono su
cosa sia il parent. Per la prima revisione il parent e' un contenitore di evidenza e non
un claim terapeutico — e' quanto propone la sua raccomandazione architetturale — quindi
ogni risultato separato ha bisogno del suo figlio, incluso quello del parent. Per la
replica il parent e' gia' il claim di quell'intervento, e duplicarlo creerebbe due
rappresentazioni della stessa affermazione.

Le due posizioni sono internamente coerenti e incompatibili fra loro. La conseguenza e' che
il numero di figli non e' decidibile guardando le fonti: dipende da una scelta di modello
che va fatta prima, ed e' la prima domanda dei packet di adjudication.

## Elenco

### Proposti da entrambe

- `evidence:229` — gefitinib
- `evidence:296` — ponatinib
- `evidence:841` — crizotinib

### Proposti solo dalla prima revisione

- `evidence:1483` — alectinib hydrochloride (`parent_intervention_already_represents_result`)
- `evidence:1484` — alectinib hydrochloride (`parent_intervention_already_represents_result`)
- `evidence:229` — erlotinib (`parent_intervention_already_represents_result`)
- `evidence:296` — pazopanib hydrochloride (`parent_intervention_already_represents_result`)
- `evidence:841` — ceritinib (`parent_intervention_already_represents_result`)

### Proposti solo dalla replica

- nessuno

### Non proponibili da nessuna delle due: 20

**8 sono l'intervento del parent**, gia' rappresentato dal claim
esistente in entrambe le letture. Il motivo documentale che comunque ne impedirebbe
l'autonomia resta registrato come secondario:

- `aggregate_result`: 1
- `insufficient_locator`: 1
- `nessun blocco documentale`: 1
- `pending_alias_blocks_child`: 2
- `regimen_component`: 2
- `unsupported_intervention`: 1

**12 sono interventi aggiuntivi** bloccati dalla lettura della fonte:

- `aggregate_result`: 3
- `insufficient_locator`: 2
- `pending_alias_blocks_child`: 1
- `regimen_component`: 2
- `unsupported_intervention`: 4

## Nota di consistenza

La prima revisione conserva i 13 parent e aggiunge 8 figli. Per cinque interventi questo
significa un parent e un figlio con lo stesso intervento, direzione, polarita' e
biomarcatore. La contraddizione si scioglie solo se il parent smette di essere
interrogabile come claim nello stesso passaggio in cui il figlio nasce. E' la proposta
GL-02.
