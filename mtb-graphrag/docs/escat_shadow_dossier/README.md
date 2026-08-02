# ESCAT shadow dossier layer

Questo modulo è un adapter offline e read-only per mostrare come un
`EscatAssessmentRecord` possa comparire nel dossier senza modificare la
qualificazione V3.

Il ruleset resta `RESEARCH_DRAFT`, `available=false` e non clinicamente
validato. L’adapter non assegna tier/subtier, non seleziona regole e non
modifica assessment, provenance, evidenze, bucket, score, gate o ordine.

## Struttura del dossier

Il blocco aggiuntivo è `clinical_actionability`. È separato da:

- `claim_relevance`;
- `provenance.claim_sources`;
- `document_support`;
- contesto di retrieval (`bucket`, `score`, `gate_trace`, `evidence`, `abstention`).

L’associazione usa esclusivamente `claim_id` esatto. Gene, variante, malattia,
farmaco, PMID e similarità testuale non sono chiavi di associazione.

## Preview


Il dossier sperimentale completo per i quattro casi esplorativi e disponibile in benchmarks/mtb_evidence/escat_shadow_dossier/data/shadow_dossiers.json; contiene solo un blocco aggiuntivo e non ricalcola i campi di contesto.

La preview è in `benchmarks/mtb_evidence/escat_shadow_dossier/data/preview_cases.json`.
Include i 15 draft pilota e casi espliciti per assessment assente,
`NOT_APPLICABLE`, superseded, conflitto e fixture curata.

Per rigenerarla:

```powershell
python -m benchmarks.mtb_evidence.escat_shadow_dossier.preview
```

Gli esempi curati sono sempre marcati `TEST_FIXTURE_ONLY` e
`NOT_A_CLINICAL_ESCAT_ASSESSMENT`.

## Confini

Il package non è importato dall’endpoint V3, dal frontend, dal runtime, dal
knowledge graph o dal repository ufficiale delle qualified claim. È un artefatto
di ricerca separato.
