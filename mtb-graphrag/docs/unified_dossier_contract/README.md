# Unified V3 dossier contract (shadow)

Questo modulo definisce un contratto canonico, read-only e offline. Aggrega
il risultato V3 congelato con estensioni separate per provenance, document
support, ontology alignment, diagnostic context ed ESCAT.

Il core non viene ricalcolato. Le estensioni sono additive e il join
claim-level usa esclusivamente `claim_id`.

Il ruleset ESCAT resta `RESEARCH_DRAFT`, `available=false`; nessun tier o
subtier viene assegnato automaticamente. I 15 draft persistenti del pilot
ESCAT e i quattro casi esplorativi di questa preview sono popolazioni diverse:
i primi sono artefatti di curation già approvati, i secondi sono dossier
canonici offline costruiti per provare il contratto.

Preview JSON: `benchmarks/mtb_evidence/unified_dossier_contract/data/unified_dossier_preview.json`.

Non esiste alcun collegamento a runtime, endpoint produttivo o frontend.
