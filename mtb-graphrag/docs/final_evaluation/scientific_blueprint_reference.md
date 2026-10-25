# Scientific blueprint — riferimento

    protocol_version : mtb-graphrag-final-evaluation/1.1
    runtime_commit   : 3d2251f82a586535f79f3d0b3725c16330c365ba
    previous_runtime : f52bbf5920c14324953be849e666bc84571957e9
    created          : 2026-08-09 (fase 1.1-review-1)
    amended          : 2026-08-10 (riallineamento architetturale pre-freeze)

## Delta rispetto al documento di riferimento del 9 agosto

Il report di posizionamento citato qui sotto è un **documento storico** e non
viene riscritto. Descriveva un'architettura con due modalità operative, `LIVE`
e `REPLAY`, e in più punti presentava la loro distinzione come contributo.

L'implementazione finale usa **un solo runtime canonico operativo**. Il delta,
registrato qui e non applicato silenziosamente al documento originale:

| Nel blueprint del 9 agosto | Nell'implementazione finale |
|---|---|
| due modalità operative, LIVE e REPLAY | un solo runtime canonico; nessuna modalità selezionabile |
| REPLAY come modalità riproducibile | riproducibilità da snapshot persistiti, artefatti immutabili e strumenti di regressione riservati alla ricerca |
| LIVE come modalità che generalizza | acquisizione documentale del runtime canonico oltre gli artefatti congelati di sviluppo |
| «LIVE abort» | `PIPELINE_ABORT` |
| distinzione LIVE/REPLAY come confine di autorità in RQ3 | confini misurati: dipendenza da bundle congelati = 0, dipendenza dagli adattatori di ricerca = 0, fallback storico implicito = 0 |

Invariati rispetto al blueprint: RQ1 nella sostanza; la catena documentale di
RQ2 e tutte le sue metriche; le API autorizzate; la separazione di autorità del
modello; RQ4 come esecuzione selettiva e fallimento controllato.

## Documento di riferimento

    TITLE : MTB GraphRAG — Report aggiornato di posizionamento scientifico,
            domande di ricerca e giustificazione dell'architettura
    DATE  : 2026-08-09
    ROLE  : Scientific blueprint for RQ1–RQ4, thesis claims and
            experiment/result mapping

## Autorità

Il blueprint scientifico definisce **cosa** la tesi sostiene: formulazione delle
research question, claim sostenibili e non sostenibili, mappatura fra esperimenti
e capitolo Risultati, invarianti architetturali.

Il **final evaluation protocol resta autoritativo** per: dataset, denominatori,
classificazione del leakage, definizione delle metriche, piano statistico,
criteri HARD, split e artifact path.

In caso di conflitto prevale il protocollo. Una metrica non si cambia perché nel
report starebbe meglio.

## Sezioni recepite

| § | Sezione | Recepita in |
|---|---|---|
| 10 | Research Questions | `final_evaluation_protocol.md` §3 |
| 12 | RQ → esperimenti | `result_schemas.json`, `final_evaluation_protocol.md` §8 |
| 15 | Supported claims | `claim_evidence_matrix.md`, tabella «Claim sostenibili» |
| 16 | Unsupported claims | `claim_evidence_matrix.md`, tabella «Claim che NON possono essere sostenute» |
| 17 | Experimental plan | `final_evaluation_protocol.md` §4, §8 |
| 18 | Architectural invariants | `success_criteria.json`, criteri HARD H-A … H-N |
| 21 | Limitations | `limitations.md`, L1 … L21 |

## Stato della sorgente

    source_file      : non presente nel repository
    source_hash      : unavailable_at_protocol_build
    hash_algorithm   : sha256 (non calcolabile)

**Motivo.** Il documento non è versionato nel repository e non è stato trovato
sul filesystem locale durante le fasi 1.0 e 1.1 (ricerche per titolo, per stringa
«posizionamento scientifico» e per data di modifica). L'unico file con titolo
affine, `docs/V3_POSITIONING.md`, è del 22 luglio 2026 e ha un contenuto diverso:
è la specifica di posizionamento della V3, non il report del 9 agosto.

Il contenuto qui recepito proviene dalla **restituzione strutturata fornita
dall'autore della tesi** nelle richieste di fase 1.1 e 1.1-review-1, non dalla
lettura diretta del documento.

**Nessun hash è stato inventato.** Quando il file sarà versionato, calcolare lo
SHA-256, sostituire `unavailable_at_protocol_build` e ri-sigillare il protocollo.

Questa condizione è registrata anche come limitazione **L21** in
`limitations.md`.

## Conseguenza operativa

Finché la sorgente non è versionata, il protocollo non può dimostrare di essere
allineato a *quel* documento: può solo dimostrare di essere allineato a ciò che
è stato riportato. È una limitazione di tracciabilità, non di validità
sperimentale: nessun risultato dipende dal blueprint, che governa la scrittura e
non la misurazione.
