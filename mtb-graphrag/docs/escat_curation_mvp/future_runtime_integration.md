# Integrazione futura nel dossier

L’adapter read-only può produrre:

```json
{
  "clinical_actionability": {
    "framework": "ESCAT",
    "status": "INCOMPLETE",
    "tier": null,
    "subtier": null,
    "origin": "MANUAL_CURATION",
    "framework_version": null,
    "missing_requirements": [],
    "sources": [],
    "curator": null,
    "curated_at": null
  }
}
```

La visualizzazione futura deve distinguere `CURATED`, `INCOMPLETE`,
`NOT_APPLICABLE`, `CONFLICTING_EVIDENCE` e assenza di assessment, mostrando
origine, regola, fonte e campi mancanti. ESCAT resta una sezione separata da
case relevance, provenance e document support: non può modificare bucket,
score, gate o ordine dei risultati.

Prima di qualunque collegamento servono un rule set ufficiale locale,
curation umana, test di regressione e un contratto di propagazione che non
promuova automaticamente alcuna fonte.
