# Modello EscatAssessmentRecord

Schema concettuale separato dalle qualified claim:

    {
      "assessment_id": "...",
      "claim_id": "...",
      "framework": "ESCAT",
      "framework_version": null,
      "assessment_status": "UNASSIGNABLE",
      "tier": null,
      "subtier": null,
      "biomarker": null,
      "disease": null,
      "intervention": null,
      "tumour_context_relation": null,
      "study_design": null,
      "outcome_basis": [],
      "evidence_scope": null,
      "assessment_origin": "UNKNOWN",
      "supporting_sources": [],
      "supporting_passages": [],
      "reason_codes": ["MISSING_FRAMEWORK_RULE"],
      "missing_requirements": [],
      "timestamp": null,
      "assessor": null
    }

## Stati

- EXPLICITLY_ANNOTATED: il record dichiara framework e valore.
- ASSIGNABLE: tutti i requisiti e le regole versionate sono disponibili.
- PARTIALLY_ASSIGNABLE: dati utili ma requisito o regola mancante.
- UNASSIGNABLE: dati insufficienti o framework non verificato.
- CONFLICTING_EVIDENCE: fonti o record incompatibili.
- NOT_APPLICABLE: claim non valutabile come actionability terapeutica, ad
  esempio le due claim diagnostiche attive.

Quando lo stato è UNASSIGNABLE, tier e subtier devono essere null.

## Origini

EXPLICIT_SOURCE, LEGACY_DERIVED, RULE_DERIVED, MANUAL_REVIEW e UNKNOWN sono
origini distinte. Il risultato legacy non può essere promosso a
EXPLICIT_SOURCE.
