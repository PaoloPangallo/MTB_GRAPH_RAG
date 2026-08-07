# 02 — Riverifica indipendente dei blocker

Dati: `evaluation/final_deliverability/blocker_reverification.json` e i tre file
`*_recheck.json`.

**Metodo.** Le sonde di questo audit sono state scritte **da zero**, non riusano
quelle del fix sprint, e usano casi **più duri** di quelli con cui i difetti
sono stati corretti. Il report del fix sprint non è stato assunto come vero in
nessun punto.

---

## ISS-002 · Source polarity — **CHIUSO**

### Casi limite provati

| Categoria | Valori |
|---|---|
| negativi | `Does Not Support`, `does not support`, `DOES NOT SUPPORT`, `  Does   Not   Support  `, `Does-Not-Support`, `does_not_support` |
| neutri | `Neutral`, `No Difference`, `neutral or no difference` |
| contraddizione | `Contradicts`, `CONTRADICTS ASSERTION` |
| ignoti | `None`, `""`, `"   "`, `Unmapped`, `N/A`, `0`, `[]`, `{}`, `3.14` |
| avversi | `Reduced Sensitivity`, `Adverse Response`, `REDUCED SENSITIVITY` |

Ogni valore provato in **entrambe** le posizioni — nel campo `direction` e in
`source_properties.evidence.evidence_direction` — e con `evidence_kind` sia
`RESPONSE` sia `BENEFIT`.

### Scansione dell'intero repository

```
candidate totali                                 46 864
candidate a polarità non-supportante o avversa    1 936
promosse a CONSISTENT                                 0
nel PRIMARY_BUCKET                                    0
inversioni automatiche di direzione                   0
```

Esito su `Does Not Support` con enrichment accettato:

```
status = AMBIGUOUS · bucket = WARNING_BUCKET
support_mask.direction = SOURCE_DOES_NOT_SUPPORT
warnings = ['SOURCE_POLARITY_DOES_NOT_SUPPORT']
```

### Due segnalazioni della sonda che NON sono difetti

La sonda ha inizialmente marcato quattro valori come «nel PRIMARY_BUCKET».
Verificato: sono **artefatti della sonda**. Avevo costruito un prodotto
cartesiano che inserisce valori di *direzione clinica* (`Reduced Sensitivity`,
`Adverse Response`) e una stringa malformata (`DoesNotSupport`) nel campo
`evidence_direction` — una forma che **non esiste nei dati**:

```
valori reali di evidence_direction: Supports 7177 · Does Not Support 999 · "" 54 · assente 38 634
```

Con i valori nella loro sede reale il comportamento è corretto:

```
direction='Reduced Sensitivity'  → REJECTED_BUCKET / CONTRADICTED
direction='Adverse Response'     → REJECTED_BUCKET / CONTRADICTED
direction='Does Not Support'     → WARNING_BUCKET  / SOURCE_DOES_NOT_SUPPORT
```

Resta un rilievo teorico (**NEW-03, P3**): una stringa di polarità non mappata
in `evidence_direction` ricade su `UNKNOWN` invece di essere rifiutata. Nessuna
candidate reale è affetta.

---

## ISS-001 · Stop controllato — **CHIUSO**

Nove casi attraverso `orchestrator.run_case`, con le chiamate a valle
**contate**, non dedotte.

| Caso | `run_status` | `stopped_at` | controllato | retrieval | downstream |
|---|---|---|:-:|:-:|:-:|
| out_of_domain | STOPPED | `OUT_OF_SCOPE` | ✅ | 0 | 0 |
| contradictory | STOPPED | `CONTRADICTORY_CASE_CONTEXT` | ✅ | 0 | 0 |
| non_actionable | STOPPED | `NON_ACTIONABLE_MEDICAL_INPUT` | ✅ | 0 | 0 |
| prompt_injection | STOPPED | `OUT_OF_SCOPE` | ✅ | 0 | 0 |
| adversarial_drug | STOPPED | `CASECONTEXT_MISMATCH` | ✅ | 0 | 0 |
| incomplete | STOPPED | `MISSING_REQUIRED_FIELDS` | ✅ | 0 | 0 |
| ambiguous | STOPPED | `CASECONTEXT_MISMATCH` | ✅ | 0 | 0 |
| empty_input | STOPPED | `INVALID_INPUT` | ✅ | 0 | 0 |
| **ELIGIBLE_CONTROL** | COMPLETED | — | — | **1** | **1** |

