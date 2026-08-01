# V3 UI data flow

V3RunForm -> V3Request -> POST /api/v1/v3/retrieve -> V3RetrieveRequest
-> EvidenceRetrievalPipeline.run con qualified_claim_v3
-> native payload: query, all_results, gate_decisions, latency_ms
-> present_retrieval_outcome
-> legacy response fields + pipeline stages/gate summary/bucket summary/provenance summary/dossier summary
-> V3EvidenceView con Dossier, Pipeline, Evidenze, Provenienza e Dati tecnici

Gli stage senza una misura nativa hanno latency_ms: null. La pipeline view non ricostruisce eventi mancanti e non inserisce chiamate a planner, fonti live o LLM. La response additiva non modifica claim, bucket, gate, score, provenance o corpus.
