# Confronto trasporti

| Versione | Trasporto | Risultato
|---|---|---|
| 1.0 | RAW_JSON_TEXT | 3 parse failure; raw precedente non recuperabile integralmente |
| 1.1 | TOOL_CALL_NESTED | 3 tool call presenti, 3 argomenti non conformi |
| 1.2 | TOOL_CALL_FLAT | 3/3 transport validi; 3/3 raggiungono il validatore; 0 status finali |

Il trasporto flat ha risolto il problema di serializzazione. Non ha aumentato artificialmente la validit? semantica: il validatore ha rifiutato le proposte non grounded o con direction incompatibile.
