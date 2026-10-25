# Selezione paper deterministica

Nessun LLM. Criteri ordinati (sezione 9): 1) disease compatibile 2)
biomarker compatibile 3) intervention compatibile (già garantiti dal
retrieval) 4) direction/relazione definita 5) testo disponibile in cache
6) SourceUnit complete 7) provenance valida 8) priorità a evidenza più
diretta (ranking per `bundle_type`: FULLTEXT_LOCAL_CONTEXT_BUNDLE >
ABSTRACT_BUNDLE > TRIAL_BUNDLE — non basato su alcuna etichetta di verità
nota) 9) deduplicazione per `document_id`. Massimo 2 paper per
associazione.

## Risultati (4 associazioni comparabili)

| Caso | Paper selezionati | Tipo |
|---|---|---|
| 1 | EB-b4c48ba003913f278ff182a6 | ABSTRACT_BUNDLE (unico disponibile) |
| 2 | EB-479f55c21cac935ef1313755 (primary), EB-278efe96eecccc226c82aa2d (secondary) | FULLTEXT_LOCAL_CONTEXT_BUNDLE, ABSTRACT_BUNDLE |
| 3 | EB-883392431572b406505185cd (primary), EB-bd6ce2f5db3fb40af814743e (secondary) | FULLTEXT_LOCAL_CONTEXT_BUNDLE, FULLTEXT_LOCAL_CONTEXT_BUNDLE |
| 4 | EB-6a291f12975b20b79e1c3dd7 (primary), EB-e887ef4fb7cc42c2903e2e5a (secondary) | FULLTEXT_LOCAL_CONTEXT_BUNDLE, ABSTRACT_BUNDLE |

7 paper selezionati in totale, nessuno escluso per duplicazione o cap
superato in questa run (tutti i candidati disponibili rientravano nel
limite di 2).
