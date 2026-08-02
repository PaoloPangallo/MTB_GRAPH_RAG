# V3 ontology shadow MVP

Questo è un esperimento read-only eseguito su 148 claim attive di `qualified_claim_repository/1.4`. Il modulo vive sotto `benchmarks/mtb_evidence/ontology_shadow_mvp/` e non è importato dal runtime V3.

La modalità è `ONTOLOGY_SHADOW_MODE`: normalizza e confronta in parallelo il contesto del parent locale con i valori della claim, producendo tipo di match, distanza, percorso e spiegazione. Non decide ammissione, provenance, bucket, score, ranking o applicabilità clinica.

Input esclusivamente locali:

- alias e gerarchia disease verificati nel repository;
- alias farmacologici verificati localmente;
- contratto locale di canonicalizzazione degli interventi;
- due record diagnostici locali;
- `graph_evidence_parents.jsonl` e claim attive della repository V3.

Non sono stati usati servizi ontologici esterni, PubMed live o LLM. I valori `canonical_id` restano null quando gli asset locali non forniscono un identificatore canonico esplicito; una `registry_key` locale non viene presentata come CURIE.

Esecuzione:

```text
python -m benchmarks.mtb_evidence.ontology_shadow_mvp.run_shadow
```

Il comando scrive solo gli artefatti in questa directory.
