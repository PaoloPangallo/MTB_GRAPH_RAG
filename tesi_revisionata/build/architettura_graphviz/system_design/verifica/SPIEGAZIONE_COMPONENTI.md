# Riparazione degli approfondimenti

La revisione precedente aveva conservato diagrammi generici nei dettagli, nonostante la nuova vista a macrofasi. Questa revisione sostituisce tutti i diciotto grafi con operazioni, dati e decisioni specifici del componente. Rimuove le categorie in maiuscolo sotto i titoli dei nodi e presenta il funzionamento prima dell'esempio.

## Riscontri aggiuntivi

- `terminology/case_resolution.py::resolve_case`: malattia e contesto separati; prima gene, poi variante; ricerca degli interventi nel vocabolario; stati non risolti conservati.
- `casecontext/pipeline.py::build_retrieval_case_context`: proiezione delle sole menzioni accettate; `projection_audit` rende esplicita la perdita ingiustificata di fatti verificati.
- `casecontext/match_verifier.py`: citazioni letterali, occorrenze e disambiguazione tramite offset; riferimenti distinti per gene e variante.
- `eligibility/gate.py` e catena deterministica: tipo, ruolo, asserzione, contraddizioni e sufficienza dipendente dalla domanda.
- `orchestrator.py::_accepted_for_gates`: solo validazioni accettate con supporto forte/pieno vengono adattate per il gate. Il dossier conserva la valutazione documentale originale.
- `orchestrator.py`: lo stato del gate è esposto separatamente e non sostituisce l'aggregazione documentale nel dossier.

I percorsi sono relativi a `mtb-graphrag/backend/research_pipeline/`. Gli altri riferimenti restano in `sources.json` e `macrofasi-sources.json`.

## Dati verificati nell'esempio

`extract-examples.cjs` legge l'archivio già documentato e verifica:

- melanoma → `DOID:1909`, contesto residuo `metastatic`;
- BRAF → `NCBIGene:673`;
- V600K nel gene BRAF → `CIViCVariant:563`;
- stringa combinata “dabrafenib e trametinib” → `UNMAPPED`, senza perdita del valore originale;
- relazione con pubblicazione 28891408: gate `AMBIGUOUS`, avviso `NO_VALIDATED_ENRICHMENT_AVAILABLE`; stato documentale `NO_SUPPORT` già verificato.

Questi riscontri sono conservati in `esempi.json`. Non sono state eseguite nuove analisi. Il diagramma descrive il meccanismo, la tabella mostra la sua applicazione ai dati documentati; i due livelli non si sostituiscono.
