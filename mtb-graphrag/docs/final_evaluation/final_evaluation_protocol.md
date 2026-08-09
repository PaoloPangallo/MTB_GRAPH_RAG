# Final Evaluation Protocol — MTB GraphRAG

    protocol_version : mtb-graphrag-final-evaluation/1.0
    runtime_commit   : f52bbf5920c14324953be849e666bc84571957e9
    runtime_branch   : feature/live-document-retrieval-selector
    protocol_branch  : eval/final-evaluation-protocol
    date             : 2026-08-09
    runtime_modified : false
    status           : PROPOSED — non congelato finché non approvato

Questo documento definisce cosa verrà misurato, su quali dati, con quali
denominatori e con quali criteri di successo. È scritto **prima** dell'esecuzione
finale e non contiene risultati finali.

I numeri che compaiono qui sono di due tipi, sempre etichettati:

* **denominatori e inventari** — proprietà dei dataset, note per costruzione;
* **misure storiche già osservate** — riportate solo per giustificare scelte di
  disegno, mai come criterio di successo (§9).

---

## 1. Principio sperimentale

La tesi non sostiene che il sistema sia clinicamente accurato. Sostiene una
proprietà architetturale:

> il sistema costruisce un dossier tracciabile impedendo che componenti
> generativi o segnali non validati modifichino autonomamente lo stato canonico.

Ne discende che le metriche primarie sono **invarianti con target 0** e
**catene di provenienza ricostruibili**, non punteggi di qualità clinica. Le
metriche di ranking esistono, ma servono a caratterizzare un componente
(il SourceUnit Selector), non a dimostrare la tesi.

La final evaluation verifica sei proprietà: fedeltà della rappresentazione (A),
document grounding (B), separazione dell'autorità (C), robustezza e
comportamento selettivo (D), generalizzazione LIVE e riproducibilità REPLAY (E),
costo operativo (F).

---

## 2. Sistema sotto test

`FULL_SYSTEM` = runtime a `f52bbf5`, con tutti i componenti attivi:

| Stage | Componente | Produttore |
|---|---|---|
| 1 | case input | deterministico |
| 2 | CaseContext Parser | LLM |
| 3 | CaseContext Match / Semantic Verifier | deterministico |
| 3b | Pre-Retrieval Eligibility Gate `1.0` | deterministico |
| 4–5 | retrieval plan + KG retrieval su `graph_candidate_repository/2.0` | deterministico |
| 6 | document resolution (cache-first, API on miss) | deterministico |
| 7 | canonical parser → SourceUnits | deterministico |
| 8 | paper selection + SourceUnit Selector `deterministic-sourceunit-selector/1.0`, K=5 | deterministico |
| 9 | Paper Context Enricher V2 | LLM |
| 10 | quote validator v2 | deterministico |
| 11–12 | gate deterministici + stato canonico | deterministico |
| 13 | dossier builder | deterministico |
| 14 | Dossier Narrator | LLM |
| 15 | Narrative Verifier `narrative-verifier/1.0` | deterministico |

Tre stage sono generativi (2, 9, 14). Ognuno è seguito da un verificatore
deterministico. Nessuno scrive stato canonico.

**Versione GCA del runtime: 2.0.** Verificato: `data_access.py` legge
`graph_candidate_repository/2.0/candidates.jsonl` e nessun modulo del runtime
importa `kg_retrieval_v3`. Le proprietà di `3.0` (polarità esplicita, regimi
preservati come unità, alterazioni composte) **non vanno attribuite al sistema
valutato**; entrano nel protocollo solo come confronto shadow in RQ1.

Durante la final evaluation il runtime non viene modificato. Le ablation sono
implementate esclusivamente nell'harness di valutazione (§8).

---

## 3. Research Questions

### RQ1 — Representation fidelity

Quanto fedelmente la rappresentazione materializzata derivata dal KG preserva
disease, biomarker, intervention, direction/polarity e provenance.

* **Corpus**: `GCA_REPOSITORY_2_0_46864` — popolazione completa, nessun
  campionamento, quindi nessun leakage di selezione possibile.
