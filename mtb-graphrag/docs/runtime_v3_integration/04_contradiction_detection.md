# 04 — Rilevamento delle contraddizioni

**Nessun LLM giudica.** Il rilevatore lavora su span testuali e stato di
asserzione, entrambi deterministici.

## Il problema

Nel benchmark RQ4 tutte e cinque le contraddizioni venivano estratte senza
segnalazione e instradate al retrieval: un testo che dice insieme
`KRAS wild-type` e `KRAS G12D mutation` produceva una candidate che proseguiva.

## Forme rilevate

| Tipo | Descrizione |
|---|---|
| `ASSERTED_AND_NEGATED_ENTITY` | stessa entita' asserita e negata |
| `SPECIFIC_ALTERATION_WITH_EXPLICIT_NEGATION` | stato genico mutuamente esclusivo, o test negativo con alterazione specifica |
| `MUTUALLY_EXCLUSIVE_DISEASE` | due diagnosi primarie incompatibili |
| `TREATMENT_HISTORY_CONFLICT` | «mai ricevuto terapia» con terapia somministrata |
| `INTENT_CONFLICT` | l'istruzione nega cio' che la domanda chiede |

## Oggetto

```json
{
  "contradiction_id": "CTR-...", "type": "...", "entity_type": "...",
  "normalized_entity": "...", "positive_spans": [], "negative_spans": [],
  "reason_code": "...", "severity": "BLOCKING | WARNING"
}
```

Una contraddizione `BLOCKING` produce `CONTRADICTORY_CASE_CONTEXT` e il
retrieval e' `SKIPPED`.

## Conservativo per costruzione

Due falsi positivi trovati e corretti durante lo sviluppo:

* la negazione attraversava i confini di frase e rendeva negata la malattia in
  `Lung adenocarcinoma. EGFR testing was negative.`;
* `wild-type` contato anche come alterazione positiva rendeva contraddittorio
  ogni `KRAS wild-type`.

Entrambi mostrano che una regola troppo larga blocca casi validi, che e' il danno
peggiore.

## Risultato

5 su 5 contraddizioni del benchmark rilevate; `contradictory_case_retrieval = 0`.
