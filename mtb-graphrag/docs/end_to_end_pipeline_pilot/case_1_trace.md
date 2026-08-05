# Caso 1 — THERAPY_EVALUATION, match forte

**STAGE 1**: testo clinico su colorectal cancer metastatico, KRAS G12D,
domanda di valutazione su panitumumab (vedi `case_definitions.py` per il
testo completo; non riprodotto qui per esteso).

**STAGE 2**: parser produce CaseContext con `disease`, `biomarker`
(gene=KRAS, alteration=G12D), `target_intervention=panitumumab`,
`query_intent=THERAPY_EVALUATION`, tutti con quote letterali. Transport
`FORCED_TOOL_VALID`.

**STAGE 3**: 6 record di verifica, tutti `MATCH` o `MISSING_IN_TEXT`
legittimo (previous_intervention assente dal testo). `essential_fields_pass=True`,
nessun warning.

**STAGE 4**: 1 associazione trovata: `GCA-008ae3aad1a64c118318ef79`
(DISEASE_COMPATIBLE, BIOMARKER_COMPATIBLE, INTERVENTION_COMPATIBLE).

**STAGE 5**: 1 paper selezionato: `EB-b4c48ba003913f278ff182a6`
(ABSTRACT_BUNDLE, unico documento disponibile per questa candidate).

**STAGE 6**: 1 chiamata Gemma — trasporto `INVALID_TOOL_ARGUMENTS`
(`EVIDENCE_KIND_INVALID`): il modello ha restituito un valore fuori enum
per `evidence_kind`.

**STAGE 7**: validazione `REJECTED_TRANSPORT` (conseguenza diretta del
fallimento di trasporto in Stage 6).

**STAGE 8**: nessun arricchimento validato disponibile ->
`support_mask={disease:SUPPORTED, biomarker:SUPPORTED,
intervention:SUPPORTED, direction:NO_DOCUMENT_SIGNAL}`, `status=AMBIGUOUS`,
`gate_bucket=WARNING_BUCKET`, warning `NO_VALIDATED_ENRICHMENT_AVAILABLE`.

**STAGE 9**: dossier prodotto con un candidate therapy (PANITUMUMAB),
sezione `author_context` vuota (nessun arricchimento validato), status
`AMBIGUOUS` — nessuna promozione impropria nonostante il match strutturale
forte.
