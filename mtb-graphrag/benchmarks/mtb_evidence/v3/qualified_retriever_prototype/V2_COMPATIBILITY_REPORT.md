# V2 compatibility report

La parity è misurata soltanto sul contratto tecnico offline.

`v2_compatibility` e `native_only` condividono candidate generation, hard
constraint nativi e tie-break. I qualificatori V3 non influenzano nessuna delle
due modalità. Sul pilot congelato i candidate set coincidono per tutti e quattro
i casi; i dettagli per caso sono in `compatibility_metrics.json`.

La parity non viene dichiarata rispetto a una nuova esecuzione Neo4j: il V2
online può usare record e ordine del traversal non disponibili nel corpus
offline. La causa è esplicita e non viene mascherata forzando artificialmente
parity 1.0. Nessuna metrica clinica è inclusa.
