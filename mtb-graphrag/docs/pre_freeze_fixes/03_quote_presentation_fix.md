# 03 — ISS-003 · Presentazione delle quote

**P0. CHIUSO.**
Dati: `evaluation/pre_freeze/quote_presentation_results.json`.

## Il problema, nella sua forma esatta

Il dossier **canonico** era già corretto e non è mai stato in discussione: un
enrichment rigettato non ha mai toccato `status`, `support_mask`, `gate_bucket`
o i gate. Verificato prima e dopo: `AMBIGUOUS / NO_DOCUMENT_SIGNAL /
WARNING_BUCKET`.

Il difetto era nel dossier **presentato**, e nasceva da due righe:

```python
# orchestrator.py:616-617 — appende senza guardare l'esito
if call["enrichment"] is not None:
    enrichment_entries.append(call["enrichment"])
```

```js
// DossierView.tsx:89 — deduce l'accettazione dall'esistenza di una stringa
const accepted = entry.author_context.filter((e) => e.author_claim_quote);
```

Le voci di `author_context` **non portavano il proprio esito**, quindi la UI non
aveva modo di filtrarle correttamente. Una quote fabbricata e rigettata con
`REJECTED_QUOTE_NOT_FOUND` finiva nel gruppo reso in corsivo sotto «*Ciò che gli
autori dei paper hanno scritto*».

## §10 — Il contratto dell'enrichment

Quattro stati chiusi e mutuamente esclusivi, in
`backend/research_pipeline/dossier/builder.py`:

```python
VALIDATED_QUOTE                # accettata dal validatore deterministico
REJECTED_QUOTE                 # proposta e scartata
ABSTAINED                      # il modello si è astenuto
PROPOSED_QUOTE_NOT_VALIDATED   # nessun esito disponibile

PRESENTABLE_AS_AUTHOR_CLAIM = {VALIDATED_QUOTE}
```

`annotate_enrichment()` allega a ogni voce `validation_outcome`,
`validation_reason_codes`, `presentation_state` e `accepted_for_gates`. È una
**copia**: l'originale non viene mutato (test dedicato).

Due proprietà deliberate:

- **un esito assente non è un'accettazione** → `PROPOSED_QUOTE_NOT_VALIDATED`,
  non presentabile. È il default conservativo, e vale anche per i dossier
  prodotti da run precedenti al fix;
- **un esito sconosciuto è un rigetto**, non un'accettazione: un vocabolario
  futuro non può aprire un varco.

Riconosce entrambi i vocabolari, v1 e v2.

## La UI non deduce più nulla

```js
function isValidatedAuthorClaim(e: Enrichment): boolean {
  return e.presentation_state === 'VALIDATED_QUOTE';
}
```

Le proposte rigettate **non vengono rimosse** — servono all'audit — ma finiscono
in una sezione propria:

> **PROPOSTE NON VALIDATE — SOLO AUDIT**
> Il modello le ha proposte, il validatore deterministico le ha scartate.
> Non sono citazioni degli autori e non contribuiscono allo status.

rese barrate, con l'esito e i reason code accanto.

### §12 — Cosa la UI può e non può fare

| | |
|---|:-:|
| semplificare, raggruppare, rendere leggibile | ✅ |
| promuovere evidenza | ❌ |
| cambiare validation status | ❌ |
| trasformare rejected in accepted | ❌ |
| dedurre supporto dalla presenza di una quote | ❌ **rimosso** |

La fonte dell'accettazione è ora, e soltanto, l'esito del validatore
deterministico calcolato nel backend.

## §11 — I nove scenari

| | Scenario | Esito validatore | Presentata prima | Presentata dopo |
|---|---|---|:-:|:-:|
| A | quote valida | `ENRICHMENT_V2_ACCEPTED` | ✅ | ✅ |
| B | quote inventata | `REJECTED_QUOTE_NOT_FOUND` | **✅** | ❌ |
| C | quote alterata di una parola | `REJECTED_QUOTE_NOT_FOUND` | **✅** | ❌ |
| D | quote da altra SourceUnit | `REJECTED_QUOTE_NOT_FOUND` | **✅** | ❌ |
| E | quote da altro documento | `REJECTED_SOURCE_UNIT` | **✅** | ❌ |
| F | SourceUnit inventata | `REJECTED_SOURCE_UNIT` | **✅** | ❌ |
| G | ABSTAIN | `ENRICHMENT_V2_ABSTAINED` | ❌ | ❌ |
| H | enrichment senza quote | `REJECTED_QUOTE_NOT_FOUND` | ❌ | ❌ |
| I | validator failure | nessun esito | — | ❌ |

```
invented_quotes_presented_as_accepted     5  ->  0
rejected_quotes_presented_as_accepted     5  ->  0
invented_quotes_canonically_accepted      0  ->  0   (mai violato)
invented_sourceunits_accepted             0  ->  0   (mai violato)
wrong_document_quotes_accepted            0  ->  0   (mai violato)
```

## Test

- `backend/research_pipeline/tests/test_quote_presentation.py` — **17 test, 4
  subtest**, inclusi i nove scenari, la conservazione delle voci rigettate per
  audit, l'immutabilità di `annotate_enrichment` e la protezione dello stato
  canonico;
- `EndToEndThroughOrchestrator` esegue una run **REPLAY reale** e verifica che
  ogni voce di `author_context` nel dossier prodotto porti `presentation_state`,
  e che nessuna voce presentabile sia esclusa dai gate;
- `frontend/src/research/DossierView.test.tsx` — **5 test nuovi**: la quote
  rigettata non compare fra le citazioni, appare invece nella sezione di audit
  con il proprio motivo, una quote priva di esito non è presentata, e lo status
  canonico positivo non promuove comunque la quote.

La fixture frontend è stata aggiornata per riflettere il contratto reale del
backend, che ora emette sempre `presentation_state`.

## §9 — Non è stato necessario fidarsi dell'LLM

Il fix non chiede nulla al modello e non cambia il prompt. Sposta soltanto un
dato che il backend già possedeva — l'esito del validatore — accanto alla voce a
cui si riferisce.
