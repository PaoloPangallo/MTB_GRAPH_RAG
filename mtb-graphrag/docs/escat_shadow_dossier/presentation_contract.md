# Contratto di presentazione

Il blocco contiene almeno:

```json
{
  "framework": "ESCAT",
  "framework_version": null,
  "status": "NOT_ASSESSED",
  "tier": null,
  "subtier": null,
  "origin": null,
  "ruleset_status": "RESEARCH_DRAFT",
  "assessment_id": null,
  "rule_ids": [],
  "candidate_rule_ids": [],
  "supporting_sources": [],
  "supporting_passages": [],
  "missing_requirements": [],
  "manual_review_required": true,
  "curator": null,
  "curated_at": null,
  "notes": []
}
```

Un eventuale stato interno DRAFT del modulo di curation viene presentato come INCOMPLETE, con nota esplicita DRAFT_PRESENTED_AS_INCOMPLETE; il contratto di presentazione non espone DRAFT come stato pubblico.

Lo stato è copiato dal record quando esiste; non è calcolato dal tier. Gli
assessment curati espongono tier/subtier soltanto quando `validate_assessment`
li considera formalmente validi. Con `RESEARCH_DRAFT` la revisione manuale
resta richiesta e il ruleset non diventa una validazione clinica.

`READY_FOR_REVIEW` può mostrare `candidate_rule_ids` forniti dal curatore, ma
non li seleziona l’adapter e non assegna tier.
