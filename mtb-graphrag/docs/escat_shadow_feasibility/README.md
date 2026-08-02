# ESCAT shadow feasibility

Pilota separato, read-only, sul branch research/v3-escat-shadow-feasibility.
La base è il commit 4b75145, che contiene il commit audit ESCAT:
docs: audit ESCAT availability in active V3 data.

## Esito

Le 148 qualified claim V3 contengono biomarcatore, malattia e direzione come
campi strutturati; 146 contengono un intervento e 2 sono diagnostiche. La
provenance completa è invece disponibile solo per una minoranza:

- 17 claim hanno fonte, identificatore, locator e testo locale registrato;
- 15 claim terapeutiche sono solo parzialmente assegnabili;
- 131 claim terapeutiche sono UNASSIGNABLE;
- 2 claim diagnostiche sono NOT_APPLICABLE per un assessment di actionability
  terapeutica;
- 0 claim ricevono un tier ESCAT nel pilota.

La definizione ufficiale ESCAT non è presente localmente in forma verificata.
V3_POSITIONING.md cita Mateo et al. come riferimento da verificare, ma dichiara
che definizioni, DOI e fonte primaria sono ancora da controllare. Il pilota
esegue quindi una matrice di assegnabilità e non assegna tier.

## Principi

Case relevance, evidence provenance, document support e clinical actionability
restano assi separati. Nessun bucket V3 viene mappato a ESCAT e nessun valore
evidence_level A/B/C/D viene convertito in un tier ESCAT.

Il valore legacy escat_tier è riportato separatamente e non è ground truth.

## Documenti

- [Audit legacy](legacy_escat_audit.md)
- [Campi richiesti](escat_required_fields.md)
- [Modello assessment](escat_assessment_model.md)
- [Modello regole](escat_rule_model.md)
- [Disponibilità delle claim](claim_data_availability.csv)
- [Claim pilota](pilot_claims.csv)
- [Confronto legacy/shadow](legacy_shadow_comparison.csv)
- [Report di fattibilità](escat_feasibility_report.md)
- [Integrazione futura](recommended_runtime_integration.md)
