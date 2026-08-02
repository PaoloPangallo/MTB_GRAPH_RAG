# ESCAT curation MVP offline

Questo ? un workbench sperimentale, locale e separato dal runtime V3. Crea
bozze per la revisione umana, non assegna automaticamente tier o subtier e non
modifica qualified claim, gate, score, bucket, Knowledge Graph o API.

## Stato del framework

`OFFICIAL_RULESET_NOT_AVAILABLE`. Nei percorsi locali espliciti verificati
(`docs/references/`, `references/`, `literature/`, `papers/`) non ? presente
una fonte normativa ESCAT versionata e verificabile. Nessuna regola ESCAT
ufficiale ? stata codificata.

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

I dati generati sono sotto `benchmarks/mtb_evidence/escat_curation_mvp/` e
non sono artefatti ufficiali.