* **Gold**: path eleggibili riderivati indipendentemente dall'export CSV
  congelato (`evaluation/rq1/kg_source.py`), senza rieseguire il
  materializzatore. Non è un confronto tautologico.
* **Metriche primarie**: structural precision, structural recall, field
  completeness, `does_not_support_promoted`, `negative_source_primary_bucket`,
  `automatic_direction_inversions`.
* **Confronto shadow**: `GCA_REPOSITORY_3_0_SHADOW`, dichiarato come non-runtime.
* **Perdite semantiche note del 2.0 da riportare, non da nascondere**:
  `ALTERATION_LOST`, `REGIMEN_SPLIT`, `DIRECTION_INVERSION` a livello di grafo.

### RQ2 — Document grounding

Quanto efficacemente la pipeline collega una GCA a evidenza documentale
attribuita e verificabile, lungo la catena:

    GCA → document identifier → resolution → snapshot → parser → SourceUnits
        → paper selection → Selector → top-5 → QUOTE/ABSTAIN → validator

* **Corpus di ranking**: `SOURCEUNIT_SELECTOR_INDEPENDENT_20` (unico corpus
  INDEPENDENT del progetto).
* **Corpus di catena**: testbed A (§5).
* **Denominatori obbligatori in coppia**: 20 coppie complessive e 9 casi
  positivi. Riportare solo il secondo è vietato dal protocollo.

### RQ3 — Authority separation

I confini deterministici impediscono ai componenti generativi di modificare
stato canonico, provenance o output verificato.

Valutata come **FULL SYSTEM + ablation** (§8) e sintetizzata nella safety matrix
(§10). Target: 0 su tutti i failure safety-critical, ciascuno con denominatore.

### RQ4 — Robustness / selective behavior

Comportamento su COMPLETE, INCOMPLETE, AMBIGUOUS, OOD, CONTRADICTORY, NEGATIVE,
ADVERSARIAL_CASECONTEXT, ADVERSARIAL_QUOTE, ADVERSARIAL_NARRATIVE.

Metriche: correct controlled stop, forbidden retrieval rate, unexpected
exception rate, inappropriate continuation, wrong status escalation, invalid
quote acceptance, abstention behavior, narrative rejection, fallback correctness.

### RQ5 — Controlled external citation recovery (OncoKB)

**Classificata FUTURE WORK / EXTENSION.** Evidenza:
`oncokb_integrated_into_runtime = false`, `pilot_executed = false`,
`oncokb_knowledge_data_retrieved = false`, `queries_executed = 0`; motivo
registrato `ONCOKB_FALLBACK_BLOCKED_NO_AUTHORIZATION + ONCOKB_FALLBACK_LOW_YIELD`.
Nessuna implementazione viene avviata per riempire una RQ.

---

## 4. Split, leakage e classificazione dei corpus

Ogni corpus è classificato PILOT / DEVELOPMENT / INDEPENDENT / FINAL_TEST in
`evaluation/final_protocol/split_manifest.json`. Le classificazioni sono
motivate da ordinamento temporale verificabile su git, non da dichiarazione.

| Corpus | N | Split | Ruolo finale | Componente contaminato |
|---|---|---|---|---|
| `GCA_REPOSITORY_2_0_46864` | 46 864 candidate | FINAL_TEST | RQ1 full-corpus + sweep polarità | — |
| `GCA_REPOSITORY_3_0_SHADOW` | 46 142 candidate | FINAL_TEST | confronto shadow RQ1 | — |
| `SOURCEUNIT_SELECTOR_INDEPENDENT_20` | 20 coppie / 20 doc / 1 697 unità | **INDEPENDENT** | evidenza primaria di generalizzazione del retrieval | — |
| `CASECONTEXT_ROBUSTNESS_35` | 35 casi | DEVELOPMENT | robustness matrix + regression | Eligibility Gate `1.0` |
| `FROZEN_EVIDENCE_BUNDLES_25` | 25 bundle / 16 candidate / 76 unità gold | DEVELOPMENT | riproducibilità REPLAY + regression selector | Selector (feature, K) |
| `AUTHORIZED_DOCUMENT_CACHE_43` | 43 doc / 3 402 unità | DEVELOPMENT | substrato cache hit/miss e degradazione | — |
| `DOSSIER_NARRATOR_25` | 25 narrative | DEVELOPMENT | ablation Narrative Verifier | `narrative-lexicon/1.0` |
| `NARRATOR_ADVERSARIAL_20` | 20 attacchi | DEVELOPMENT | safety matrix layer narrativo | `narrative-verifier/1.0` |
| `QUOTE_VALIDATOR_BATTERY_14` | 14 scenari | DEVELOPMENT | safety matrix layer quote | validator v2 |
| `END_TO_END_PIPELINE_PILOT_5` | 5 casi | PILOT | regression only | orchestrator routing |

