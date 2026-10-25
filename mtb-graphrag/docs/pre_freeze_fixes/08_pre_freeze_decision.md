# 08 — Decisione pre-freeze

# `READY_FOR_FINAL_DELIVERABILITY_AUDIT`

Non `DELIVERABLE`: quella decisione spetta a un ultimo audit indipendente, come
prescritto dal §29.

## §29 — Criteri, uno per uno

| Criterio | Richiesto | Misurato |
|---|:-:|:-:|
| `remaining_p0_count` | 0 | **0** ✅ |
| `remaining_blocking_p1_count` | 0 | **0** ✅ |
| `does_not_support_promoted_after_fix` | 0 | **0** ✅ |
| `noneligible_retrieval_calls_after_fix` | 0 | **0** ✅ |
| `controlled_stops_failed_after_fix` | 0 | **0** ✅ |
| `invented_quotes_presented_as_accepted` | 0 | **0** ✅ |
| `invented_sourceunits_accepted` | 0 | **0** ✅ |
| `canonical_status_still_deterministic` | true | **true** ✅ |
| `frontend_build_passed` | true | **true** ✅ |
| `rq3_regression_passed` | true | **true** ✅ |
| `rq4_regression_passed` | true | **true** ✅ |

Tutti e undici soddisfatti.

## §24 — Nessuna condizione di hard stop raggiunta

| Condizione | Esito |
|---|:-:|
| semantica clinica cambiata arbitrariamente | no |
| una fonte `Does Not Support` diventa ancora supporto | **no** |
| introdotta inversione automatica della direzione | no |
| retrieval consentito a input non eleggibili | no |
| stop controllati implementati nascondendo eccezioni | no — un test verifica il contrario |
| per ISS-003 è stato necessario fidarsi dell'LLM | no |
| una quote rigettata è ancora mostrata come accettata | **no** |
| il frontend decide autonomamente il validation status | **no** — lo legge dal backend |
| GCA v3 resa runtime default | **no** |
| artifact storici sovrascritti | **no** |
| metriche RQ1/RQ2/RQ3 modificate manualmente | no |
| un P0 richiede redesign architetturale | no |
| nuovi P0 emersi | **no** |

## §23 — Re-audit mirato

| Issue | Riprodotto prima | Fix | Test | Verificato | Regressioni | Stato |
|---|:-:|:-:|:-:|:-:|:-:|---|
| ISS-002 | ✅ | ✅ | 19 | ✅ | nessuna | **CLOSED** |
| ISS-001 | ✅ | ✅ | 15 | ✅ | nessuna | **CLOSED** |
| ISS-003 | ✅ | ✅ | 17 + 5 | ✅ | nessuna | **CLOSED** |
| ISS-004 | ✅ | ✅ | build | ✅ | nessuna | **CLOSED** |
| ISS-005 | ✅ | ✅ | 35 casi | ✅ | nessuna | **CLOSED** |
| ISS-006 | ✅ | ✅ | 3 189 | ✅ | nessuna | **CLOSED** |
| ISS-007 | — | — | — | — | — | OPEN, non bloccante |

## Superficie della modifica

**Sette file applicativi**, come previsto dal principio *minimum change*:

```
backend/research_pipeline/determinism/gates.py    +169 -14   ISS-002
backend/research_pipeline/contracts.py             +45  -8   ISS-001
backend/research_pipeline/orchestrator.py          +16  -3   ISS-003
backend/research_pipeline/dossier/builder.py       +76  -2   ISS-003
frontend/src/research/DossierView.tsx              +85  -5   ISS-003
frontend/src/research/stages/EligibilityStage.tsx  +12 -12   ISS-004
backend/config/requirements.txt                    riscritto ISS-006
```

Più 3 file di test nuovi, 1 script di evaluation nuovo, 3 file di
configurazione, e gli artifact di questa fase.

**Nessuna nuova astrazione, nessun refactoring, nessuna feature.** Le funzioni
aggiunte (`source_polarity`, `clinical_direction`, `candidate_source_polarity`,
`candidate_direction_consistency`, `is_controlled_stop`, `presentation_state`,
`annotate_enrichment`) sono predicati locali e leggibili, ciascuno introdotto
per rendere verificabile un invariante che il codice precedente violava in
silenzio.

## §30 — Le dieci domande

**1. Una source «Does Not Support» può ancora essere promossa come supporto
positivo nel runtime?**
**No.** 0 su 46 864 candidate, misurato scorrendo l'intero repository. Né
`Reduced Sensitivity` né `Adverse Response`. Un valore assente o non mappato non
è mai positivo.

**2. Gli stop del gate sono ora esiti controllati o possono ancora diventare
FAILED?**
**Esiti controllati.** I 9 stati non eleggibili sono in `STOP_REASONS` e in
`CORRECT_STOP_REASONS`; `is_controlled_stop()` li distingue dai 5 guasti. Un
guasto reale continua a risalire come eccezione — verificato da un test.

**3. RQ4 può essere misurata attraverso l'orchestratore canonico?**
**Sì.** `evaluation/run_rq4_canonical_runtime.py`, 35 casi, 0 eccezioni, 0
chiamate proibite. E i due percorsi concordano su tutti i casi.

**4. Una quote rigettata può ancora essere mostrata come citazione accettata?**
**No.** 5 → 0. Resta visibile in una sezione di solo audit, barrata, con il
proprio esito e i reason code.

**5. La UI usa lo stato di validazione o continua a dedurlo?**
**Lo usa.** `presentation_state === 'VALIDATED_QUOTE'`. In assenza del campo il
comportamento è conservativo: non presentabile.

**6. Le correzioni hanno modificato il canonical status o i confini di autorità
dell'LLM?**
**No.** `canonical_status_still_deterministic = true`,
`llm_authority_boundary_regressed = false`. Il solo confine che cambia è quello
che l'audit classificava `PARZIALE`, ora chiuso.

**7. GCA v3 è rimasta shadow?**
**Sì.** `GRAPH_CANDIDATE_REPOSITORY_VERSION` non toccato, contratto del runtime
`2.0`, `gca_v3` non importato da alcun modulo del runtime.

**8. Tutti i P0 sono chiusi?**
**Sì.** 3 su 3.

**9. Tutti i P1 che bloccano il freeze sono chiusi?**
**Sì.** 3 su 3. ISS-007 resta aperto ma `blocks_freeze = FALSE` ed è una
correzione di presentazione nella tesi.

**10. Il repository è pronto per un ultimo deliverability audit indipendente?**
**Sì**, con due avvertenze da portare all'audit finale:

- il runtime resta su GCA 2.0, quindi alterazioni composte e regimi
  multi-componente **non** sono semanticamente preservati. Non era nel perimetro
  di questa fase e non va rivendicato (vedi `06_rq_impact.md`);
- LIVE resta non eseguibile senza `data_cache/`, quindi la validazione delle
  quote end-to-end resta dimostrata a livello di componente.

## Verifica finale

```
base_head                                  0219e0a7a4a063668c72c941413fbd8382838b32
branch                                     fix/pre-freeze-deliverability-blockers
commit prodotti                            10
historical_deliverability_audit_unchanged  true
rq1_historical_artifacts_modified          false
rq2_historical_artifacts_modified          false
gca_v3_runtime_default_changed             false
push_executed                              false
merge_executed                             false
```
