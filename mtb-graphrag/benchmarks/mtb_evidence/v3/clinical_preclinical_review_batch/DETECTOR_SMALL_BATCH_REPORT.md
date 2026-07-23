# Il rilevatore source-level su tre casi

## In una riga

Su tre positivi selezionati dal rilevatore stesso, **uno e' un falso positivo** — e la causa non e' una soglia da tarare.

## I tre casi

| Fonte | Verdetto | Revisione | Esito | Segnali |
| --- | --- | --- | --- | ---: |
| `PU-PMID-22235099-cohort-1` | split_required | audit_split_confirmed_with_more_units | **confirmed_positive** | 185 |
| `PU-PMID-23344087-cohort-1` | split_required | audit_split_partially_supported | **partially_confirmed** | 11 |
| `PU-PMID-31358542-cohort-1` | split_required | audit_split_not_supported | **rejected_positive** | 110 |

## Il reperto

Due fonti su tre hanno ricevuto il verdetto `split_required` sulla base di
**una sola** occorrenza di `preclinical.in_vitro`.

In PMID 23344087 quell'occorrenza sta nei metodi dell'abstract e descrive un
esperimento della fonte. In PMID 31358542 sta in una frase che cita i modelli
di altri. Stesso segnale, stesso conteggio, verita' opposta.

Il punteggio non aiuta a distinguerli: 14 contro 125, e il caso col punteggio
piu' alto e' quello sbagliato. Il problema non e' la soglia — e' che il
rilevatore non ha nozione di **provenienza dentro il documento**, e non
distingue cio' che la fonte fa da cio' che la fonte cita.

## Che cosa nessun segnale poteva vedere

In PMID 22235099 il verdetto era giusto e il numero di unita' no: i sistemi
preclinici sono quattro, e nessun segnale conta i modelli distinti. Un
rilevatore che dica «c'e' del preclinico» non dice **quanto** preclinico, e la
differenza fra una unita' e quattro e' quella fra un profilo utilizzabile e un
profilo che fonde quattro esperimenti diversi.

## Metriche

- conferme piene: **1**
- conferme parziali: **1**
- positivi respinti: **1**
- evidenza insufficiente: 0
- copertura delle componenti trovate: **1.000**
- componenti segnalate ma inesistenti: **1**
- fonti in cui il numero di unita' era corretto: **0.000**

Non sono precision, recall, sensitivity, specificity o accuracy, e non vanno
chiamate cosi'. Il batch contiene solo positivi scelti dal rilevatore: non
dice nulla su quante fonti abbia mancato in silenzio.

## Stato

```
detector_promotion_ready = false
```

Il rilevatore resta fuori produzione. Tre casi, uno sbagliato, e il modo in cui
sbaglia e' strutturale: promuoverlo adesso metterebbe in produzione un
componente che non sa distinguere una citazione da un esperimento.

La direzione della correzione e' pero' chiara, ed e' piu' utile del verdetto:
servono segnali che leggano il **contesto** dell'occorrenza — vicinanza a un
marcatore di citazione, sezione del documento, presenza di metodi propri — e
un segnale che conti i modelli distinti invece di limitarsi a rilevarne uno.

