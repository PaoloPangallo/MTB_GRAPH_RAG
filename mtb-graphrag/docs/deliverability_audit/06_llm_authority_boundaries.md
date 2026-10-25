# 06 — Confini di autorità dell'LLM (RQ3)

La domanda del §21 non è «il prompt lo vieta?» ma «il codice lo impedisce?».
Ogni riga di questa tabella è verificata eseguendo il codice, non leggendolo.

## §13 — Dove viene assegnato lo stato canonico

Catena esatta, tre funzioni:

```
orchestrator.run_case
  └─ per ogni paper:
       validation = validate(...)                          # validator_v2 in LIVE
       gate_outcome = _accepted_for_gates(validation["outcome"])   # orchestrator.py:63-81
       if gate_outcome is not None:
           validated.append({...})                          # SOLO gli accettati
  └─ evaluation = detpipe.evaluate_association(query_intent, candidate, validated)
                                                            # determinism/gates.py:43-76
  └─ check_origin.checks_payload(evaluation["support_mask"])
                                                            # determinism/check_origin.py
```

`_accepted_for_gates` è il collo di bottiglia, e restituisce `None` per **ogni**
esito non accettato — astensioni e rigetti inclusi. Verificato:

```python
_accepted_for_gates("REJECTED_QUOTE_NOT_FOUND")   -> None
_accepted_for_gates("ENRICHMENT_V2_ABSTAINED")    -> None
_accepted_for_gates("ENRICHMENT_V2_ACCEPTED")     -> "ENRICHMENT_ACCEPTED"
```

`evaluate_association` riceve quindi una lista vuota, e produce
`AMBIGUOUS / NO_DOCUMENT_SIGNAL / WARNING_BUCKET`. Nessun testo narrativo,
nessuna recommendation, nessuna quote non validata partecipa.

### Gli input che NON possono modificare lo status

| Input | Può modificare lo status? | Meccanismo |
|---|:-:|---|
| testo narrativo dell'LLM | ❌ | `evaluate_association` legge solo `evidence_kind` degli enrichment **accettati** |
| recommendation generata | ❌ | `REJECTED_CLINICAL_RECOMMENDATION` al validatore; e comunque non c'è campo |
| quote non validata | ❌ | `_accepted_for_gates` → `None` |
| source neutral / Does Not Support | ⚠️ | **sì, in modo errato** — vedi sotto |
| partial alteration match | ⚠️ | nessun `PARTIAL_MATCH` esiste in v2 (INV-C04) |
| unresolved regimen | ⚠️ | nessuna rappresentazione in v2 (INV-C06) |

Le prime tre righe sono la separazione LLM/deterministico, e **regge**. Le
ultime tre non riguardano l'LLM: riguardano la fedeltà del contratto v2, e sono
il Checkpoint C.

### Onestà del modulo `check_origin`

`check_origin.py` dichiara sei controlli come `NOT_IMPLEMENTED`:

```
source_gate · provenance_gate · completeness · negation · contradiction_gate · score
```

e `DeterministicCheck.__post_init__` **solleva** se un controllo non implementato
dichiara uno `source_stage`, «perché si leggerebbe come eseguito». Distingue
inoltre gli assi `INHERITED_VERIFIED_RESULT` (`disease`, `biomarker`, decisi
allo stage 5) da quelli `COMPUTED_HERE` (`intervention`, `direction`), per non
far sembrare che i gate valutino quattro assi indipendenti.

È il livello di rigore che il resto del progetto dovrebbe avere ovunque.

Va però notato che `source_gate` — dichiarato non implementato — è **esattamente**
il controllo che avrebbe intercettato l'inversione di polarità di INV-C01. La
differenza fra i due casi è sostanziale: qui il sistema **dichiara** una lacuna;
in `gates.direction_consistency` il sistema produce attivamente una risposta
positiva **sbagliata** invece di astenersi.

## §21 — Classificazione dei nove punti

