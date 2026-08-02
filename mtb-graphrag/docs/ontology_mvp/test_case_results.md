# Casi obbligatori

| Caso | Query | Claim | Risultato | Nota |
|---|---|---|---|---|
| A | Non-Small Cell Lung Cancer | Lung Adenocarcinoma | `DESCENDANT`, distanza 1 | arco locale esplicito `NSCLC → lung adenocarcinoma`; non equivalenza |
| B | EGFR L858R | EGFR p.L858R | `SYNONYM`, distanza 0 | differenza di notazione normalizzata; nessun ID |
| C | ALK Fusion AND ALK G1202R | ALK G1202R AND v::ALK Fusion | `SYNONYM`, distanza 0 | ordine booleano e prefisso `v::` normalizzati; composizione conservata |
| D | FGFR2 Fusion | FGFR2::BICC1 Fusion | `RELATED`, compatibilità false | gene-level e partner-specific distinti |
| E | alectinib | alectinib hydrochloride | `RELATED`, compatibilità false | sale/formulazione non mappata localmente |
| F | RMI2 | FGFR2::BICC1 Fusion | `INCOMPATIBLE` | gene diverso |
| G | NSCLC | Intrahepatic Cholangiocarcinoma | `INCOMPATIBLE` | concetti disease locali senza relazione |
| H | EGFR L858R | EGFR Exon 19 Deletion | `INCOMPATIBLE` | stesso gene, alterazioni diverse |

`CLASS_MATCH` è coperto da un test con una fixture esplicita e locale costruita nel test; non è dichiarato disponibile nel registry reale perché non è stato trovato un mapping di classe verificato.

I test di non-mutazione verificano che l’evaluator non modifichi claim fields come bucket, score e rank. Il modulo non importa `EvidenceRetrievalPipeline` e non esegue endpoint V3: perciò non può alterare ordine o output di produzione. I quattro casi esplorativi V3 non sono stati rieseguiti né modificati; l’invarianza è garantita dall’isolamento del package e dalla modalità read-only.
