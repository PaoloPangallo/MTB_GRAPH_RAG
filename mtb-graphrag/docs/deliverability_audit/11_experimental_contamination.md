# 11 — Contaminazione sperimentale

Dati: `evaluation/deliverability/experimental_contamination_audit.csv`,
`evaluation/deliverability/raw/H01_contamination.json`.

**Una contaminazione non è un bug.** Un bug fa comportare male il software; una
contaminazione fa *misurare male l'esperimento*. Le due cose sono elencate
separatamente, come richiesto dal §25.

## I quattro controlli critici sono superati

### ✅ CONT-15 — Nessuna self-comparison del materializzatore

Il rischio più serio per RQ1: se lo script che misura la fedeltà del
materializzatore usasse il materializzatore stesso per costruire il proprio
atteso, `precision = recall = 1.0` sarebbe una tautologia.

Verificato: `evaluation/rq1/kg_source.py` **legge l'export CSV grezzo** e **non
importa** `gca_v3.materialize` né alcun modulo di materializzazione. L'atteso è
costruito indipendentemente da ciò che misura.

`materialization_precision = 1.0` è quindi un risultato, non una tautologia.

### ✅ CONT-01 / CONT-02 — Nessun mock né fixture raggiungibile dal runtime

Scansione dei 51 moduli di `backend/research_pipeline` (esclusi i test) per
`unittest.mock`, `MagicMock`, `monkeypatch`, `FIXTURE`, `DUMMY_`, `FAKE_`:
**zero occorrenze**.

Gli artifact congelati usati in REPLAY **non sono mock**: sono risposte reali
del modello registrate al commit `6ee64c5`, con transport, quote,
`source_unit_id`, prompt version, token e latenza. Ogni stage che li usa dichiara
`artifact_origin = RECORDED_REAL_RUN`, e quel valore declassa la run a `HYBRID`.

### ✅ CONT-04 / CONT-09 — Nessun replay travestito da run, nessun fallback silenzioso

`execution_mode.classify_run_mode` è **asimmetrico per costruzione**: un solo
artifact registrato declassa una run LIVE a HYBRID, e nessuna combinazione
promuove REPLAY a LIVE. `HYBRID` non è nemmeno richiedibile. Verificato sulle run
reali: REPLAY riporta `execution_mode: REPLAY`, `fully_live: false`,
`llm_calls: 0`.

E il fallback silenzioso non è semplicemente assente — è stato **attivamente
rimosso**, con i commenti che lo documentano:

> «Non esiste più un `use_replay` dedotto dalla presenza di artefatti congelati
> per il caso: era il fallback silenzioso.»

### ✅ CONT-05 / CONT-06 / CONT-12 — Nessuna metrica hard-coded, nessuna riga duplicata

Cinque script rieseguiti, output riprodotto byte a byte salvo i timestamp.
Nessun file `.jsonl` sotto `evaluation/` contiene righe duplicate.

---

## ⛔ CONT-19 — La contaminazione che conta (P0)

**Le metriche RQ4 post-gate misurano un percorso diverso da quello che la claim
rivendica.**

`evaluation/run_runtime_v3_integration.py` importa e chiama
`backend.research_pipeline.casecontext.pipeline.run` — la catena deterministica —
**direttamente**. Non passa da `orchestrator.run_case`.

Il docstring di `casecontext/pipeline.py` spiega perché la catena è condivisa:

> «Serve sia all'orchestratore sia all'harness di valutazione, che devono
> eseguire **esattamente la stessa** catena: duplicarla renderebbe il benchmark
> una misura di un'altra pipeline.»

L'intenzione è corretta e la catena *è* la stessa. Ma la claim di RQ4 riguarda il
**runtime** («input non eleggibili vengono fermati prima di produrre retrieval»),
e attraverso il runtime lo stesso input produce un `ValueError` non gestito
(ISS-001). L'harness non poteva accorgersene: la giunzione orchestratore↔gate è
precisamente il tratto che non attraversa.

Non è disonestà: è un punto cieco strutturale nella strategia di misurazione.
La correzione è misurare RQ4 **attraverso `orchestrator.run_case`**, dopo aver
corretto ISS-001.

## ⚠️ CONT-11 — Denominatori (P1)

RQ1 e RQ2 usano **46 864** come denominatore. Ma il retrieval è ristretto alle
candidate con EvidenceBundle, e sono **16**.

Nessun artifact affianca al denominatore di popolazione quello end-to-end. Un
lettore che veda `candidates_with_pmid: 8230` può ragionevolmente concludere che
8 230 candidate siano documentalmente ancorabili; in realtà 16 possono
attraversare la pipeline, e 15 hanno un documento in cache.

