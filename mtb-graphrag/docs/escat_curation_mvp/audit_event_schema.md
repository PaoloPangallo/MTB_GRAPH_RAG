# EscatAssessmentEvent

Ogni riga di `assessment_events.jsonl` ? append-only e contiene:

```json
{
  "event_id": "EV-...",
  "assessment_id": "ESCAT-AS-...",
  "timestamp": "2026-08-02T00:00:00+00:00",
  "actor": "curator",
  "action": "FIELD_EDITED",
  "field": "biomarker",
  "previous_value": null,
  "new_value": "EGFR L858R",
  "reason": "manual review",
  "rationale": "manual review"
}
```

Azioni supportate: `DRAFT_CREATED`, `FIELD_PREFILLED`, `FIELD_EDITED`,
`CURATOR_SET`, `RATIONALE_SET`, `STATUS_CHANGED`, `SOURCE_ATTACHED`,
`PASSAGE_ATTACHED`, `RULE_SELECTED`, `ASSESSMENT_VALIDATED`,
`ASSESSMENT_REJECTED`, `ASSESSMENT_SUPERSEDED`.

`field` pu? essere nullo per eventi di assessment complessivi, ma `rationale`
resta obbligatoria per gli eventi prodotti dal workbench. Gli snapshot di
supersessione sono conservati in `workspace/assessment_versions/`.
