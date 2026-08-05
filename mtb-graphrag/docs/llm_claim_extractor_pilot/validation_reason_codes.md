# Reason code

Sono distinti: ACCEPTED_FIELD, DROPPED_NO_QUOTE,
DROPPED_BAD_OFFSET, DROPPED_WRONG_SOURCE_UNIT, DROPPED_UNNORMALIZED,
DROPPED_GRAPH_ONLY, DROPPED_DIRECTION_CONFLICT,
DROPPED_NEGATION_CONFLICT e DROPPED_AMBIGUOUS.

Gli errori globali distinguono schema, identità, lineage, contraddizione,
direzione e errore tecnico. In questo modo una proposta non grounded non viene
confusa con un documento privo di contenuto o con un errore del retriever.
