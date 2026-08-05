# Confronto dei trasporti

## Protocollo 1.0

Il primo smoke aveva tre parse failure del testo JSON, con 1.024 output token ciascuno. Il runner non aveva conservato `done_reason`, thinking o raw recuperabile: la diagnosi corretta ? `RAW_CAPTURE_GAP`, non una troncatura dimostrata.

## Protocollo 1.1

Le tre risposte hanno prodotto una tool call con nome corretto e `done_reason=tool_calls`, ma nessuna ha prodotto argomenti conformi al contratto annidato. Il trasporto ? quindi pi? osservabile, non ancora valido per la proposta. Il validatore sostanziale non ? stato indebolito e non sono state applicate riparazioni JSON.

La run da 75 chiamate non ? autorizzata: il criterio di successo non ? raggiunto.
