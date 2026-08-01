# Audit provenance qualified claim V3

Audit read-only eseguito sul branch audit/v3-provenance a partire da
93fb997. Sono stati letti il repository promosso
qualified_claim_repository/1.4 e quattro artefatti non ufficiali di review
delle source unit. Non sono stati letti gold, ledger SQLite o run ufficiali.

## Artefatti

- provenance_audit.md: metodo, universo, diagnosi e limiti.
- provenance_summary.json: conteggi macchina.
- provenance_inventory.csv: una riga per ogni claim attiva.
- broken_provenance_links.csv: riferimenti strutturali rotti.
- source_identifier_distribution.csv: identificatori diretti e parent-context.
- domain_provenance_summary.csv: statistiche per dominio e asse.
- pilot_claims.md: esempi FGFR2, ALK G1202R, EGFR/osimertinib, audit, rejected, aggregate e migliore provenance.
- recommended_repairs.md: proposte non applicate.

## Regola di interpretazione

source_ids e locator della claim sono distinti da parent_source_ids. Un parent
con PMID o DOI non è considerato automaticamente una fonte documentale della
claim: in quel caso lo stato resta PARENT_ONLY.

Gli artefatti ausiliari source-unit review servono solo a verificare la
presenza testuale di identificatori interni. Non sono il registro runtime e
non trasformano un ID interno in PMID, DOI, NCT, URL o locator.
