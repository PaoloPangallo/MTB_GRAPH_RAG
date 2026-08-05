# Prompt v2.0

Versione: `paper-context-enricher-prompt/2.0`. Tool:
`submit_paper_context_enrichment_v2`. Schema minimale, tutti i campi
stringa, nessun null, nessun oggetto annidato, nessun union type, nessun
`evidence_kind`:

```json
{
  "decision": "QUOTE | ABSTAIN",
  "source_unit_id": "string",
  "author_claim_quote": "string",
  "author_context_summary": "string",
  "abstention_reason": "string"
}
```

Nessun campo prodotto dal modello viene usato come identificatore:
`enrichment_id`, `case_id`, `candidate_id`, `paper_id`, `model`,
`prompt_version`, `transport_version`, hash, timestamp e lineage sono
tutti aggiunti localmente dopo la chiamata
(`paper_context_enricher_v2.py::call_enricher_v2`), mai richiesti a Gemma.

Il system prompt istruisce esplicitamente a non astenersi per: finding
negativo, resistenza, contraddizione col candidate, risultato incerto,
quote che non ripete ogni campo del CaseContext, summary che risulterebbe
vuoto. Il task prompt (incorporato nella richiesta utente, non un blocco
separato) esclude deliberatamente: status atteso, baseline, risultato del
validatore, se il caso è DIRECT/PARTIAL/CONTRADICTED, la citazione attesa.
