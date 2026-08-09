# Scientific blueprint — riferimento

    protocol_version : mtb-graphrag-final-evaluation/1.1
    runtime_commit   : f52bbf5920c14324953be849e666bc84571957e9
    created          : 2026-08-09 (fase 1.1-review-1)

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
