# Istruzioni per la seconda revisione

## Che cosa ti viene chiesto

Le quattro annotazioni del pilota MTB-Evidence sono state prodotte una sola volta e
non sono ancora ground truth. Ti viene chiesto un giudizio **indipendente** su claim,
qualificatori e applicabilita'.

Indipendente vuol dire che questo pacchetto non contiene, deliberatamente, alcun
suggerimento su quale sia la risposta giusta: nessuna decisione gia' presa, nessun
output di sistemi automatici, nessun punteggio. Se ti sembra che manchi un'indicazione
su come decidere, e' voluto.

## Che cosa contiene il pacchetto

| File | Contenuto |
| --- | --- |
| `review_cases.csv` | domanda, contesto clinico e differenze osservate fra annotazione e snapshot |
| `review_claims.csv` | le claim provvisorie, con i valori corrispondenti trovati nel grafo |
| `review_sources.csv` | le fonti citate e se sono presenti nello snapshot |

Le colonne `graph_*` riportano i valori **osservati nel grafo**, non un giudizio.
`dimensions_with_differing_values` elenca le dimensioni su cui i due lati riportano
valori diversi, senza dire quale sia corretto.

## Come compilare

Per ogni riga compila `reviewer_decision` con uno di:

- `accept` - la claim e' corretta come scritta, qualificatori compresi;
- `accept_with_changes` - il nucleo regge ma qualcosa va corretto; scrivi cosa in `reviewer_notes`;
- `reject` - la claim non e' sostenibile;
- `insufficient_information` - non e' decidibile con quanto fornito; scrivi cosa servirebbe.

`reviewer_notes` e' libero ed e' la parte piu' utile: annota il motivo, non solo l'esito.

## Punti su cui prestare attenzione

- **Popolazione e linea.** Una claim vera in una popolazione gia' trattata puo' essere
  falsa in prima linea. Verifica che i qualificatori obbligatori siano tutti presenti.
- **Specificita' della malattia.** Un sottotipo e la sua categoria generale non sono
  intercambiabili.
- **Mutazione singola e composta.** Hanno implicazioni terapeutiche diverse e non vanno
  trattate insieme.
- **Assenza dallo snapshot.** `present_in_snapshot = no` significa che quella fonte non e'
  recuperabile da questo grafo. Non significa che la pubblicazione non esista, ne' che la
  claim sia falsa: e' un'informazione sulla copertura, e sta a te dire se cambia il giudizio.

## Dopo la compilazione

Restituisci i tre CSV compilati. I disaccordi con la prima annotazione verranno
riconciliati in una discussione esplicita, non risolti a maggioranza.
