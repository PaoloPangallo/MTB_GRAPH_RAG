# 00 — Baseline dei blocker, riprodotta prima di ogni modifica

Fonti rilette integralmente: `docs/deliverability_audit/12_open_issues.md`,
`docs/deliverability_audit/13_final_deliverability_decision.md`,
`evaluation/deliverability/issues.csv` (21 righe).

Riproduzione: `evaluation/pre_freeze/baseline_issues.json`, prodotta da
`evaluation/pre_freeze/probes/repro_p0.py` — lo **stesso** script verrà rieseguito
dopo i fix, senza modifiche.

## §0 — Stato di partenza

| | |
|---|---|
| Base HEAD | `0219e0a7a4a063668c72c941413fbd8382838b32` ✅ come richiesto |
| Branch creato | `fix/pre-freeze-deliverability-blockers` |
| Working tree | **non pulita** — deviazione già autorizzata nella fase precedente |
| Worktree | 4 registrati, 3 in `%TEMP%`, non toccati |
| Runtime canonico | `orchestrator.py::run_case` via `research_routes` |
| GCA repository del runtime | `graph_candidate_repository/**2.0**` — **resta 2.0** |

**Working tree.** Il §0 imporrebbe di fermarsi. I file non puliti sono: i tre
staged e i dodici untracked già documentati e autorizzati nella fase di audit
(immagini, PDF/TeX, artifact esploratori, uno script PowerShell), più le due
directory di audit `evaluation/deliverability/` e `docs/deliverability_audit/`
che **questo stesso mandato ordina di conservare**. Nessun file `.py` applicativo
è modificato rispetto a `0219e0a`. La deviazione è la stessa già approvata e
viene qui riconfermata.

Hash dei file che verranno toccati, registrati prima di ogni modifica in
`evaluation/pre_freeze/raw/A00_file_hashes_before.json`.

## Perimetro

| Issue | Severità | blocks_freeze | In questo branch |
|---|:-:|:-:|:-:|
| ISS-001 eligibility stop | P0 | TRUE | ✅ |
| ISS-002 source polarity | P0 | TRUE | ✅ |
| ISS-003 quote presentata come accettata | P0 | TRUE | ✅ |
| ISS-004 build frontend | P1 | TRUE | ✅ |
| ISS-005 RQ4 bypassa l'orchestratore | P1 | TRUE | ✅ |
| ISS-006 dipendenze non pinnate | P1 | TRUE | ✅ |
| ISS-007 denominatore end-to-end | P1 | **FALSE** | ❌ correzione di presentazione nella tesi, non di codice |
| ISS-008 … ISS-021 | P2/P3 | FALSE | ❌ §15 del mandato |

`ISS-017` (`run_rq1` / `run_gca_v3_audit` non onorano `OUT`) è classificato **P3**
in `issues.csv`: per il §17 del mandato **non** viene corretto qui. Durante i
test si userà comunque una directory temporanea dedicata, come richiesto.

---

## ISS-002 — Source polarity · riprodotto

`backend/research_pipeline/determinism/gates.py:24-40` · `direction_consistency`

**Comportamento osservato.** Il test di sottostringa non gestisce la negazione:

| `direction` | `evidence_kind=RESPONSE` | promosso? |
|---|---|:-:|
| `Does Not Support` | `CONSISTENT` | ❌ |
| `does not support` | `CONSISTENT` | ❌ |
| `  DOES NOT SUPPORT  ` | `CONSISTENT` | ❌ |
| `Reduced Sensitivity` | `CONSISTENT` | ❌ |
| `Adverse Response` | `CONSISTENT` | ❌ |

Esito end-to-end su una candidate `Does Not Support` con enrichment accettato:

```
status      = DIRECT
support_mask.direction = SUPPORTED
gate_bucket = PRIMARY_BUCKET
warnings    = []
```

```
does_not_support_promoted      = 1
negative_source_primary_bucket = 1
population_promoted_v2         = 752
reachable_end_to_end           = ['GCA-003ca9889b3d8906d4674f37']
```

**Conseguenza runtime.** 752 candidate su 46 864 nel repository che il runtime
usa ricevono supporto positivo pur avendo una fonte negativa o avversa.

**Conseguenza scientifica.** Hard stop §28 dell'audit: la polarità negativa viene
convertita automaticamente in positiva. Invalida la *representation fidelity* sul
percorso eseguito.

**Minimum fix dell'audit.** Confrontare valori normalizzati espliciti verificando
la negazione **prima** dell'affermazione; leggere `evidence_direction` come asse
separato da `direction`; test su tutte le 46 864 candidate v2.

