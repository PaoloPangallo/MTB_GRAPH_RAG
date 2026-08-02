# EscatAssessmentRecord

Campi principali:

`assessment_id`, `claim_id`, `framework`, `framework_version`,
`assessment_status`, `tier`, `subtier`, `biomarker`, `disease`, `intervention`,
`direction`, `tumour_context_relation`, `study_design`, `outcome_basis`,
`evidence_scope`, `assessment_origin`, `supporting_sources`,
`supporting_passages`, `rule_ids`, `reason_codes`, `missing_requirements`,
`rationale`, `curator`, `curated_at`, `created_at` e
`supersedes_assessment_id`.

Gli stati ammessi sono `DRAFT`, `INCOMPLETE`, `READY_FOR_REVIEW`, `CURATED`,
`REJECTED`, `CONFLICTING_EVIDENCE`, `NOT_APPLICABLE` e `SUPERSEDED`.

Un tier è ammesso soltanto in presenza di rule set ufficiale disponibile,
versione, rule id, fonte della regola, source di supporto e audit curatoriale.
Un subtier richiede anche i requisiti specifici della regola.
