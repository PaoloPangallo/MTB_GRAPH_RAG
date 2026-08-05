# Caso 5 — CaseContext mismatch / no match

**STAGE 1**: testo clinico su colorectal cancer con un'alterazione
fabbricata ("ZZTK9 P44R", gene inesistente nel repository), domanda su
panitumumab.

**STAGE 2**: parser produce fedelmente `gene=ZZTK9`, `alteration=P44R`,
con quote letterale corretta — comportamento atteso: il parser riporta
cosa c'è nel testo, non giudica plausibilità clinica. Transport
`FORCED_TOOL_VALID`.

**STAGE 3**: tutti i record `MATCH`, incluso il biomarker fabbricato (la
quote è genuinamente presente nel testo). `essential_fields_pass=True` —
**il verificatore non doveva e non poteva rilevare un problema qui**: il
problema non è testuale ma di esistenza nel repository, un livello diverso
di controllo.

**STAGE 4**: **NO_MATCH**. Nessuna candidate nel repository ha un
biomarcatore compatibile con "ZZTK9" — tutte le 46864 candidate
disponibili risultano escluse per `BIOMARKER_GENE_NOT_COMPATIBLE` (oltre a
`DISEASE_NOT_COMPATIBLE`/`TARGET_INTERVENTION_NOT_COMPATIBLE` per la quasi
totalità). Pipeline fermata qui.

**STAGE 5-9**: non eseguiti. **Gemma non è mai stato chiamato per questo
caso** (`fake_enricher`-equivalente reale: zero chiamate registrate) —
nessuna evidenza artificiale costruita, coerente con l'obiettivo
dichiarato del caso.
