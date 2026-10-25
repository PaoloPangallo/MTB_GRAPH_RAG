# Caso 4 — CONTRADICTED/resistance

**STAGE 1**: testo clinico su lung squamous cell carcinoma con FGFR1
amplification, domanda di valutazione su infigratinib, status atteso mai
rivelato al modello.

**STAGE 2**: parser produce `disease`, `biomarker` (gene=FGFR1,
alteration=amplification), `target_intervention=infigratinib`,
`query_intent=THERAPY_EVALUATION`, tutti con quote letterali. Transport
`FORCED_TOOL_VALID`.

**STAGE 3**: tutti i record `MATCH`. `essential_fields_pass=True`.

**STAGE 4**: 1 associazione trovata: `GCA-0062c0237b990701837a1cc4`
(candidate che asserisce Sensitivity/Response per infigratinib in questo
contesto — baseline del documento reale: CONTRADICTED).

**STAGE 5**: 2 paper selezionati, entrambi FULLTEXT_LOCAL_CONTEXT_BUNDLE/
ABSTRACT_BUNDLE: `EB-6a291f12975b20b79e1c3dd7` (primary),
`EB-e887ef4fb7cc42c2903e2e5a` (secondary).

**STAGE 6**: 2 chiamate Gemma, entrambe `FORCED_TOOL_VALID`, **entrambe
`abstain=true`**: il modello ha riportato correttamente che il testo
discute **BGJ398**, non **infigratinib** — non ha trattato i due nomi come
equivalenti né inventato un collegamento, si è astenuto esplicitamente su
entrambi i documenti.

**STAGE 7**: entrambe `ENRICHMENT_ABSTAINED`.

**STAGE 8**: nessun arricchimento validato -> `status=AMBIGUOUS`,
`gate_bucket=WARNING_BUCKET`. Nessuna promozione a `DIRECT` (il candidate
asserisce Sensitivity/Response) né a `CONTRADICTED` esplicito (nessun
`evidence_kind=RESISTANCE` validato) — esito conservativo e corretto: il
sistema non ha prove valide né per confermare né per contraddire, quindi
non assegna nessuno dei due.

**STAGE 9**: dossier con un candidate therapy (INFIGRATINIB), status
`AMBIGUOUS`, nessuna evidenza positiva fabbricata — obiettivo del caso
pienamente raggiunto: "Gemma riporti cosa scrivono gli autori; non
trasformi resistenza in beneficio; il validatore impedisca una promozione
positiva."
