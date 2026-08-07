# 10 — Benchmark di narrative fidelity

`evaluation/run_dossier_narrator_benchmark.py` · artifact in
`evaluation/dossier_narrator/`.

**Non è una nuova Research Question.** Il Narrator è *architectural completion /
safety validation*: il benchmark misura se la narrativa resta fedele a un
dossier già deciso, e se il verifier intercetta le infedeltà. Non misura
correttezza clinica.

## Composizione — 25 dossier

| Strato | n | Caratteristica |
|---|:-:|---|
| `DIRECT` | 5 | supporto stabilito, citazione validata |
| `AMBIGUOUS` | 5 | `NO_DOCUMENT_SIGNAL`, nessuna citazione |
| `DOES_NOT_SUPPORT` | 5 | polarità negativa della fonte |
| `NO_VALIDATED_QUOTE` | 5 | astensione documentale |
| `MULTI_CANDIDATE` | 5 | due candidate con status diversi |

I dossier sono sintetici ma **conformi al contratto reale** verificato nel
documento 00. Sono sintetici per necessità: il campione REPLAY reale non produce
alcuna candidate `DIRECT` (produce `PARTIAL`, `AMBIGUOUS`, `DISCOVERED`), e uno
strato vuoto non sarebbe un benchmark.

## Risultato LIVE

Narrative prodotte da **gemma4:cloud** in una run reale il 2026-08-07, congelate
in `benchmarks/mtb_evidence/dossier_narrator/narrative_runs.jsonl`.

```
narration_attempts             25
narration_transport_success    25   (100 %)
verifier_pass                  25
verifier_fail                   0
structured_fallback_used        0
```

## La prima esecuzione aveva 3 FAIL, ed è il risultato più utile

Tutte e tre nello strato `MULTI_CANDIDATE`, tutte con
`NARRATIVE_CRITICAL_LIMITATION_OMITTED / NO_VALIDATED_QUOTE_NOT_STATED`.

Il modello aveva scritto:

> «non è stato trovato un **segnale** documentale esplicito (NO_DOCUMENT_SIGNAL)
> per supportare la direzione della relazione»

che dichiara correttamente l'assenza di citazione validata. Il lexicon conosceva
solo «**supporto** documentale» e la contava come omissione.

**Era un falso positivo del verifier, non un'infedeltà del modello.** Un
verifier troppo stretto non è più sicuro: spinge il sistema verso il fallback
permanente, cioè verso il non mostrare mai nulla, che è un modo diverso di
fallire.

Correzione: aggiunte le varianti `segnale` / `riscontro` / `evidenza`
documentale, mantenendo la richiesta di una negazione esplicita accanto a un
sostantivo documentale. Aggiunto un test di regressione con cinque formulazioni
equivalenti, **più la controprova** che una narrativa che omette davvero
continua a fallire.

Riverificate le **stesse** narrative dopo la correzione: 25/25 PASS. Non è stato
richiesto nulla di nuovo al modello.

## Modalità

| | Chiamate al modello | Uso |
|---|---|---|
| `--live` | sì, 25 | risultato riportato sopra |
| default | no, simulatore locale **dichiarato** | esercita il verifier senza rete né costo |

Ogni riga degli artifact porta `mode`: `LIVE` o `SIMULATED`. Il simulatore non è
un modello e non va confuso con uno — è etichettato in ogni riga prodotta.

## Metriche registrate

`narration_attempts`, `narration_transport_success`, `verifier_pass`,
`verifier_fail`, `unauthorized_entity_detected`, `status_escalation_detected`,
`polarity_inversion_detected`, `unauthorized_recommendation_detected`,
`unauthorized_quote_detected`, `critical_omission_detected`,
`structured_fallback_used`, `latency_ms_total`, `input_tokens`, `output_tokens`.

## Campione per revisione manuale

`evaluation/gold/narrative_manual_review.csv` — 25 righe con `run_id`,
`case_id`, `candidate_ids`, `canonical_statuses`, `narrative_verifier_status`,
`narrative_text`, `automatic_reason_codes`.

Le sette colonne del revisore sono **vuote**, come richiesto. Finché restano
vuote, la fedeltà è verificata automaticamente e non da un giudizio esperto: è
un limite dichiarato in `12_limitations.md`.
