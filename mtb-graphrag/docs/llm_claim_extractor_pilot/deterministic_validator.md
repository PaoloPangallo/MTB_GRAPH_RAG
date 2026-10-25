# Validatore deterministico

LlmClaimProposalValidator controlla schema strict, identità, lineage, documento,
source unit, quote letterali, offset, ambiguità di quote duplicate,
normalizzazione, direzione, negazione, contraddizione, campi graph-only e
astensione.

Gli esiti sono ACCEPTED, ACCEPTED_WITH_DROPPED_FIELDS,
REJECTED_UNGROUNDED, REJECTED_SCHEMA, REJECTED_LINEAGE,
REJECTED_CONTRADICTION, REJECTED_DIRECTION, ABSTAINED e
VALIDATION_ERROR. Il validatore non usa un LLM.