Non è un numero sbagliato: è un numero senza il proprio contesto. Va affiancato,
in ogni tabella della tesi, dal denominatore end-to-end.

## ⚠️ CONT-14 — Verifica di coerenza interna, non contro un riferimento (P2)

`test_v3_runtime_admission.py` verifica `admission.py` contro il repository 3.0,
che è prodotto da `gca_v3/materialize.py`. Entrambi derivano dallo stesso export
del grafo. La verifica «0 violazioni su 46 142 candidate» è quindi una
**coerenza interna**, non un confronto con un riferimento indipendente.

Il riferimento esterno esiste ed è previsto:
`evaluation/gold/rq1_gca_v3_manual_review.csv`, 70 record stratificati. **Le
colonne del revisore sono vuote.** `13_runtime_switch_decision.md` lo dichiara
già come una delle tre condizioni per lo switch a v3.

Da presentare nella tesi come «fedeltà rispetto ai metadati della sorgente», non
«fedeltà semantica validata».

## ⚠️ CONT-16 — Tre assi di versionamento che condividono la stringa «v3» (P2)

| Nome | Significato |
|---|---|
| `backend/api/v3_presentation.py` | **V3 di prodotto** (pipeline agentica legacy) |
| `graph_candidate_repository/3.0` | **V3 del contratto GCA** |
| `legacy_runtime_repository = "1.4"` | la «Legacy V3» usa il repository 1.4 |

Ambiguità di nomenclatura, non di dati: nessun artifact è mescolato. Ma un
lettore della tesi o del repository può facilmente concludere che «il runtime V3»
usi «GCA v3», che è falso.

## ⚠️ CONT-17 — Artifact sperimentali non versionati (P2)

13 file untracked sotto `benchmarks/mtb_evidence/exploratory/manual_v3_cases/` e
`manual_v3_cases_product_hardening/` (input, output e summary di 4+ casi
manuali). Non entrano in alcuna metrica di questo audit, e **non possono entrare
in una metrica della tesi** finché restano fuori da git: nessun revisore potrebbe
verificarli.

## ⚠️ CONT-03 / CONT-08 / CONT-18 — Minori (P3)

- **Cache**: quattro moduli del runtime usano `lru_cache` a livello di modulo
  (`data_access` 2, `replay` 5, `kg_retrieval` 3, `repository_v3` 3). Sono cache
  di dataset congelati, motivate nei commenti («`candidates.jsonl` pesa 72,5 MB e
  rileggerlo a ogni run costava ~3 s») e invalidabili con `cache_clear()`. Non
  alterano i risultati; un test che cambi `RESEARCH_PIPELINE_DATA_ROOT` senza
  invalidare legge il dataset precedente.
- **Provenienza**: gli artifact dell'enricher congelato provengono dal commit
  `6ee64c5`, che vive in un worktree temporaneo su un branch diverso. I dati sono
  tracciati qui, ma la loro origine punta a un albero che può sparire.
- **Percorsi assoluti**: 7 artifact committati contengono
  `C:\Users\paolo\Desktop\...`.

## ✅ CONT-20 — Menzione d'onore

`evaluation/rq4_casecontext_robustness/aggregate_metrics.json` contiene:

```json
"endpoint_configuration": {
  "override_applied_by_harness": true,
  "override_mechanism": "RESEARCH_PIPELINE_LLM_BASE_URL (previsto da llm_config.base_url())",
  "base_url_used": "https://ollama.com",
  "runtime_default_base_url": "https://api.ollama.com",
  "runtime_default_status": "HTTP_405 su /v1/chat/completions — inutilizzabile",
  "prompt_modified": false,
  "runtime_code_modified": false
}
```

Un harness che registra nel proprio artifact di essere stato costretto a
sovrascrivere l'endpoint di default, e che il default era rotto, è divulgazione
esemplare. Il valore è oggi *stale* (il default è stato corretto a
`https://ollama.com`, verificato: `llm_config.base_url()` restituisce quel
valore), ma non è occultato.

## Sintesi

```
experimental_contamination_found = true
contaminazioni P0 = 1   (CONT-19 — metrica su percorso diverso dalla claim)
contaminazioni P1 = 1   (CONT-11 — denominatori senza contesto)
contaminazioni P2 = 3   (CONT-14, CONT-16, CONT-17)
contaminazioni P3 = 3   (CONT-03, CONT-08, CONT-18)
controlli critici superati = 4/4  (self-comparison, mock, replay-come-live, metriche hard-coded)
```
