# Architecture

```text
frozen V3 result ───────────────┐
qualified claim provenance ─────┤
PMID/document support ──────────┤
ontology shadow evidence ──────┼─> canonical dossier (read-only)
CompanionDiagnostic context ────┤
ESCAT shadow assessment ────────┘
```

CASE RELEVANCE, PROVENANCE, DOCUMENT SUPPORT, ONTOLOGY ALIGNMENT,
DIAGNOSTIC CONTEXT e CLINICAL ACTIONABILITY sono moduli distinti. Nessuno
modifica retroattivamente il risultato di un altro modulo.

Il builder copia il core e calcola hash prima/dopo. Un mismatch o un core
alterato è un errore di integrità, non una ragione per ricalcolare bucket o
score.
