# 08 — Decisione di freeze

# `DELIVERABLE_WITH_MINOR_DOCUMENTATION_FIXES`

Il codice può essere congelato oggi. Restano soltanto correzioni **documentali**,
che non richiedono modifiche al runtime né agli esperimenti.

---

## §17 — I diciotto criteri di freeze

| Criterio | Richiesto | Misurato |
|---|:-:|:-:|
| `remaining_p0` | 0 | **0** ✅ |
| `remaining_blocking_p1` | 0 | **0** ✅ |
| `does_not_support_promoted` | 0 | **0** ✅ |
| `negative_source_primary_bucket` | 0 | **0** ✅ |
| `automatic_direction_inversions` | 0 | **0** ✅ |
| `noneligible_retrieval_calls` | 0 | **0** ✅ |
| `expected_controlled_stops_failed` | 0 | **0** ✅ |
| `invented_quotes_canonically_accepted` | 0 | **0** ✅ |
| `invented_quotes_presented_as_accepted` | 0 | **0** ✅ |
| `invented_sourceunits_accepted` | 0 | **0** ✅ |
| `wrong_document_quotes_accepted` | 0 | **0** ✅ |
| `canonical_status_deterministic` | true | **true** ✅ |
| `llm_authority_uncontrolled` | 0 | **0** ✅ |
| `frontend_build_passed` | true | **true** ✅ |
| `backend_tests_passed` | true | **true** ✅ |
| `frontend_tests_passed` | true | **true** ✅ |
| `rq4_canonical_runtime_passed` | true | **true** ✅ |
| `historical_artifacts_unchanged` | true | **true** ✅ |

**Diciotto su diciotto.**

## §18 — Nessuna condizione di hard stop

Tutte e dodici verificate e negative: nessun P0 aperto, nessun nuovo P0, nessuna
fonte negativa promossa, nessuna quote falsa mostrata come validata, canonical
status non controllato dall'LLM, eligibility sicura, artifact riproducibili,
frontend compilabile, backend eseguibile dall'ambiente documentato, LIVE e
REPLAY distinti, risultati storici invariati, claim coerenti con il runtime.

## §22 — Le tredici domande

**1. Tutti e tre i P0 originari risultano realmente chiusi in verifica
indipendente?**
**Sì.** Con sonde scritte da zero e casi più duri: ISS-002 su tutte le 46 864
candidate più valori limite per case, spazi, punteggiatura e tipi non stringa;
ISS-001 su 9 casi attraverso `orchestrator.run_case` con le chiamate contate;
ISS-003 su 8 scenari più 4 run REPLAY reali via API.

**2. Tutti i P1 che bloccavano il freeze risultano chiusi?**
**Sì.** ISS-004 build exit 0, ISS-005 riproduzione identica, ISS-006 3 189 test
senza `PYTHONPATH`.

**3. Una source negativa può ancora diventare supporto positivo?**
**No.** 0 su 46 864 nel percorso runtime, 0 nel `PRIMARY_BUCKET`. Con una
riserva onesta: nel ramo `THERAPY_DISCOVERY` la polarità non è *segnalata*
(NEW-01), ma non produce comunque supporto — `direction = NOT_APPLICABLE`,
bucket `DISCOVERY_BUCKET`.

**4. Un expected eligibility stop può ancora diventare FAILED?**
**No.** 8 su 8 terminano `STOPPED` con stop controllato, 0 eccezioni. E un
guasto reale continua a risalire come eccezione invece di essere mascherato.

**5. Una quote rigettata può ancora essere presentata come accettata?**
**No.** Dimostrato su una run reale: CASE-2 contiene una voce `REJECTED_QUOTE`
con quote presente e `accepted_for_gates: false` — sotto la regola precedente
sarebbe stata resa come citazione d'autore.

**6. I confini di autorità dell'LLM rimangono enforced dal codice?**
**Sì.** `PROMPT_ONLY_RESTRICTION = 0`, `UNCONTROLLED = 0`. Nove chiavi extra
rifiutate dal trasporto, `TOOL_SCHEMA` a 5 proprietà, 2 stage LLM su 16.

**7. RQ1, RQ2, RQ3 e RQ4 sono sostenibili nel perimetro realmente
implementato?**
**Sì**, con le condizioni di `04_rq_readiness.md`: RQ1 come materializzazione da
export congelato, RQ2 come fattibilità e non copertura, RQ3 pienamente, RQ4
attraverso il runtime canonico con i 9 fallimenti di trasporto dichiarati.

**8. I risultati GCA v3 sono correttamente separati dal runtime GCA 2.0?**
**Sì.** `graph_candidate_runtime_version = "2.0"`, `gca_v3_runtime = false`.
`01_claim_scope.md` e `docs/pre_freeze_fixes/06_rq_impact.md` elencano
esplicitamente cosa non si può rivendicare come proprietà del runtime.

**9. I denominatori full-corpus ed end-to-end sono chiaramente distinguibili?**
**Sì nei report** (46 864 vs 16, dichiarati). **Non ancora nelle tabelle della
tesi**: è ISS-007, l'unica correzione documentale rimasta.

**10. Gli artifact storici sono rimasti immutati?**
**Sì.** Verificato per hash e per diff. Le quattro apparenti differenze sono
solo fine riga CRLF/LF.

**11. Un revisore può riprodurre il nucleo del progetto da un clone pulito?**
**Sì.** Ambiente, dati, test, build, REPLAY, esperimenti e metriche. LIVE resta
`REPRODUCIBLE_WITH_EXTERNAL_DEPENDENCY`, con la dipendenza dichiarata dal 503.

**12. Esiste oggi un motivo tecnico o sperimentale per non congelare il codice?**
**No.** L'audit precedente ne aveva uno decisivo — ISS-002, che classificava
come evidenza diretta una candidate la cui fonte la negava. Quel motivo non
esiste più.

**13. Il repository è deliverable?**
**Sì**, con correzioni documentali.

---

## Cosa resta da fare — solo documentazione

1. **ISS-007** — affiancare il denominatore end-to-end (16) a quello full-corpus
   (46 864) in ogni tabella della tesi.
2. **NEW-01** — dichiarare che in `THERAPY_DISCOVERY` l'asse polarità non è
   segnalato.
3. **ISS-012** — dichiarare che ~26 % dei casi non raggiunge il gate per
   fallimento del trasporto del parser.
4. **Perimetro GCA** — non rivendicare come proprietà del runtime le proprietà
   v3 (alterazioni composte, AST, regimi multi-componente).

Nessuna richiede di toccare il codice o rieseguire un esperimento.

---

## Nota di metodo

Questo audit non ha assunto vero nulla del report di correzione. Ha riscritto le
sonde, allargato i casi, e in due punti ha trovato che **le proprie
segnalazioni** erano artefatti della sonda e non difetti del sistema — i valori
di direzione clinica inseriti nel campo `evidence_direction`, e il caso `C2` la
cui quote è realmente letterale nel documento. Entrambi sono documentati come
tali in `02_blocker_reverification.md`, perché un audit che nasconde i propri
falsi positivi non è più verificabile di uno che nasconde i difetti.

Ha inoltre trovato tre rilievi che le fasi precedenti non avevano registrato
(NEW-01, NEW-02, NEW-03), nessuno bloccante.

---

## Verdetto

```
DELIVERABLE_WITH_MINOR_DOCUMENTATION_FIXES
```
