# Dossier preview (research-only)

Schema minimale (sezione 17 del protocollo):
`case_context`, `case_context_verification`, `candidate_therapies[]`
(ciascuno con `document_support`, `author_context` separato,
`validation_results`, `gate_results`, `status`, `warnings`),
`limitations`, `provenance`. L'arricchimento di Gemma appare solo sotto
`author_context` e non sovrascrive mai `claim`/`status`/`support_mask`/
`gate`/`score`/`provenance` — verificato da un test dedicato
(`DossierSeparationTests`), non solo per ispezione.

## Riepilogo (4 dossier prodotti su 5 casi)

| Caso | Drug | Status | Gate bucket | Author context |
|---|---|---|---|---|
| 1 | PANITUMUMAB | AMBIGUOUS | WARNING_BUCKET | vuoto (nessun arricchimento validato) |
| 2 | ENCORAFENIB | DISCOVERED | DISCOVERY_BUCKET | vuoto |
| 3 | NIVOLUMAB | AMBIGUOUS | WARNING_BUCKET | vuoto |
| 4 | INFIGRATINIB | AMBIGUOUS | WARNING_BUCKET | vuoto |
| 5 | — | — | — | nessun dossier (fermato al retrieval) |

Nessun dossier di questa run contiene un `author_context` popolato, perché
nessun arricchimento ha raggiunto `ENRICHMENT_ACCEPTED`/
`ENRICHMENT_ACCEPTED_WITH_WARNING` in questa run (vedi
`enrichment_validation.md`). Lo schema è comunque completamente
esercitato: ogni dossier riporta correttamente `document_support`
(paper selezionati/esclusi) e `validation_results` (incluse le
astensioni/i rigetti), distinguendo sempre l'evidenza deterministica dal
contesto (assente in questo caso) prodotto da Gemma.
