# Qualified retriever prototype smoke report

Il benchmark è tecnico, offline e descrittivo. Non usa terapie attese, clinical
gold, applicabilità finale o metriche cliniche per scegliere i pesi.

## Snapshot

- corpus: `qualification_corpus/2.0`
- fingerprint: `99a1a575a813676bb3d2658a3ab103cf396755f4b0cdbd9a8c26f09ea6c77ffd`
- frozen KG: `ffc97bc7c660f19478c33d28d1599b70e442525f0fae34b512e5efbf0796a9ae`
- scoring config: `ddbfe3cec5d79f0f321b6a853938aa074e55f9ab77149fc73f2ce17224908c00`
- query pilot: 4
- modalità: `v2_compatibility`, `native_only`, `qualified_soft`

## Risultato tecnico

`qualified_soft` conserva il link `ES-V2-evidence-100003` come audit-only,
mantiene evidenza negativa come negativa, separa contesto clinico/preclinico e
non usa qualificatori prototipo per escludere. Il caso RMI2 produce zero
candidati senza ampliare la ricerca fuori dallo snapshot.

I conteggi completi, i warning e gli hash dei risultati sono in
`prototype_metrics.json`; le singole decisioni e le esclusioni native sono in
`retrieval_traces.jsonl`.

## Limiti

La modalità V2 usa la rappresentazione offline congelata. Non esegue Neo4j e
non può promettere identità d'ordine con traversal che dipendano da dettagli
non serializzati. Questo smoke run non costituisce il confronto sperimentale
V2/V3-A e non calcola qualità clinica.
