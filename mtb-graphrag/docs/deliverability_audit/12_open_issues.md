# 12 — Problemi aperti

Dati completi: `evaluation/deliverability/issues.csv` (21 righe, 15 colonne).

```
P0 = 3     P1 = 4     P2 = 8     P3 = 6        totale 21
blocks_freeze = TRUE  →  6
```

| Categoria | n |
|---|---:|
| SOFTWARE_BUG | 4 |
| ARCHITECTURAL_INCONSISTENCY | 4 |
| EXPERIMENTAL_GAP | 4 |
| REPRODUCIBILITY_GAP | 3 |
| SCIENTIFIC_LIMITATION | 3 |
| DOCUMENTATION_GAP | 2 |
| FUTURE_FEATURE | 1 |

---

## P0 — invalidano una claim o impediscono la consegna

### ISS-001 · Il gate non può fermare una run — `SOFTWARE_BUG`

`orchestrator.py:417` passa `eligibility_status` come `stopped_at`;
`contracts.py:279` lo rifiuta perché **8 dei 9 `ELIGIBILITY_STATES` non sono in
`STOP_REASONS`**. Ogni decisione non eleggibile solleva
`ValueError: stop reason sconosciuta`.

- **Runtime:** run `FAILED`, `reason_codes = ['LIVE_STAGE_FAILED']`,
  `stages_executed = []`, `llm_calls = 0`. Confermato in LIVE su 5 categorie via
  API reale e in 10 casi su 14 con parser stub.
- **L'invariante di sicurezza regge:** `retrieval_called = 0` sempre.
- **Scientifico:** la claim RQ4 non è dimostrabile attraverso il runtime. Le
  metriche pubblicate misurano `casecontext.pipeline.run`, che bypassa
  l'orchestratore.
- **Fix minimo:** aggiungere gli 8 stati a `STOP_REASONS`, decidere quali sono
  `CORRECT_STOP_REASONS`, aggiungere un test del ramo non eleggibile attraverso
  `orchestrator.run_case`.

### ISS-002 · La polarità negativa diventa supporto positivo — `SOFTWARE_BUG` · ⛔ HARD STOP §28

`gates.py:34` — `"support" in "does not support"` è `True`.

```python
direction_consistency("Does Not Support", "RESPONSE")   -> "CONSISTENT"
direction_consistency("Reduced Sensitivity", "RESPONSE")-> "CONSISTENT"
direction_consistency("Adverse Response", "RESPONSE")   -> "CONSISTENT"
```

Esito: `status = DIRECT`, `support_mask.direction = SUPPORTED`,
`gate_bucket = PRIMARY_BUCKET`, **zero warning**, per una candidate la cui fonte
afferma esplicitamente di non supportarla.

**752 candidate su 46 864** nel repository che il runtime usa; **1 raggiungibile
end-to-end**. Il runtime inoltre non legge mai
`source_properties.evidence.evidence_direction`: l'informazione c'è, è ignorata.

- **Scientifico:** condizione di hard stop del §28 soddisfatta. Invalida la
  claim di *representation fidelity* sul percorso eseguito.
- **Fix minimo:** verificare la negazione **prima** dell'affermazione su valori
  normalizzati espliciti; leggere `evidence_direction` come asse separato;
  aggiungere un test su tutte le 46 864 candidate v2 (l'equivalente per v3
  esiste già).

### ISS-003 · Una quote fabbricata entra nel dossier presentato — `ARCHITECTURAL_INCONSISTENCY`

`orchestrator.py:616-617` appende `call["enrichment"]` ad `author_context`
**incondizionatamente** rispetto all'esito di validazione.
`DossierView.tsx:89` filtra per **presenza** della quote, chiama il risultato
`accepted`, e lo rende in corsivo sotto «*Ciò che gli autori dei paper hanno
scritto*».

- **Lo stato canonico è protetto:** `status = AMBIGUOUS`,
  `direction = NO_DOCUMENT_SIGNAL`, `bucket = WARNING_BUCKET`.
- **Il dossier presentato no:** una quote `REJECTED_QUOTE_NOT_FOUND` viene
  mostrata al clinico come citazione d'autore.
- **Scientifico:** risposta **sì** alla domanda §34 «una quote inventata può
  entrare nel dossier canonico».
- **Fix minimo:** allegare `validation_outcome` a ogni voce di `author_context` e
  far filtrare la UI su quello. Preferibile al filtro a monte perché conserva
  l'auditabilità.

---

## P1 — da correggere prima del freeze

| ID | Titolo | Categoria |
|---|---|---|
| **ISS-004** | `npm run build` fallisce — 6 errori TS2769 in `EligibilityStage.tsx` | SOFTWARE_BUG |
| **ISS-005** | RQ4 misurata bypassando l'orchestratore | EXPERIMENTAL_GAP |
| **ISS-006** | Dipendenze non pinnate, `pytest` non dichiarato, nessun lockfile | REPRODUCIBILITY_GAP |
| **ISS-007** | Denominatore 46 864 senza il denominatore end-to-end (16) | SCIENTIFIC_LIMITATION |

ISS-004 è ironico e istruttivo: il file che non compila è **l'interfaccia che
espone l'eligibility gate**, introdotta da `af099fd`. Non è stato visto perché
`vitest` non fa typecheck e nessuna CI esegue `tsc`.

ISS-007 non blocca il freeze: è una correzione di presentazione, non di codice.

---

## P2 — limiti reali, documentabili senza invalidare il contributo

| ID | Titolo |
|---|---|
| ISS-008 | `kg_retrieval_v3.py`: 147 righe con **zero riferimenti** in tutto il repository |
| ISS-009 | Un mismatch letterale viene riportato come `OUT_OF_SCOPE` |
| ISS-010 | Il rilevatore di istruzioni avversariali è una lista chiusa di 22 pattern |
| ISS-011 | Il campione manuale v3 a 70 record non è annotato → coerenza interna, non riferimento esterno |
| ISS-012 | Il parser LLM fallisce il trasporto nel 28 % delle run LIVE |
| ISS-013 | Il docstring dell'orchestratore descrive un test di parità inesistente |
| ISS-014 | 13 artifact sperimentali untracked |
| ISS-015 | Tre assi di versionamento condividono la stringa «v3» |

---

## P3 — engineering / future work

| ID | Titolo |
|---|---|
| ISS-016 | `describe_availability()` riporta `FROZEN_REPLAY` dove il runtime in realtà fallisce |
| ISS-017 | `run_rq1` e `run_gca_v3_audit` non onorano un `OUT` sostituito |
| ISS-018 | 7 artifact committati contengono il percorso assoluto dell'autore |
| ISS-019 | Il farmaco può stare nell'unità invece che nella quote |
| ISS-020 | Narrator e Narrative Verifier non implementati |
| ISS-021 | `endpoint_configuration` in RQ4 è *stale* dopo la correzione del default |

---

## Ordine di correzione consigliato

```
1. ISS-002   gates.direction_consistency        ~15 righe + 1 test
2. ISS-001   contracts.STOP_REASONS             ~8 righe + 1 test
3. ISS-003   author_context + DossierView       ~10 righe backend + ~5 frontend
4. ISS-004   EligibilityStage.tsx               6 sostituzioni meccaniche
5. ISS-005   rerun RQ4 attraverso l'orchestratore  (dipende da 2)
6. ISS-006   requirements + pytest.ini          configurazione
7. ISS-007   affiancare il denominatore end-to-end nelle tabelle della tesi
```

I primi quattro sono correzioni chirurgiche in **quattro file**. Nessuno richiede
una modifica architetturale, un cambio di contratto o una rigenerazione di
dataset.
