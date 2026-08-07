# 01 — ISS-002 · Source polarity

**P0, hard stop §28 dell'audit. CHIUSO.**
Dati: `evaluation/pre_freeze/source_polarity_results.json`.

## Cosa è stato indagato prima di toccare il codice

Il §3 chiedeva cinque accertamenti. Esiti:

| Domanda | Risposta |
|---|---|
| Campo realmente usato dal runtime | `candidate["direction"]`, letto solo da `gates.evaluate_association` |
| Valori reali osservati | 8: `Supports` 4 295, `Does Not Support` 513, `Resistance` 1 184, `Sensitivity/Response` 2 158, `""` 54, `Adverse Response` 12, `Reduced Sensitivity` 14, `None` 38 634 |
| Dove `evidence_direction` viene ignorato | `grep -rn evidence_direction backend/research_pipeline/` → **0 occorrenze**. Il dato esiste in `source_properties.evidence` (7 177 `Supports`, 999 `Does Not Support`) e nessun modulo lo legge |
| Mapping duplicati | Sì: `backend/pipeline/evidence/v2_adapter.py::DIRECTION_TO_POLARITY` mappa già `supports` / `does not support`. È **legacy** e non raggiungibile dal runtime di ricerca; ne ho riusato il **vocabolario**, non il codice |
| Stessa logica di sottostringa altrove | Sì, in `documents/authorized_cache.py:162-163`, ma **non decide supporto**: etichetta gli strati del campionamento del corpus pilota. Toccarla cambierebbe la selezione e quindi artifact storici. **Lasciata invariata**, registrata come nota |

## La correzione

`backend/research_pipeline/determinism/gates.py`. Due assi separati, letti per
**valore normalizzato esatto**, con la negazione valutata **prima**
dell'affermazione.

```python
source_polarity(v)     -> SUPPORTS | DOES_NOT_SUPPORT | CONTRADICTS | NEUTRAL | UNKNOWN
clinical_direction(v)  -> SENSITIVITY | RESISTANCE | POLARITY_ONLY | UNKNOWN
candidate_source_polarity(candidate)   # risolve la polarità dai due punti in cui vive
candidate_direction_consistency(...)   # entry point sicuro a livello di candidate
```

Regola, nell'ordine:

1. se la polarità è in `NON_SUPPORTING_POLARITIES` → esito dedicato
   `SOURCE_DOES_NOT_SUPPORT`, **qualunque cosa riporti l'enrichment**;
2. altrimenti direzione clinica per valore esatto;
3. valore non mappato → `UNRELATED`, mai positivo.

`evaluate_association` instrada l'esito negativo in `WARNING_BUCKET` con il
proprio warning, **prima** di ogni altro ramo. La candidate resta visibile con il
motivo invece di sparire.

### I requisiti del §3, uno per uno

| Requisito | Esito |
|---|:-:|
| `SUPPORTS` trattato come supporto solo secondo la policy esistente | ✅ invariata |
| `DOES_NOT_SUPPORT` non può diventare `SUPPORTED` | ✅ |
| `CONTRADICTS` non può diventare `SUPPORTED` | ✅ mappato benché assente dall'export |
| `NEUTRAL` / `NO DIFFERENCE` non può diventare `SUPPORTED` | ✅ mappato |
| `UNKNOWN` / `NULL` / non mappato non positivo per default | ✅ già corretto prima, non peggiorato |
| Nessuna inversione automatica della direzione | ✅ un test lo verifica esplicitamente |

## Prima e dopo

```
                                             prima      dopo
does_not_support_promoted                        1    ->    0
negative_source_primary_bucket                   1    ->    0
valori negativi promossi a CONSISTENT            5    ->    0
candidate negative promosse (percorso runtime) 752    ->    0
candidate negative nel PRIMARY_BUCKET (46 864)   —    ->    0
automatic_direction_inversions                   —    ->    0
```

Esito per una candidate `Does Not Support` con enrichment accettato:

```
prima  status=DIRECT     bucket=PRIMARY_BUCKET  direction=SUPPORTED               warnings=[]
dopo   status=AMBIGUOUS  bucket=WARNING_BUCKET  direction=SOURCE_DOES_NOT_SUPPORT
       warnings=['SOURCE_POLARITY_DOES_NOT_SUPPORT']
```

## Una misura che resta 213, e perché è corretto

`population_promoted_v2_field_only` vale ancora 213. Non è un residuo del
difetto: è la misura che chiama `direction_consistency` con il **solo** campo
`direction`, e per quelle 213 candidate la polarità vive esclusivamente in
`source_properties`. Quella chiamata risponde a una domanda più ristretta —
«questa direzione clinica e questo `evidence_kind` concordano?» — e la sua
risposta `CONSISTENT` è corretta *per ciò che le è stato chiesto*.

Il percorso realmente eseguito (`evaluate_association` →
`candidate_source_polarity`) dà **0**. Entrambe le misure sono riportate
nell'artifact: non ho sostituito la metrica originale, ne ho aggiunta una che
misura il runtime.

Per impedire l'uso scorretto a un chiamante futuro è stato aggiunto
`candidate_direction_consistency(candidate, evidence_kind)`, documentato come
l'entry point da usare per ogni decisione sul supporto.

## Test

`backend/research_pipeline/tests/test_source_polarity_gate.py` — **19 test, 13
subtest**.

Falsificazione verificata eseguendo le asserzioni chiave contro `gates.py` di
`0219e0a`: **7 su 7 falliscono**.

`WholeRepositorySweep` scorre tutte le **46 864** candidate v2 — l'equivalente
del controllo che esisteva solo per v3 — e include la fixture reale
`GCA-003ca9889b3d8906d4674f37`, l'unica candidate a polarità negativa
raggiungibile end-to-end, individuata dall'audit.

Quattro test proteggono la direzione opposta: `Supports` + `RESPONSE` resta
`PRIMARY_BUCKET`, `Sensitivity/Response` idem, `Resistance` + `RESISTANCE` idem,
`Resistance` + `RESPONSE` resta `CONTRADICTED`.
