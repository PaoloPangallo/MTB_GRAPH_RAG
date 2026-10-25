# Provenance repair pilot report

## Decision

Il pilota ha analizzato 18 claim. Nessuna source unit nuova è stata inventata e nessun PMID parent-only è stato promosso.

- claim con source unit nuova propagata: **0**
- claim con locator nuovo: **0**
- claim `CLAIM_PUBLICATION_IDENTIFIER_ONLY`: **0**
- claim `PARENT_PUBLICATION_AVAILABLE`: **7**
- claim `AMBIGUOUS_PARENT_PROVENANCE`: **1**
- claim con mapping/source locator già presente: **10**

## Punto responsabile della perdita

La perdita è nella materializzazione/promozione: `corpus/materialization.py::promoted_claims()` copia i record senza reintrodurre un mapping claim -> source unit. Serializer e adapter non sono stati modificati.

## Estensione alle 131 claim

Non è sicuro estendere automaticamente la riparazione alle 131 claim parent-only: il repository corrente non contiene mapping claim-specifici dimostrabili per esse. Il rischio è attribuire una pubblicazione contestuale alla claim sbagliata, soprattutto per parent multi-pubblicazione e claim aggregate. Serve source-unit review o mapping esplicito upstream.

## Invarianti

- claim semantics: unchanged
- gate/scoring/bucket: unchanged
- repository 1.4: unchanged
- Knowledge Graph, ledger, gold, official experiments: not modified
- API/frontend: unchanged; overlay not default