```
noneligible_retrieval_calls      = 0
downstream_calls (non eleggibili) = 0
controlled_stops_failed          = 0
unexpected_exceptions            = 0
STOP_REASONS = 15, partizionati in 10 controllati + 5 guasti, senza sovrapposizione
```

Il controllo positivo dimostra che il fix non ha trasformato tutto in uno stop.

---

## ISS-003 · Presentazione delle quote — **CHIUSO**

### Otto scenari

| Caso | Esito validatore | Canonicamente accettata | `presentation_state` | Presentabile |
|---|---|:-:|---|:-:|
| A quote valida | `ENRICHMENT_V2_ACCEPTED` | ✅ | `VALIDATED_QUOTE` | ✅ |
| B inventata | `REJECTED_QUOTE_NOT_FOUND` | ❌ | `REJECTED_QUOTE` | ❌ |
| C alterata di una parola | `REJECTED_QUOTE_NOT_FOUND` | ❌ | `REJECTED_QUOTE` | ❌ |
| C2 con punto finale | `ENRICHMENT_V2_ACCEPTED` | ✅ | `VALIDATED_QUOTE` | ✅ |
| D altra SourceUnit | `REJECTED_QUOTE_NOT_FOUND` | ❌ | `REJECTED_QUOTE` | ❌ |
| E altro documento | `REJECTED_SOURCE_UNIT` | ❌ | `REJECTED_QUOTE` | ❌ |
| F SourceUnit inventata | `REJECTED_SOURCE_UNIT` | ❌ | `REJECTED_QUOTE` | ❌ |
| G ABSTAIN | `ENRICHMENT_V2_ABSTAINED` | ❌ | `ABSTAINED` | ❌ |

**Il caso C2 era mal etichettato dalla mia sonda.** La quote
`"did not derive benefit from panitumumab."` — punto finale incluso — **è**
letteralmente nel documento, che termina proprio con quella stringa.
Accettarla è corretto. Corretti i conteggi: **8 su 8 conformi**.

```
invented_quotes_canonically_accepted  = 0
invented_quotes_presented_as_accepted = 0
rejected_quotes_presented_as_accepted = 0
invented_sourceunits_accepted         = 0
wrong_document_quotes_accepted        = 0
```

### Input degeneri

```
esito assente     → PROPOSED_QUOTE_NOT_VALIDATED   (non presentabile)
esito sconosciuto → REJECTED_QUOTE                 (non presentabile)
esito vuoto       → PROPOSED_QUOTE_NOT_VALIDATED   (non presentabile)
PRESENTABLE_AS_AUTHOR_CLAIM = {VALIDATED_QUOTE}
```

### Prova end-to-end su run reali

Quattro run REPLAY attraverso l'API. **CASE-2** contiene una voce reale:

```json
{"presentation_state": "REJECTED_QUOTE",
 "validation_outcome": "REJECTED_QUOTE_NOT_FOUND",
 "accepted_for_gates": false,
 "has_quote": true}
```

Una quote **presente** ma **rigettata**: sotto la regola precedente
(`accepted = quote != null`) sarebbe stata resa come citazione d'autore. È la
dimostrazione sul campo, non su fixture, che ISS-003 è chiuso.

Su tutte le run: `0` voci prive di `presentation_state`, `0` voci presentabili
ma non ammesse ai gate.

Il frontend legge `presentation_state === 'VALIDATED_QUOTE'`; la regola
`quote != null` non compare più in `DossierView.tsx`.

---

## ISS-004 · Build — **CHIUSO**

`npm run build` → **exit 0**, `vite build` raggiunto e completato.

## ISS-005 · RQ4 attraverso l'orchestratore — **CHIUSO**

Rieseguito in directory temporanea: **riproduzione identica** all'artifact
committato, salvo il timestamp. Vedi `04_rq_readiness.md`.

## ISS-006 · Ambiente — **CHIUSO**

```
$ env -u PYTHONPATH pytest -q
3189 passed, 17 skipped, 1 warning, 36890 subtests passed
```

## ISS-007 — **APERTO, non bloccante**

`blocks_freeze = FALSE`. Il §11 chiede solo di verificare che il problema sia
correttamente documentato: lo è, in `docs/pre_freeze_fixes/07_remaining_limits.md`
e `06_rq_impact.md`, che distinguono esplicitamente il denominatore full-corpus
(46 864) da quello end-to-end (16). I report finali **non** confondono i due,
quindi non è nemmeno un blocker documentale.
