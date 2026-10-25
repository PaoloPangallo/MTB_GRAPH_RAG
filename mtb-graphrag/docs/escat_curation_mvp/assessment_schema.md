# EscatAssessmentRecord

Campi principali:

`assessment_id`, `claim_id`, `framework`, `framework_version`,
`assessment_status`, `tier`, `subtier`, `biomarker`, `disease`, `intervention`,
`direction`, `tumour_context_relation`, `study_design`, `outcome_basis`,
`evidence_scope`, `assessment_origin`, `supporting_sources`,
`supporting_passages`, `rule_ids`, `reason_codes`, `missing_requirements`,
`rationale`, `curator`, `curated_at`, `created_at` e
`supersedes_assessment_id`.

Stati ammessi: `DRAFT`, `INCOMPLETE`, `READY_FOR_REVIEW`, `CURATED`,
`REJECTED`, `CONFLICTING_EVIDENCE`, `NOT_APPLICABLE`, `SUPERSEDED`.

La serializzazione ignora campi legacy estranei come `evidence_level`; non li
converte in tier ESCAT. Un tier richiede rule set, framework version, rule id,
fonte della regola, source di supporto distinta, requisiti, motivazione,
curator e timestamp. Un subtier richiede i requisiti specifici della regola.
In assenza del rule set ufficiale il tier resta nullo e `CURATED` ? rifiutato.
