# V3 pipeline observability: mappa tecnica

## Flusso reale

| Livello | File / simbolo | Responsabilita | Modifica prevista |
|---|---|---|---|
| Form V3 | frontend/src/components/V3RunForm.tsx, submit | Raccoglie gene, alterazione, biomarcatore, malattia, interventi, direction, policy e limit | Nuovo form esplicito; nessun OncoKB live |
| Client | frontend/src/App.tsx, handleV3Run | POST a /api/v1/v3/retrieve | Invia il payload completo V3 |
| Request model | backend/api/v3_schemas.py, V3RetrieveRequest | Valida e converte il payload in query V3 | Nessuna modifica alla semantica |
| Pipeline | backend/pipeline/evidence/retrieval/pipeline.py, EvidenceRetrievalPipeline.run | Seleziona qualified_claim_v3, carica repository, applica gate e ranking | Nessuna modifica al motore |
| Adapter | backend/api/v3_presentation.py, present_retrieval_outcome | Separa claim e record tecnici e rende reason/provenance leggibili | Aggiunge proiezione read-only pipeline |
| Response model | backend/api/v3_schemas.py, V3RetrieveResponse | Serializza response legacy + osservabilita | Campo additivo e retrocompatibile |
| Vista | frontend/src/components/V3EvidenceView.tsx | Mostra dossier, pipeline, evidenze, lineage e dati tecnici | Console coordinata a tab |

## Verifiche diagnostiche

- Il form precedente inviava interventions vuoto, direction vuota, malattia Lung Adenocarcinoma e limite 50.
- Le run manuali EGFR usavano NSCLC, osimertinib, sensitivity e limite 20.
- Il form precedente chiamava comunque /api/v1/v3/retrieve; la differenza dei conteggi era il payload, non un endpoint diverso.
- Il frontend leggeva item.score.total, che coincide con il campo nativo. Il valore 0.0 del form e reale: i risultati hanno structural_score_eligible=false.
- I caratteri ? erano separatori testuali JSX, non dati del corpus.
- Il backend V3 diretto costruisce QualifiedClaimQuery e conserva original, normalized e gate_query; non istanzia il vecchio planner e non usa un renderer LLM.
- Le latenze di fase sono mostrate solo quando presenti nel payload nativo; gli altri stage espongono null.
