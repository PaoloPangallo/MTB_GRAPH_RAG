# Architettura dell’integrazione shadow

```text
qualified claim ──┐
claim provenance ─┼─> read-only dossier adapter ──> clinical_actionability
document support ─┘              │
                                 └─ assessment lookup by exact claim_id
```

Il layer riceve una claim, le fonti della claim, il supporto documentale, gli
assessment disponibili e un contesto V3 già materializzato. Copia i dati in
uscita e aggiunge soltanto il blocco ESCAT.

La risoluzione considera corrente un solo assessment con `claim_id` identico e
stato diverso da `SUPERSEDED`. Zero assessment produce `NOT_ASSESSED`; più
assessment correnti producono `CONFLICTING_EVIDENCE`; uno storico soltanto
superseded non diventa corrente.

Il layer non scrive JSONL, non aggiunge audit events e non promuove il ruleset.
