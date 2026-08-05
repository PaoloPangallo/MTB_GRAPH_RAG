# Validazione deterministica

LlmClaimProposalValidator controlla schema strict, identità, lineage,
appartenenza delle SourceUnit, document lineage, quote letterali e offset,
normalizzazione, direction, negazione, contraddizione, campi graph-only e
astensione.

Gli esiti includono ACCEPTED, ACCEPTED_WITH_DROPPED_FIELDS,
REJECTED_UNGROUNDED, REJECTED_SCHEMA, REJECTED_LINEAGE,
REJECTED_CONTRADICTION, REJECTED_DIRECTION, ABSTAINED e VALIDATION_ERROR.
La validazione è deterministica e non usa un LLM. Il support status resta
prodotto dal ClaimSupportVerifier esistente.
