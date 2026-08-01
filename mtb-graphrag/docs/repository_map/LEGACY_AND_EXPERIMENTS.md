# LEGACY_AND_EXPERIMENTS

| Area | Funzione storica | Uso dimostrato | Stato |
|---|---|---|---|
| backend/pipeline/graph.py e agents/ | LangGraph, planner/agenti | route legacy/confronto e campagne | LEGACY_BUT_REQUIRED |
| backend/pipeline/control/ | piano fisso/agentico, ledger, replay, verificatori | confronto e run verificabili | LEGACY_BUT_REQUIRED |
| backend/pipeline/llm/ | Ollama/Gemma, prompt e rendering | route legacy e campagne LLM | LEGACY_REFERENCE_ONLY |
| frontend componenti non V3 | report, judge, comparison, input storico | App.tsx e test legacy | LEGACY_BUT_REQUIRED |
| backend/evaluation/ | benchmark GraphRAG/zero-shot/ablation | CLI e report storici | LEGACY_REFERENCE_ONLY |
| experiments/reproducibility/ | sweep, baseline, rumore, router, multi-answer | CLI tesi | ARCHIVE_CANDIDATE per singoli script |

## Ufficiale ed esplorativo

- benchmarks/mtb_evidence/final_experiment/ e gold/manifest sono ufficiali:
  citati ma non letti o modificati.
- benchmarks/mtb_evidence/v3/ mescola contratti congelati, readiness, audit e
  risultati; usare manifest e protocollo.
- benchmarks/mtb_evidence/exploratory/ contiene run manuali e output, non
  fonte del runtime.
- experiments/thesis_alignment/ contiene casi di studio e
  run_case_study.py, invocabile manualmente.

## Renderer e agenti

Il percorso agentico è strategia/planner → strumenti allow-listed →
EventLedger → replay/canonical view → rendering → verifier → dossier. Questi
file sono rilevanti per confronti e tesi, ma non appartengono alla traccia V3
endpoint → UI.

ARCHIVE_CANDIDATE significa solo che non è emerso uso corrente; non autorizza
eliminazione o spostamento.

## Gruppi di script simili

| Gruppo | File rappresentativi | Differenza | Corrente/sperimentale | Certezza |
|---|---|---|---|---|
| Builder corpus | evaluation/scripts/promote_qualified_claim_corpus_1_4.py, regenerate_qualification_corpus.py, rebuild_qualification_views.py | promozione versionata, rigenerazione completa, ricostruzione view | promozione 1.4 è la corrente congelata; gli altri sono tooling di manutenzione | alta |
| Validator | scripts/validate_v3_schemas.py, evaluation/run_repository_history_validation.py, evaluation/run_source_cache_validation.py, evaluation/scripts/verify_source_locators.py | schema locale, storia repository, cache esterna, locator | validator locali/reference; non modificano V3 runtime | alta |
| Runner retrieval/benchmark | evaluation/scripts/run_qualified_retriever_prototype.py, evaluation/scripts/run_pilot_evaluation.py, backend/evaluation/run_benchmark.py | prototipo V3, pilot, benchmark GraphRAG storico | prototype/pilot sperimentali; run_benchmark legacy | alta |
| Scorer/report | backend/evaluation/compute_metrics.py, calculate_objective_metrics_three_way.py, compare_results.py, reevaluate_reports.py | metriche, obiettivi, confronto, ricalcolo report | esperimenti/benchmark | media |
| Debug/report locali | scratch_*.py, report generator e output manuali | analisi ad hoc e output non contrattuali | apparentemente obsoleti finché non collegati a una campagna | media |

Non è stata eseguita una consolidazione: questi gruppi sono solo una mappa
per una futura pulizia.
