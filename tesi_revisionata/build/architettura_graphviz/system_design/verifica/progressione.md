# Riscontro della progressione didattica — 17 ottobre 2026

Nota storica della revisione precedente. Per la distinzione corretta tra predefinito, focused-v1 e confronto semantico condizionale consultare [MACROFASI_RISCONTRO.md](MACROFASI_RISCONTRO.md), che sostituisce questa descrizione.

`journey.js` contiene parafrasi didattiche, non copie dei payload intermedi. Le frasi finali di esempio sono esplicitamente indicate come parafrasi, non come output letterali del modello. Nessuna nuova esecuzione.

## Riscontro con il codice corrente

- Preparazione: `data_access.py`, `retrieval/composite_evidence.py`, riferimenti della fase corpus in `sources.json`. La conoscenza è disponibile prima della ricerca.
- Caso e identità: `casecontext/pipeline.py`, `terminology/case_resolution.py`, contratto dei 16 stage in `contracts.py`. Gene, variante e contesto di malattia rimangono distinti.
- Registro: ramo `trial_fact_provenance` in `orchestrator.py`; `documents/trial_facts.py::extract_trial_facts` e `bind_trial_relation`. I fatti vengono collegati senza chiamata generativa; eleggibilità non valutata.
- Solo grafo: separazione `kg_only_associations` nell’orchestratore. Nessuna lettura documentale attribuita a un record privo di documento.
- Pubblicazione: `enrichment/validator_v3.py` verifica citazione letterale e identità del passaggio; `enrichment/document_verification.py::admit` distingue l’autenticità dal supporto alla relazione. Nessuna causa dell’esito NO_SUPPORT viene inferita dalla sola differenza clinica.
- Regole: `determinism/gates.py::evaluate_association` e filtro `_accepted_for_gates` nell’orchestratore; osservazioni non ammesse non vengono promosse a supporto.
- Dossier: raccolta prima della presentazione, come richiesto in `narrative/stage_runner.py`.
- Spiegazione corrente: `narrative/controlled_narrator.py` usa catalogo, piano e alternativa deterministica; `narrative/controlled.py::verify_controlled` confronta campi, ordine e copertura. Il diagramma descrive questo codice corrente; l’esempio riporta separatamente il controllo finale dell’analisi archiviata.

I percorsi sopra sono relativi a `mtb-graphrag/backend/research_pipeline/`; `sources.json` conserva riferimenti puntuali e impronte dei file.

## Riscontro con l’archivio E2E20-16

Origine: `experiments_real/remaining_fixes_20261015/live4/E2E20-16/`.

- `input.json`: caso dichiaratamente sintetico, melanoma metastatico, BRAF V600K, dabrafenib e trametinib.
- `run.json`, stage 2, 3 e 3b: estrazione, ancoraggio delle informazioni ed ammissione alla ricerca.
- Stage 4: identità della malattia con contesto metastatico conservato.
- Stage 8: cinque passaggi selezionati per l’associazione alla pubblicazione 28891408.
- `dossier.json`: citazione autenticata e NO_SUPPORT per la relazione dell’esempio; studio NCT02279004 con eleggibilità NOT_EVALUATED; FoundationOne CDx–BRAF nel solo grafo.
- `run.json`, stage 14 e 15: narrazione presente e controllo finale PASS. Questo non certifica applicabilità clinica.

`extract-examples.cjs` ha riverificato cinque record del corpus e i tre file dell’archivio; `esempi.json` conserva le impronte e i riferimenti. La preparazione e il coordinamento non sono due ulteriori stage operativi: la progressione operativa comprende 16 fasi.