### 4.1 Contaminazioni accertate — da dichiarare in tesi

Tre contaminazioni sono state verificate con timestamp e vanno riportate:

1. **Eligibility Gate ← benchmark CaseContext.** Benchmark congelato
   `2026-08-06T14:32:06Z`, eseguito `14:43Z`. Il gate è stato scritto alle
   `19:34Z` dello stesso giorno, e il suo docstring cita esplicitamente il
   fallimento osservato su quel benchmark («nel benchmark RQ4 un CaseContext
   completamente vuoto superava `essential_fields_pass` … ed entrava nel
   retrieval»). I 35 casi sono quindi **regression del gate, non
   generalizzazione**.

2. **Narrative lexicon ← benchmark narratore.** La prima esecuzione LIVE produsse
   3 FAIL, il lexicon fu corretto e **le stesse 25 narrative** furono
   riverificate ottenendo 25/25. Il 25/25 è un risultato post-tuning sullo stesso
   campione e non può essere presentato come accuratezza del verifier.

3. **Selector ← bundle congelati.** Feature e K=5 sono stati scelti osservando i
   76 SourceUnit gold dei 25 bundle. Quel corpus non è evidenza di
   generalizzazione del selector.

Il corpus indipendente è invece pulito: selector congelato `2026-08-08T09:11Z`,
corpus e gold congelati `10:59Z`, valutazione `11:00Z`, con
`selector_code_modified = false`, `selector_weights_modified = false` e
leakage audit a 0 accessi al gold durante l'inferenza.

### 4.2 Sovrapposizioni

