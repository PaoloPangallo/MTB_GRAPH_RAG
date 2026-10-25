# Regole di risoluzione degli assessment

1. La chiave unica è `claim_id`.
2. Nessun match su biomarcatore, malattia, intervento, PMID o testo è ammesso.
3. Nessun assessment produce `NOT_ASSESSED`.
4. Un assessment corrente viene presentato con il suo stato reale.
5. `SUPERSEDED` è escluso dalla selezione corrente; se è l’unico record, la
   presentazione è `NOT_ASSESSED` con una nota storica.
6. Più assessment correnti producono `CONFLICTING_EVIDENCE` senza scegliere
   arbitrariamente un record.
7. Un assessment riferito a una claim inesistente produce `NOT_ASSESSED` con
   `CLAIM_NOT_FOUND`.
8. `NOT_APPLICABLE` viene mostrato solo se è presente un record esplicito con
   quello stato.

Il resolver non modifica record, eventi o riferimenti di supersessione.
