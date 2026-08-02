# ESCAT curation MVP offline

Questo è un workbench sperimentale, locale e separato dal runtime V3. Crea
draft per la revisione umana, non assegna tier o subtier automaticamente e
non modifica qualified claim, gate, score, bucket, Knowledge Graph o API.

## Stato del framework

`OFFICIAL_RULESET_NOT_AVAILABLE`. Nei percorsi locali espliciti verificati
(`docs/references/`, `references/`, `literature/`, `papers/`) non è presente
una fonte normativa ESCAT versionata e verificabile. Il riferimento in
`docs/V3_POSITIONING.md` è soltanto una citazione da verificare, non un rule
set utilizzabile.

## Risultato del pilota

- 15 draft generati dalle 15 claim `PARTIALLY_ASSIGNABLE` della feasibility;
- 15 draft `INCOMPLETE`, senza tier e subtier;
- 2 claim diagnostiche disponibili come `NOT_APPLICABLE` per actionability
  terapeutica;
- nessun mapping da `evidence_level`, PMID, legacy o LLM;
- ogni testo locale eventualmente allegato resta distinto dalla source.

## Uso

```text
python -m benchmarks.mtb_evidence.escat_curation_mvp.cli list-claims
python -m benchmarks.mtb_evidence.escat_curation_mvp.cli seed-pilot
python -m benchmarks.mtb_evidence.escat_curation_mvp.cli create-draft <claim_id>
python -m benchmarks.mtb_evidence.escat_curation_mvp.cli show-missing-fields <assessment_id>
python -m benchmarks.mtb_evidence.escat_curation_mvp.cli attach-source <assessment_id> PMID:...
python -m benchmarks.mtb_evidence.escat_curation_mvp.cli attach-passage <assessment_id> '{"text":"...","locator":"ABSTRACT"}'
python -m benchmarks.mtb_evidence.escat_curation_mvp.cli validate-assessment <assessment_id>
python -m benchmarks.mtb_evidence.escat_curation_mvp.cli export-assessment <assessment_id>
python -m benchmarks.mtb_evidence.escat_curation_mvp.cli show-history <assessment_id>
```

I dati generati sono sotto `benchmarks/mtb_evidence/escat_curation_mvp/` e
non sono artefatti ufficiali.
