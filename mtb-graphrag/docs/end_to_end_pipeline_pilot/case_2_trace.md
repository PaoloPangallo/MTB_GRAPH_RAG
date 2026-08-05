# Caso 2 — THERAPY_DISCOVERY

**STAGE 1**: testo clinico su colorectal cancer con BRAF V600E, domanda di
scoperta ("which therapeutic options are associated..."), nessun farmaco
nominato.

**STAGE 2**: parser produce `target_intervention=null`,
`query_intent=THERAPY_DISCOVERY`, biomarker BRAF V600E con quote letterale.
Transport `FORCED_TOOL_VALID`.

**STAGE 3**: tutti i record essenziali `MATCH`; `target_intervention`
correttamente `MISSING_IN_TEXT` (mai popolato, mai una stringa wildcard).
`essential_fields_pass=True`.

**STAGE 4**: 1 associazione trovata: `GCA-0031c17c5ff5ae29ff221b1e` —
**ENCORAFENIB scoperto dal KG senza mai comparire nel testo clinico**.
Reason codes: DISEASE_COMPATIBLE, BIOMARKER_COMPATIBLE,
DISCOVERY_NO_INTERVENTION_FILTER.

**STAGE 5**: 2 paper selezionati: `EB-479f55c21cac935ef1313755` (primary,
FULLTEXT_LOCAL_CONTEXT_BUNDLE), `EB-278efe96eecccc226c82aa2d` (secondary,
ABSTRACT_BUNDLE).

**STAGE 6**: 2 chiamate Gemma — entrambe `INVALID_TOOL_ARGUMENTS`
(`EVIDENCE_KIND_INVALID`).

**STAGE 7**: entrambe `REJECTED_TRANSPORT`.

**STAGE 8**: `query_intent=THERAPY_DISCOVERY` -> `status=DISCOVERED`,
`gate_bucket=DISCOVERY_BUCKET`, `support_mask={..., intervention:DISCOVERED,
direction:NOT_APPLICABLE}` — nessuna promozione a claim positiva o
negativa, coerente con la natura esplorativa della discovery.

**STAGE 9**: dossier con un candidate therapy (ENCORAFENIB), status
`DISCOVERED`, nessun `author_context` (nessun arricchimento valido).
