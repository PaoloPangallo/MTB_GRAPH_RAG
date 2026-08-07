# 01 — Perimetro delle claim

Ricostruito **prima** dei test, come richiesto dal §1, per non misurare
proprietà che il progetto non rivendica.

## Il runtime canonico

```
POST /api/v1/research/pipeline/runs
  → orchestrator.run_case
  → retrieval/kg_retrieval.py  →  graph_candidate_repository/2.0
```

`GRAPH_CANDIDATE_REPOSITORY_VERSION` non è stato modificato dal fix sprint.
Verificato: `graph_candidate_runtime_version = "2.0"`, `gca_v3_runtime = false`.

## NON sono requisiti di deliverability runtime

Il §1 le esclude esplicitamente, e questo audit non le ha verificate come tali:

- preservazione completa delle alterazioni composte;
- AST delle alterazioni;
- preservazione completa dei regimi multi-componente;
- runtime su GCA v3.

Restano sostenibili **solo** come risultati sperimentali / shadow, e gli
artifact le dimostrano in quella sede (`evaluation/gca_v3/`,
`evaluation/runtime_v3_integration/`).

**Conseguenza per la tesi**: non si può scrivere che il runtime preserva la
semantica delle alterazioni composte o dei regimi. `kg_retrieval._match_candidate`
continua ad accettare `A AND B` per un caso che menziona solo `A`. È un limite
noto della v2, fuori perimetro, e va dichiarato.

## Proprietà runtime obbligatorie — verificate in questo audit

| Proprietà | Esito |
|---|:-:|
| selective routing | ✅ |
| source polarity safety | ✅ |
| candidate / document separation | ✅ |
| document grounding | ✅ |
| SourceUnit grounding | ✅ |
| QUOTE \| ABSTAIN | ✅ |
| quote validation | ✅ |
| canonical status deterministico | ✅ |
| separazione LLM / core | ✅ |
| dossier canonico | ✅ |
| presentazione coerente con validation status | ✅ |
| LIVE / REPLAY distinction | ✅ |

Dodici su dodici. Il dettaglio è in `03_runtime_invariants.md`.

## RQ5

`PLANNED`. `oncokb_called = false`. Il §17 lo esclude dai requisiti di freeze
purché resti dichiarato pilot/future work: lo è.
