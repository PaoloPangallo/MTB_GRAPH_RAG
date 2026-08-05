# Risultati per pair (7/7)

| Caso | Paper | Decision | Esito | Note |
|---|---|---|---|---|
| 1 (match forte, KRAS G12D/panitumumab, baseline DIRECT/Resistance) | EB-b4c48ba003913f278ff182a6 | QUOTE | **ENRICHMENT_V2_ACCEPTED** | Quota resistenza a panitumumab in pazienti mCRC con mutazioni KRAS — coerente con la direzione Resistance del candidate |
| 2 (discovery, BRAF V600E/encorafenib) | EB-479f55c21cac935ef1313755 | QUOTE | REJECTED_QUOTE_NOT_FOUND | Citazione su trial RAF/EGFR non letteralmente presente nella SourceUnit dichiarata |
| 2 (discovery) | EB-278efe96eecccc226c82aa2d | QUOTE | **ENRICHMENT_V2_ACCEPTED** | Quota attività clinica di cetuximab+encorafenib in mCRC BRAF-mutato |
| 3 (partial, MSI/nivolumab) | EB-883392431572b406505185cd | ABSTAIN | ABSTAINED_WITH_INCONSISTENT_FIELDS | Astensione motivata (il testo descrive solo il piano statistico), ma `source_unit_id` popolato — non promosso |
| 3 (partial) | EB-bd6ce2f5db3fb40af814743e | ABSTAIN | ENRICHMENT_V2_ABSTAINED | Astensione pulita: discute checkpoint blockade in generale, mai "nivolumab" nominato |
| 4 (contradicted/resistance, FGFR1/infigratinib) | EB-6a291f12975b20b79e1c3dd7 | ABSTAIN | ENRICHMENT_V2_ABSTAINED | Astensione pulita: il testo discute BGJ398, non infigratinib |
| 4 (contradicted) | EB-e887ef4fb7cc42c2903e2e5a | ABSTAIN | ABSTAINED_WITH_INCONSISTENT_FIELDS | Stessa motivazione (BGJ398≠infigratinib), ma `source_unit_id` popolato — non promosso |

## Primo esempio positivo end-to-end del progetto

Il Caso 1 è il **primo `ENRICHMENT_ACCEPTED`/`ENRICHMENT_V2_ACCEPTED`
ottenuto in tutta questa serie di pilot** (0/7 con v1.0, 0/7 con v1.1,
2/7 con v2.0). La quote accettata riporta correttamente una resistenza
(non un beneficio), coerente con la direzione `Resistance` del candidate
e con il criterio "i casi negativi o di resistenza vengono citati invece
di produrre astensione automatica" (sezione 13 del protocollo).

Il Caso 4 (BGJ398 vs infigratinib) continua a produrre astensione
corretta su entrambi i paper con tutte e tre le versioni del prompt —
comportamento di sicurezza stabile indipendentemente dal contratto di
output.
