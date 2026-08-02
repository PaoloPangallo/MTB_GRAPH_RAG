# ESCAT curation MVP offline

Questo ? un workbench sperimentale, locale e separato dal runtime V3. Crea
bozze per la revisione umana, non assegna automaticamente tier o subtier e non
modifica qualified claim, gate, score, bucket, Knowledge Graph o API.

## Stato del framework

RESEARCH_DRAFT. La fonte locale Mateo.pdf e stata verificata e formalizzata
in un ruleset versionato di ricerca. Il ruleset non e clinicamente validato e
non puo rendere CURATED alcun assessment: la promozione a ruleset clinico
richiederebbe revisione indipendente e approvazione esplicita.

## Risultato reale del pilota

- 15 draft, corrispondenti alle 15 claim `PARTIALLY_ASSIGNABLE`;
- 15 claim terapeutiche e 0 claim diagnostiche;
- 15 draft `INCOMPLETE`;
- 15 `tier=null`, 15 `subtier=null`;
- 0 draft `NOT_APPLICABLE`;
- eventuali claim diagnostiche sono escluse dal campione, non trasformate in draft;
- nessun mapping da `evidence_level`, PMID, legacy o LLM.

## CLI offline

Tutti i comandi leggono lo stato corrente e scrivono un evento append-only per
le operazioni di modifica o validazione:

```text
list-claims
show-claim <claim_id>
create-draft <claim_id>
show-draft <assessment_id>
show-missing-fields <assessment_id>
edit-field <assessment_id> <field> <value> [--actor NAME]
set-curator <assessment_id> <curator> [--actor NAME]
set-rationale <assessment_id> <rationale> [--actor NAME]
set-status <assessment_id> <STATUS> [--ruleset PATH]
attach-source <assessment_id> <JSON_OR_SOURCE_ID> [--actor NAME]
attach-passage <assessment_id> <JSON_OR_TEXT> [--actor NAME]
select-rule <assessment_id> <rule_id> --ruleset PATH [--actor NAME]
validate-assessment <assessment_id> [--ruleset PATH]
reject-assessment <assessment_id> <rationale> [--actor NAME]
supersede-assessment <assessment_id> --new-assessment-id <id> [--actor NAME]
export-assessment <assessment_id>
export-dossier <assessment_id>
show-history <assessment_id>
```

Esempio:

```powershell
python -m benchmarks.mtb_evidence.escat_curation_mvp.cli create-draft <claim_id>
python -m benchmarks.mtb_evidence.escat_curation_mvp.cli show-history <assessment_id>
```

Il ruleset di ricerca ? sotto
`benchmarks/mtb_evidence/escat_curation_mvp/rulesets/ESCAT_2018_MATEO_RESEARCH_DRAFT_v1/`.
Il confronto con i 15 draft ? read-only; nessuna regola ? selezionata e nessun
tier/subtier ? assegnato. Tutti gli artefatti restano separati dal runtime e
dagli artefatti clinicamente ufficiali.
