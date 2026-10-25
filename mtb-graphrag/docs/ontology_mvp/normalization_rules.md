# Regole di normalizzazione

1. Case folding, trim e collasso degli spazi.
2. Normalizzazione dei separatori `::`, dei trattini Unicode e della punteggiatura minima.
3. Alias disease soltanto dai gruppi verificati locali; l’alias non crea una gerarchia.
4. Alias farmaco soltanto da `DRUG_ALIASES`; alias pending o non presenti restano non mappati.
5. `p.L858R` e `L858R` sono la stessa forma normalizzata nel dominio variante, senza creare un ontology ID.
6. Componenti congiunte separate da `AND` sono ordinate deterministicamente per il confronto; il significato booleano viene conservato e non espanso.
7. `v::ALK Fusion` perde solo il prefisso di notazione `v::`; non viene trasformato in un nuovo concetto.
8. Fusion gene-level e partner-specific sono `RELATED` soltanto come forma testuale, non come equivalenza.
9. Principio attivo e sale/formulazione restano distinti; in assenza di mapping esplicito il match è non compatibile o sconosciuto.
10. Similarità fuzzy, conoscenza generale dell’LLM e inferenza clinica non sono usate.

La normalizzazione è separata dal match ontologico. Un valore può essere normalizzato senza possedere un concetto canonico o una relazione verificata.