| # | L'LLM può… | Classificazione | Evidenza |
|---|---|---|---|
| 1 | decidere l'eligibility | **IMPOSSIBLE_BY_CONSTRUCTION** | `eligibility/gate.py` + `casecontext/*`: 0 riferimenti a llm/ollama/requests/httpx in 10 moduli. L'output del parser è un *input* al gate, non una decisione |
| 2 | promuovere una candidate | **IMPOSSIBLE_BY_CONSTRUCTION** | il retrieval avviene allo stage 5, prima di qualunque chiamata all'enricher; l'enricher vede solo candidate già selezionate |
| 3 | modificare la polarity | **IMPOSSIBLE_BY_CONSTRUCTION** | `direction` è letto dalla candidate, mai dall'enrichment. *(Che sia letto male è INV-C01, un difetto deterministico, non un'intrusione dell'LLM)* |
| 4 | assegnare il canonical status | **IMPOSSIBLE_BY_CONSTRUCTION** | `evaluate_association` non ha alcun parametro che l'LLM controlli, oltre a `evidence_kind` di enrichment **già validati** |
| 5 | creare provenance | **IMPOSSIBLE_BY_CONSTRUCTION** | `TOOL_SCHEMA` ha 5 proprietà; `transport_v2` righe 71-73 rifiuta chiavi extra con `INVALID_TOOL_ARGUMENTS` |
| 6 | creare una SourceUnit | **IMPOSSIBLE_BY_CONSTRUCTION** | idem, più `SOURCE_UNIT_NOT_FOUND` / `SOURCE_UNIT_NOT_IN_PAPER` |
| 7 | accettare autonomamente una quote | **VALIDATED_DOWNSTREAM** | `validator_v2` verifica `quote not in unit_text`, confronto letterale esatto, zero chiamate al modello |
| 8 | suggerire uno status a parole | **VALIDATED_DOWNSTREAM** | `_STATUS_GATE_WORDS` → `REJECTED_SUMMARY_UNGROUNDED` |
| 9 | modificare il dossier canonico | ⚠️ **PARZIALE** | status/mask/bucket protetti; **ma** `author_context` riceve il testo del modello senza filtro di validazione — vedi INV-D06 in `05_document_grounding.md` |

**Otto punti su nove sono impossibili per costruzione o validati a valle.** Non
esiste alcun punto classificato `PROMPT_ONLY_RESTRICTION` o `UNCONTROLLED`.

Questo è il risultato più solido dell'intero audit, ed è il nucleo di RQ3.

## Le due chiamate LLM, delimitate

`contracts.LLM_STAGE_IDS` è un `frozenset` di **due** elementi:

```python
LLM_STAGE_IDS = frozenset({"stage_2_casecontext_parser", "stage_9_paper_context_enricher"})
```

con il commento: «I soli due stage che un LLM può produrre. Ogni altro stage è
deterministico: è ciò che impedisce a Gemma di comparire come autore di gate,
status, direction, contraddizione, score o bucket.»

Verificato che il `StageProducer` di ogni altro stage è costruito da
`_deterministic(...)` con `kind="DETERMINISTIC"`. Il vincolo è dichiarato nel
contratto e rispettato nell'implementazione.

`MAX_LLM_CALLS_PER_RUN = 6` (`run_store.py:36`), speso da `budget.spend(...)` in
`live_providers.parser_fn` e `enricher_fn`. Il commento in `live_providers`
documenta che nel runtime precedente il budget era «dichiarato e non applicato»
— ora lo è.

## Sintesi

```
llm_can_directly_change_canonical_status = false   ✅
llm_can_create_provenance                = false   ✅ (impossibile per costruzione)
llm_can_create_sourceunit                = false   ✅
llm_can_accept_its_own_quote             = false   ✅ (validato a valle)
llm_can_decide_eligibility               = false   ✅
prompt_only_restrictions                 = 0       ✅
uncontrolled_paths                       = 0       ✅
narrator_can_change_canonical_dossier    = n/a     (narrator non implementato)
llm_output_reaches_dossier_unfiltered    = true    ❌ INV-D06
```