**Nota**: `unknown_promoted = []` — i valori vuoti/ignoti già restituiscono
`UNRELATED`, non `CONSISTENT`. Quella parte del contratto è già corretta e non va
peggiorata.

---

## ISS-001 — Eligibility stop · riprodotto

`orchestrator.py:417` + `contracts.py:46-57` · `_finalize` / `STOP_REASONS`

| Caso | `run_status` | `stopped_at` | `retrieval_called` | Eccezione |
|---|---|---|:-:|---|
| out_of_domain | **RAISED** | — | 0 | `ValueError: stop reason sconosciuta: 'OUT_OF_SCOPE'` |
| empty_input | **RAISED** | — | 0 | `ValueError: … 'INVALID_INPUT'` |
| non_actionable | **RAISED** | — | 0 | `ValueError: … 'NON_ACTIONABLE_MEDICAL_INPUT'` |
| prompt_injection | **RAISED** | — | 0 | `ValueError: … 'OUT_OF_SCOPE'` |

```
controlled_stops_failed     = 4 / 4
noneligible_retrieval_calls = 0        ← l'invariante di sicurezza REGGE
```

**Conseguenza runtime.** Uno stop previsto dalla policy si presenta come guasto
software. `RunStore._execute` lo cattura e riporta `FAILED` /
`LIVE_STAGE_FAILED`, con `stages_executed = []`.

**Conseguenza scientifica.** RQ4 non è dimostrabile attraverso il runtime
canonico.

**Minimum fix dell'audit.** Aggiungere gli 8 stati a `STOP_REASONS` e decidere
quali appartengono a `CORRECT_STOP_REASONS`; test del ramo non eleggibile
attraverso `orchestrator.run_case`.

Da correggere è il **contratto di rappresentazione dello stop**, non la policy di
eligibility, che è già corretta.

---

## ISS-003 — Quote rigettata presentata come accettata · riprodotto

`orchestrator.py:616-617` + `frontend/src/research/DossierView.tsx:89`

| Caso | Esito validatore | Accettata canonicamente | Presentata come accettata | Difetto |
|---|---|:-:|:-:|:-:|
| A quote valida | `ENRICHMENT_V2_ACCEPTED` | ✅ | ✅ | — |
| B quote inventata | `REJECTED_QUOTE_NOT_FOUND` | ❌ | **✅** | ⛔ |
| C quote alterata | `REJECTED_QUOTE_NOT_FOUND` | ❌ | **✅** | ⛔ |
| D altra SourceUnit | `REJECTED_QUOTE_NOT_FOUND` | ❌ | **✅** | ⛔ |
| E altro documento | `REJECTED_SOURCE_UNIT` | ❌ | **✅** | ⛔ |
| F SourceUnit inventata | `REJECTED_SOURCE_UNIT` | ❌ | **✅** | ⛔ |
| G ABSTAIN | `ENRICHMENT_V2_ABSTAINED` | ❌ | ❌ | — |
| H quote vuota | `REJECTED_QUOTE_NOT_FOUND` | ❌ | ❌ | — |

```
presented_as_accepted_but_not_validated = 5
author_context entries carrying validation_outcome = false
```

**Conseguenza runtime.** `enrichment_entries.append(call["enrichment"])` è
incondizionato rispetto all'esito. Le voci di `author_context` **non portano**
il proprio esito di validazione, quindi la UI non ha modo di filtrarle
correttamente e ricorre a `accepted = quote != null`.

**Conseguenza scientifica.** Una quote fabbricata viene mostrata al clinico come
citazione d'autore. Lo stato canonico resta protetto (`AMBIGUOUS`,
`NO_DOCUMENT_SIGNAL`, `WARNING_BUCKET`) — verificato.

**Minimum fix dell'audit.** Allegare a ogni voce di `author_context` il proprio
`validation_outcome` e far filtrare la UI su quello.

---

## Invarianti che NON devono degradare

Da `13_final_deliverability_decision.md`, verificati prima del fix e da
riverificare dopo:

```
noneligible_retrieval_calls        = 0
invented_quotes_accepted           = 0
invented_sourceunits_accepted      = 0
wrong_document_quotes_accepted     = 0
llm_can_directly_change_canonical_status = false
prompt_only_restrictions           = 0
uncontrolled_paths                 = 0
live_replay_distinction_enforced   = true
graph_candidate_contract_version   = "2.0"    ← deve restare 2.0
backend tests 3047 · evaluation 91 · frontend 195
```
