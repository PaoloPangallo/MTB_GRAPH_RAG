# Protocollo del pilot a due stadi (Gemma)

La soglia precedente ("almeno 2/3 ACCEPTED") è stata sostituita da criteri
separati per tipo di bundle, perché lo smoke test include intenzionalmente
un caso CONTRADICTED per cui rigetto o astensione sono l'esito corretto, non
un fallimento.

## Criteri per tipo di caso

**A. DIRECT** — successo se: transport valido, proposta grounded, tutti i
campi centrali accettati, status `DIRECT` preservato.

**B. PARTIAL** — successo se: i campi effettivamente supportati vengono
accettati, i campi graph-only o incompatibili vengono scartati, nessuna
promozione impropria a `DIRECT`. Sono esiti validi: `REJECTED_DIRECTION`,
`PARTIAL`, `AMBIGUOUS`, `ACCEPTED_WITH_DROPPED_FIELDS`, a seconda del
contenuto.

**C. CONTRADICTED** — successo se: non viene prodotto supporto positivo, la
contraddizione viene rilevata oppure il modello si astiene oppure la
proposta viene rigettata per direzione, e il documento non viene adattato
alla candidate.

Il numero grezzo di `ACCEPTED` non è più usato come soglia generale.

## Stadio 1

Una singola run (`run_index=0`) per tutti i 25 EvidenceBundle congelati. Tre
bundle riusano il risultato reale già ottenuto dallo smoke test (nessuna
richiamata); gli altri 22 ricevono al massimo una nuova chiamata reale
ciascuno. Configurazione, transport, prompt, schema, adapter e validatore
restano quelli congelati per Gemma (`gemma4:cloud`, transport
`llm-claim-proposal-transport/1.2`, prompt `llm-claim-extractor-prompt/1.3`,
validator `deterministic-llm-proposal-validator/1.1`).

## Stadio 2

Le altre due run per bundle (fino a 50 chiamate aggiuntive). Autorizzabile
solo se lo Stadio 1 soddisfa tutti i criteri della sezione 8 del protocollo
(vedi `gemma_stage2_decision.md`). Non è richiesto che la maggioranza delle
proposte sia `ACCEPTED`: rigetti e astensioni corretti sono esiti validi.

## Hard stop

Il run si interrompe immediatamente, senza ulteriori chiamate, se: viene
accettata una quote inesistente; viene accettata una SourceUnit inventata;
un campo graph-only viene promosso; un caso CONTRADICTED diventa positivo;
il validatore viene aggirato o modificato; il prompt o il transport
cambiano durante il pilot; il file degli EvidenceBundle o delle baseline
cambia. Ognuna di queste condizioni è verificata automaticamente per ogni
riga (`stage1_pilot.detect_hard_stops`), non solo a fine run.
