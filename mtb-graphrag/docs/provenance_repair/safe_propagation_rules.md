# Safe propagation rules

1. `CLAIM_VERIFIED_LOCATOR`: source unit e locator sono già nella claim oppure provengono da un mapping claim-specifico univoco.
2. `CLAIM_PUBLICATION_IDENTIFIER_ONLY`: mapping claim-specifico e source unit esistono, ma il locator è assente.
3. `PARENT_PUBLICATION_AVAILABLE`: il parent ha una pubblicazione, ma non è dimostrato il passaggio claim-specifico.
4. `AMBIGUOUS_PARENT_PROVENANCE`: il parent ha più pubblicazioni e non esiste mapping univoco.
5. Una aggregate claim senza mapping esplicito non viene attribuita.
6. Nessun valore viene ricostruito per somiglianza testuale e nessun PMID parent-only viene copiato nella claim.

Le condizioni di singola source unit del parent sono applicate solo quando `source_unit_ids` e locator sono realmente presenti nel parent; la 1.4 non presenta questa struttura per le claim parent-only analizzate.
