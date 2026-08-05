# Caso 3 — PARTIAL, contesto incompleto

**STAGE 1**: testo clinico su colorectal cancer con instabilità
microsatellitare (grado non specificato), precedente chemioterapia
fluoropirimidinica, domanda di valutazione su nivolumab.

**STAGE 2**: parser produce `gene="microsatellite"` (non un vero simbolo
genico) con `normalized_value="microsatellite instability (MSI)"`,
`previous_interventions` popolato, `target_intervention=nivolumab`,
`uncertainties=["specific degree of MSI not yet reported"]`. Transport
`FORCED_TOOL_VALID`.

**STAGE 3**: tutti i record `MATCH`. `essential_fields_pass=True`.

**STAGE 4**: 1 associazione trovata: `GCA-02861e174359dd9f4f53df9b`
(**questo match ha richiesto la correzione del bug di retrieval** che
inizialmente considerava solo `gene`, perdendo l'abbreviazione "MSI"
presente solo in `normalized_value` — vedi `retrieval_trace.md`).

**STAGE 5**: 2 paper selezionati, entrambi FULLTEXT_LOCAL_CONTEXT_BUNDLE:
`EB-883392431572b406505185cd` (primary), `EB-bd6ce2f5db3fb40af814743e`
(secondary — quest'ultimo è il documento baseline CONTRADICTED per questa
stessa candidate in un'altra associazione candidate-documento, selezionato
qui puramente per tipo di bundle, non per l'etichetta nota).

**STAGE 6**: 2 chiamate Gemma, entrambe `FORCED_TOOL_VALID`. **Entrambe
`abstain=true`**: la prima perché il testo discute solo il protocollo
statistico dello studio senza riportarne i risultati; la seconda perché il
testo discute "immune checkpoint blockade"/"checkpoint inhibition" in
generale senza mai nominare "nivolumab".

**STAGE 7**: entrambe `ENRICHMENT_ABSTAINED`.

**STAGE 8**: nessun arricchimento validato -> `status=AMBIGUOUS`,
`gate_bucket=WARNING_BUCKET`, warning `NO_VALIDATED_ENRICHMENT_AVAILABLE`.

**STAGE 9**: dossier con un candidate therapy (NIVOLUMAB), status
`AMBIGUOUS` — nessuna promozione a PARTIAL/DIRECT nonostante il match
strutturale, coerente con l'obiettivo del caso ("assenza di promozione
impropria").
