# Audit event

Ogni riga JSONL è un `EscatAssessmentEvent` append-only:

```json
{
  "event_id": "EV-...",
  "assessment_id": "ESCAT-AS-...",
  "timestamp": "...",
  "actor": "...",
  "action": "FIELD_EDITED",
  "field": "biomarker",
  "previous_value": null,
  "new_value": "EGFR L858R",
  "reason": "local source review"
}
```

Azioni supportate: `DRAFT_CREATED`, `FIELD_PREFILLED`, `FIELD_EDITED`,
`SOURCE_ATTACHED`, `PASSAGE_ATTACHED`, `RULE_SELECTED`,
`ASSESSMENT_VALIDATED`, `ASSESSMENT_REJECTED` e
`ASSESSMENT_SUPERSEDED`.