* corpus indipendente ↔ pilot: `overlap_with_pilot_candidates = 0`,
  `overlap_with_pilot_documents = 0` (verificato nell'inventario del corpus);
* corpus indipendente ↔ LIVE unseen-document E2E: **sovrapposizione voluta di 1
  caso** (`GCA-0101aa9c8f708d6f8dd74be0` → `pmcid:PMC4157820`). Riuso per una
  proprietà diversa (acquisizione LIVE), non tuning. Va dichiarato.

---

## 5. Testbed

Cinque testbed distinti e collegati. Nessuna RQ è forzata su un unico dataset.

### TESTBED A — end-to-end final corpus · N = 55

L'obiettivo ideale di §10 della richiesta è 40–60 casi. Il massimo corpus
metodologicamente difendibile costruibile **senza inventare casi clinici privi
di fonte** è:

| Strato | Sorgente | N |
|---|---|---|
| A. eligible / straightforward | `CASECONTEXT_ROBUSTNESS_35` · IN_SCOPE_COMPLETE | 5 |
| B. eligible con grounding documentale | `SOURCEUNIT_SELECTOR_INDEPENDENT_20` · 9 casi positivi | 9 |
| C. ABSTAIN expected | `SOURCEUNIT_SELECTOR_INDEPENDENT_20` · 11 casi zero-direct | 11 |
| D. incomplete | `CASECONTEXT_ROBUSTNESS_35` · IN_SCOPE_INCOMPLETE | 5 |
| E. ambiguous | `CASECONTEXT_ROBUSTNESS_35` · AMBIGUOUS | 5 |
| F. OOD | `CASECONTEXT_ROBUSTNESS_35` · OUT_OF_SCOPE | 5 |
| G. contradictory | `CASECONTEXT_ROBUSTNESS_35` · CONTRADICTORY | 5 |
| H. non-actionable | `CASECONTEXT_ROBUSTNESS_35` · NON_ACTIONABLE_MEDICAL_INPUT | 5 |
| J. adversarial CaseContext | `CASECONTEXT_ROBUSTNESS_35` · ADVERSARIAL | 5 |
| **Totale** | | **55** |

Lo strato **I (document degradation)** e la distinzione full-text/abstract **non
sono pre-assegnati**: sono classificazioni *osservate* dell'esito di
acquisizione sui 20 casi con identificatore documentale, riportate con il
proprio denominatore. Pre-assegnarli richiederebbe conoscere la disponibilità
PMC prima della run, cioè guardare il risultato.

Lo strato **H (Does Not Support / polarità negativa)** non è nel testbed A: è
misurato full-corpus su 46 864 candidate (§7), che è un denominatore
incomparabilmente più forte di una manciata di casi campionati.

**Etichetta obbligatoria: `stratified challenge set`.** Non è un campione a
prevalenza clinica e non va presentato come tale.

**Limitazione dichiarata**: 35 dei 55 casi sono DEVELOPMENT rispetto
all'Eligibility Gate. Il testbed A misura quindi la *tenuta degli invarianti
architetturali* — dove la contaminazione da tuning è poco dannosa perché le
metriche sono oggettive e il target è 0 — e **non** la generalizzazione del gate
su input mai visti. Quest'ultima resterebbe da dimostrare su un corpus nuovo.

### TESTBED B — independent SourceUnit corpus · N = 20

Confronto First-K vs BM25 vs deterministic selector, e GOLD vs SELECTOR
downstream Gemma, sulle stesse coppie congelate (§6, §7).

### TESTBED C — adversarial / safety corpus · N = 59

`NARRATOR_ADVERSARIAL_20` + `DOSSIER_NARRATOR_25` + `QUOTE_VALIDATOR_BATTERY_14`:
verifier, quote validator, polarity, mismatch, narratore.

Composizione del sotto-corpus narratore, da dichiarare: 20 dossier sintetici e
5 da campione REPLAY reale, perché il campione REPLAY non produce candidate
`DIRECT`. Le colonne del revisore umano sono vuote: la fedeltà è verificata
automaticamente, non da giudizio esperto.

### TESTBED D — REPLAY historical corpus · N = 25

I 25 bundle congelati. Misura la riproducibilità, non la performance.

### TESTBED E — LIVE operational corpus · N = 43 documenti

Il manifest della cache autorizzata più il caso unseen-document. Copre cache
hit, cache miss, PMID→PMCID, PMC full text, degradazione ad abstract
(3 `PMC_RESOLUTION_FAILED` noti), documento non disponibile.

---

## 6. Baseline

Un solo confronto di retrieval, sulle stesse 20 coppie, **paired**:

1. **FIRST-K** — prime k unità nell'ordine del documento;
2. **BM25** — ranking lessicale sulla query derivata dalla candidate;
3. **DETERMINISTIC SELECTOR** — il componente del runtime.

Stesso K, stesso documento, stesso insieme di SourceUnit, stesso gold.

Metriche: HitRate@3/@5/@10, Recall@5/@10, Precision@5, MRR, mean e median first
relevant rank, full coverage@5/@10 — ciascuna riportata sia sul denominatore
complessivo (20) sia sui soli casi positivi (9), e sia su `direct` sia su
`direct + partial`.

Non esistono altre baseline. Embedding, reranker neurali, soglie di rifiuto,
nuovi modelli, nuovi prompt, OncoKB, GCA v3 e KG alternativi introdurrebbero
variabili nuove, non ablation del sistema congelato: sono esclusi (§11).

---

## 7. Esperimenti

### E1 · RQ1 fidelity full-corpus
Riderivazione dei path eleggibili + confronto di contratto su 46 864 candidate.
Offline, deterministico, nessuna chiamata LLM.

### E2 · Negative polarity sweep full-corpus
Su 46 864 candidate, di cui 1 936 a polarità negativa. Riportare:
`TOTAL_CORPUS`, `NEGATIVE_SOURCE_CANDIDATES`, `DOES_NOT_SUPPORT_PROMOTED`,
`NEGATIVE_SOURCE_PRIMARY_BUCKET`, `DIRECTION_INVERSION`. Da non confondere con la
vecchia metrica stretta `direction_consistency`.

### E3 · SourceUnit retrieval comparison
Testbed B, tre strategie, paired (§6).

### E4 · GOLD vs SELECTOR downstream
Stessi 20 casi, stesso contratto Gemma, stesso validator. Metriche: valid
transport, QUOTE, ABSTAIN, validated quote, rejected quote, wrong doc, wrong
SourceUnit, wrong quote, decision concordance. Riportate separatamente per i 9
casi positivi e gli 11 zero-direct.

### E5 · End-to-end final evaluation
Testbed A, FULL_SYSTEM, LIVE, 1 run per caso.

### E6 · Ablation study
Quattro ablation (§8), paired sugli stessi casi.

### E7 · LIVE evaluation
Testbed E. Casi: cache hit, cache miss, PMID-only→PMCID, PMC full text, PMC
non disponibile → degradazione ad abstract, unseen document, documento non
disponibile, parser failure su fixture, selector failure su fixture.

Per ogni run: `cache_hit`, `network_fetch`, `snapshot_persisted`,
`document_resolved`, `source_units`, `paper_selection`, `selector_called`, `K`,
`gemma_called`, `validator_called`, `run_state`, `failure_reason`.

### E8 · REPLAY evaluation
Testbed D. Dimostra riproducibilità, **non** performance: `network_calls = 0`,
`live_selector_calls = 0`, `frozen_bundle_used = true`, `source_unit_ids`
preservati, output canonico preservato, metriche storiche riprodotte, accordo
sugli hash deterministici dove applicabile.

### E9 · Latency e cache
Per-stage `duration_ms` è già registrato dall'orchestratore per tutti i 15 stage.
Riportare median, mean, p95 (solo se N ≥ 20), min, max.

Confronto operativo principale: **CACHE HIT vs CACHE MISS + API** sullo stesso
documento. I cache miss falliti e i cache miss con acquisizione riuscita **non
vanno mediati insieme**.

---

## 8. Ablation study

Le ablation non modificano il runtime. Sono implementate nell'harness di
valutazione come shadow runner/wrapper offline. Nessun commit cambia il
comportamento canonico di `f52bbf5`.

### Ablation A — CaseContext Verifier
FULL: parser → verifier → gate → retrieval.
ABLATION: bypass del verifier **solo nel runner sperimentale**.
Corpus: mismatch, incomplete, OOD, contradictory, adversarial.
Metriche: forbidden retrieval rate, bad CaseContext propagated, downstream
candidates generated, incorrect continuation.
Domanda: quanto del comportamento sicuro dipende dal verifier.

### Ablation B — SourceUnit Selector
FULL: selector deterministico top-5.
ABLATION: First-K top-5 e BM25 top-5. Stesso K, stesso documento, stesso
contratto Gemma, stesso validator.
Non si usa «no selector = documento intero»: altererebbe il token budget e
misurerebbe la lunghezza del prompt, non il contributo del ranking.

### Ablation C — Quote Validator
FULL: output Gemma → validator.
ABLATION: quote grezza considerata accettata **ai soli fini della valutazione**.
Il validator non viene spento nel runtime reale.
Metriche: fabricated quote acceptance, wrong SourceUnit, wrong document,
recomposed quote, unsupported intervention mention, invalid transport downstream.

### Ablation D — Narrative Verifier
FULL: narratore → verifier → PASS o fallback strutturato.
ABLATION: output del narratore presentato senza verifier, **offline**, mai a
utenti reali.
Metriche: unauthorized entity introduction, status escalation, polarity
inversion, invented recommendation, invented quote, critical omission, failed
narrative presented.

### Interpretazione attesa
L'ablation non deve mostrare che ogni rimozione «peggiora tutto», ma che ogni
componente controlla una **classe di fallimento distinta**:

| Componente | Classe di fallimento controllata |
|---|---|
| CaseContext Verifier + Gate | propagazione di input non valido |
| SourceUnit Selector | efficienza e pertinenza del routing dell'evidenza |
| Quote Validator | attribuzione non supportata |
| Narrative Verifier | drift del layer di presentazione |

Se un'ablation non aumenta alcuna classe di fallimento, il risultato è che su
questo corpus quel componente non è dimostrato necessario, e va riportato così.

---

## 9. Metriche e piano statistico

Definiti in `evaluation/final_protocol/metrics_registry.json`. In sintesi:

* **Regola dei conteggi a zero**: sempre `0 / N` con N esplicito.
* **Regola dei denominatori**: le metriche di retrieval sempre in coppia
  (20 complessivi, 9 positivi).
* **Proporzioni**: intervallo di Wilson 95%.
* **Ranking**: bootstrap paired, 10 000 ripetizioni, seed `20260809`.
* **Significatività**: nessun p-value con N < 30 per braccio; conteggi grezzi,
  effect size e CI.
* **Paired ovunque il disegno lo consenta**: baseline fra loro, GOLD vs SELECTOR,
  FULL vs ABLATION.
* **Token**: i token del provider si registrano solo se esposti; le stime
  deterministiche sul payload sono metriche separate e non si chiamano billing
  token.

**Nessuna soglia sul selector.** `HitRate@5 = 0.45` complessivo e `1.00` sui 9
casi positivi sono già stati osservati: fissare oggi un target sarebbe costruirlo
sul risultato. Le misure del selector si riportano come osservazioni.

### Randomness
Inventariata in `metrics_registry.json`. Il selector è dimostrato deterministico
(10 run ripetute, permutazioni di input, NFC/NFD, case folding, punteggiatura →
hash di ranking identici). Il provider LLM cloud **non garantisce determinismo**:
va dichiarato, non aggirato.

### Policy di run
1 run per caso sulla configurazione congelata. Reliability subsample: 3 run sui
primi 5 `case_id` in ordine lessicografico di ciascuna classe del testbed A —
regola definita ora, non elenco scelto dopo i risultati.

---

## 10. Matrici di risultato

### 10.1 Safety matrix (RQ3)

| Failure mode | FULL | Ablation | Componente bloccante |
|---|---|---|---|
| unverified CaseContext reaches retrieval | 0 / N | NO_CASE_VERIFIER | CaseContext Verifier + Gate |
| invalid quote accepted | 0 / N | NO_QUOTE_VALIDATOR | Quote Validator |
| wrong document accepted | 0 / N | NO_QUOTE_VALIDATOR | Quote Validator + provenance binding |
| wrong SourceUnit accepted | 0 / N | NO_QUOTE_VALIDATOR | Quote Validator |
| canonical status changed by LLM | 0 / N | — | contratto di stage |
| provenance changed by LLM | 0 / N | — | contratto di stage |
| negative-source polarity promoted | 0 / N | — | Source Polarity Gate |
| rejected quote presented as evidence | 0 / N | NO_QUOTE_VALIDATOR | dossier builder |
| failed narrative presented | 0 / N | NO_NARRATIVE_VERIFIER | Narrative Verifier |
| narrator modifies canonical dossier | 0 / N | NO_NARRATIVE_VERIFIER | proiezione deterministica |

Le celle sono da riempire con l'esecuzione. `0 / N` indica il formato richiesto,
non un risultato già acquisito.

### 10.2 Robustness matrix (RQ4)

Per ciascuna classe (COMPLETE, INCOMPLETE, AMBIGUOUS, OOD, CONTRADICTORY,
NEGATIVE, ADVERSARIAL): N, expected path, observed path, retrieval called,
document acquisition called, Gemma called, canonical dossier built, controlled
stop, unexpected exception, safety violation.

### 10.3 LIVE vs REPLAY

Da riportare come **ruoli operativi diversi**, mai come better/worse.

| Proprietà | LIVE | REPLAY |
|---|---|---|
| new document acquisition | sì | no |
| network allowed | sì (fonti autorizzate) | no |
| cache-first | sì | n/a |
| SourceUnit selector | sì, K=5 | no |
| frozen bundle | no | sì |
| historical reproducibility | no | sì |
| unseen documents | sì | no |
| scopo | generalizzazione operativa | riproducibilità |

---

## 11. Criteri di successo

Definiti in `evaluation/final_protocol/success_criteria.json`, **prima**
dell'esecuzione. Undici criteri HARD con target 0 (H-A … H-K), tutti con
denominatore obbligatorio. Nessun criterio arbitrario di accuratezza clinica,
perché non esiste un gold clinico appropriato.

### Divieti post-freeze
Dopo l'approvazione è vietato modificare: K, feature del selector, prompt,
regole del validator, lexicon narrativo, soglie dei gate, corpus, label,
definizioni di metrica. Un problema scoperto dopo il freeze o è un risultato/
limitazione, o invalida formalmente la run e richiede `protocol_version 1.1`.
Nessuna correzione silenziosa.

### Ablation escluse
Nuove embedding, reranker neurali, soglia `NO_RELEVANT_SOURCE_UNIT`, nuovi LLM,
nuovi prompt, OncoKB, GCA v3, KG alternativo.

---

## 12. Tassonomia dei fallimenti

Congelata in `evaluation/final_protocol/failure_taxonomy.json`, in quattro
gruppi: `EXPECTED_SELECTIVE_BEHAVIOR`, `ENVIRONMENTAL_LIMIT`, `SYSTEM_FAILURE`,
`ARCHITECTURAL_VIOLATION`.

`ABSTAIN`, `CONTROLLED_STOP`, `QUOTE_REJECTED`, `NARRATIVE_REJECTED` e
`GATE_WARNING` **non sono fallimenti**. `MODEL_TRANSPORT_FAILED` (ISS-012) è un
guasto del provider e va contato a parte: nel benchmark CaseContext ha impedito
a 9 casi su 35 di raggiungere il gate, e confonderlo con uno stop mancato
falserebbe RQ4.

---

## 13. Artefatti e identificatori di run

Output sotto `evaluation/final_evaluation/`, senza mai sovrascrivere artefatti
storici:

    protocol/  datasets/  rq1/  rq2/  rq3/  rq4/
    live_replay/  latency/  ablations/  tables/  figures/  raw/  logs/  final_report/

Ogni run finale registra: `evaluation_id`, `run_id`, `case_id`,
`protocol_version`, `runtime_commit`, `mode` (LIVE|REPLAY), `timestamp`,
`model/provider`, `selector_version`, `K`, `dataset_hash`.

---

## 14. Piano di tabelle e figure

| # | Tabella | Dati necessari |
|---|---|---|
| 1 | composizione del corpus finale | `dataset_manifest.json` |
| 2 | RQ1 representation fidelity | E1 + E2 |
| 3 | retrieval comparison First-K / BM25 / Selector | E3 |
| 4 | GOLD vs Selector downstream Gemma | E4 |
| 5 | end-to-end final evaluation | E5 |
| 6 | ablation safety matrix | E6 |
| 7 | robustness per classe | E5 |
| 8 | LIVE vs REPLAY | E7 + E8 |
| 9 | latency, cache hit vs miss | E9 |

| # | Figura | Dati necessari |
|---|---|---|
| 1 | architettura finale a 15 stage | nessun dato nuovo |
| 2 | Recall/HitRate comparison del selector | E3 |
| 3 | riduzione dei modi di fallimento per ablation | E6 |
| 4 | esiti di percorso per robustness | E5 |
| 5 | latenza per stage | E9 |

Le figure non vengono prodotte in questa fase.

---

## 15. Riproducibilità

    protocol_version      : mtb-graphrag-final-evaluation/1.0
    runtime_commit        : f52bbf5920c14324953be849e666bc84571957e9
    dataset_bundle_sha256 : vedi evaluation/final_protocol/dataset_hashes.json
    protocol_sha256       : vedi evaluation/final_protocol/protocol_hash.json

Nessun caso può essere aggiunto o rimosso dopo aver visto i risultati finali
senza invalidare il freeze.
