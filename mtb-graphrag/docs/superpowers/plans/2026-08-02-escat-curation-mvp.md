# ESCAT Curation MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** costruire un workbench offline per draft ESCAT manuali, validazione formale e audit trail senza assegnazione automatica di tier.

**Architecture:** un package sperimentale separato in benchmarks/mtb_evidence/escat_curation_mvp contiene modelli, precompilazione, validazione, JSON/JSONL append-only e CLI. I draft sono derivati in sola lettura dalle 15 claim parzialmente assegnabili e non scrivono repository o runtime V3.

**Tech Stack:** Python standard library, dataclass, JSON/JSONL/CSV, pytest.

## Global Constraints

- OFFICIAL_RULESET_NOT_AVAILABLE impedisce assessment CURATED con tier.
- Nessun mapping evidence_level A/B/C/D verso ESCAT.
- Nessun LLM, PMID-only, legacy tier o keyword disease può assegnare tier.
- EscatAssessmentRecord resta separato dalla qualified claim.
- Nessuna modifica a runtime, frontend, KG, repository, gate, score, bucket o ordine V3.

### Task 1: contratti e test rossi

**Files:**
- Create: benchmarks/mtb_evidence/escat_curation_mvp/tests/test_models.py
- Create: benchmarks/mtb_evidence/escat_curation_mvp/tests/test_validation.py

- [ ] Scrivere test per stati, origini, framework non disponibile, tier nullo, subtier incompleto e separazione della source dal passage.
- [ ] Eseguire pytest e verificare il fallimento perché il package non esiste ancora.

### Task 2: modelli e validatore

**Files:**
- Create: benchmarks/mtb_evidence/escat_curation_mvp/models.py
- Create: benchmarks/mtb_evidence/escat_curation_mvp/validation.py

- [ ] Implementare i cinque modelli richiesti con serializzazione JSON.
- [ ] Implementare validazione che blocchi tier senza ruleset versionato, rule_id, fonte, source, motivazione, curator e timestamp.
- [ ] Eseguire i test e verificare il passaggio.

### Task 3: precompilazione e audit trail

**Files:**
- Create: benchmarks/mtb_evidence/escat_curation_mvp/prefill.py
- Create: benchmarks/mtb_evidence/escat_curation_mvp/audit.py
- Create: benchmarks/mtb_evidence/escat_curation_mvp/io.py
- Create: benchmarks/mtb_evidence/escat_curation_mvp/tests/test_audit.py

- [ ] Leggere claim, parent, source unit e provenance senza scrivere gli input.
- [ ] Conservare origine e livello per ogni valore precompilato.
- [ ] Implementare eventi append-only e supersedes senza sovrascrittura.
- [ ] Eseguire test di audit e preservazione degli assessment precedenti.

### Task 4: CLI offline e fixture dei 15 draft

**Files:**
- Create: benchmarks/mtb_evidence/escat_curation_mvp/cli.py
- Create: benchmarks/mtb_evidence/escat_curation_mvp/pilot.py
- Create: benchmarks/mtb_evidence/escat_curation_mvp/data/pilot_drafts.jsonl
- Create: benchmarks/mtb_evidence/escat_curation_mvp/data/pilot_missing_requirements.csv
- Create: benchmarks/mtb_evidence/escat_curation_mvp/data/pilot_data_availability.csv

- [ ] Implementare list-claims, show-claim, create-draft, show-missing-fields, attach-source, attach-passage, select-rule, validate-assessment, export-assessment e show-history.
- [ ] Generare esattamente 15 draft parzialmente assegnabili, senza tier/subtier.
- [ ] Testare CLI con directory temporanea e nessun contatto live.

### Task 5: documentazione e verifica finale

**Files:**
- Create: docs/escat_curation_mvp/README.md
- Create: docs/escat_curation_mvp/architecture.md
- Create: docs/escat_curation_mvp/curation_workflow.md
- Create: docs/escat_curation_mvp/assessment_schema.md
- Create: docs/escat_curation_mvp/audit_event_schema.md
- Create: docs/escat_curation_mvp/official_ruleset_requirements.md
- Create: docs/escat_curation_mvp/legacy_exclusion_rules.md
- Create: docs/escat_curation_mvp/pilot_drafts_report.md
- Create: docs/escat_curation_mvp/future_runtime_integration.md
- Create: docs/escat_curation_mvp/escat_curation_summary.json

- [ ] Documentare fonte ufficiale assente, stato framework e integrazione futura.
- [ ] Eseguire pytest, validazione JSON/JSONL/CSV e diff di immutabilità dal commit 6cd4cd4.
- [ ] Stagiare solo package, fixture, documentazione e piano collegato.
- [ ] Creare il commit feat: add an auditable ESCAT curation MVP.
