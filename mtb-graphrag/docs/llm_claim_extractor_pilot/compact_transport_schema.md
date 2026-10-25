# Schema compatto del trasporto

Il trasporto `llm-claim-proposal-transport/1.1` richiede gli identificativi di candidate, bundle e documento, quattro blocchi di campo (`value`, `source_unit_ids`, `quotes`, `explicitness`), relazione, negazione, contraddizione, incertezze e astensione.

Sono rifiutati campi extra, chiavi annidate mancanti, quote non stringa e valori di explicitness non ammessi. Il modello non invia proposal ID, normalizzazioni o offset.
