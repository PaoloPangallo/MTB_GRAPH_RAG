# Riscontro tra presentazione, codice e esempio

Questa nota è materiale di verifica per l'autore, separato dalla vista destinata al relatore.

## Struttura consegnata

1. Comprensione del caso: Case Parser, campi estratti, ancoraggio, ammissione alla ricerca.
2. Recupero GCA: Entity Resolution, compatibilità per famiglia, ordinamento per specificità, tipo di fonte.
3. Analisi delle fonti: pubblicazioni, registri e solo grafo; selezione BM25 strutturale + MedCPT e RRF.
4. Verifiche: autenticazione, struttura, confronto semantico condizionale ed esiti distinti.
5. Dossier: relazione, fonte, osservazione, controlli e limiti.
6. Presentazione: catalogo, piano del modello, composizione, verifica di fedeltà e alternativa deterministica.

I diciotto passaggi precedenti restano approfondimenti. Preparazione del corpus e coordinamento sono rispettivamente a monte e trasversali; non sono due nuovi stage operativi.

## Differenze corrette rispetto alla descrizione precedente

| Aspetto | Riscontro nel codice | Conseguenza nella presentazione |
| --- | --- | --- |
| Registri senza Reader generativo | `retrieval/live_sourceunit_selection.py`: ramo `if focused and record.document_id.startswith('nct:')`; `orchestrator.py`: ramo `trial_fact_provenance` | Esplicitamente attribuito a focused-v1. Il predefinito mantiene selezione e Reader per il percorso documentale. |
| Piano dei documenti | `retrieval/document_plan.py::focused_enabled`, chiamato condizionalmente dal selettore | Non descritto come comportamento universale. |
| Predefinito documentale | `backend/api/research_routes.py` dichiara `legacy` se la variabile di profilo è vuota | La tabella descrive il codice senza opzioni aggiuntive, non una configurazione d'ambiente non ispezionata. |
| RRF | `canonical_rrf.py`: ranghi da 1, costante 60, profondità 25, pesi uguali, filtri prima della fusione | Punteggi somma di reciproci di rango; non media dei punteggi BM25 e MedCPT. |
| Compatibilità e specificità | `_match_candidate` filtra prima di `_specificity_order_key`; ordinamento lessicografico | Separazione esplicita tra ammissione della relazione e ordine delle relazioni ammesse. Nessun punteggio di efficacia. |
| Semantica aggiuntiva | `verification_policy.py::policy_for` e ramo EVIDENCE_DRUG in `orchestrator.py` | Richiede osservazione ammessa e struttura PASS; non viene attribuita a tutte le famiglie. |
| Contesto vicino | `enrichment/context_reader.py::ContextPolicy.from_environment` | Contesto adiacente predefinito, usato condizionalmente; espansione e gerarchia sono opzioni distinte. |

## Esempio documentato e limiti del confronto

Fonte dei dati: archivio `experiments_real/remaining_fixes_20261015/live4/E2E20-16`, più cinque record del corpus verificati da `extract-examples.cjs`. Impronte e riferimenti sono in `esempi.json`.

- Il caso è sintetico: melanoma metastatico, BRAF V600K, dabrafenib e trametinib come intervento oggetto della ricerca.
- Pubblicazione 28891408: cinque passaggi selezionati; osservazione adiuvante di stadio III con V600E oppure V600K; citazione autentica; stato della relazione NO_SUPPORT. La relazione dell'esempio è EVIDENCE_STATEMENT, non EVIDENCE_DRUG. Il mancato supporto non viene spiegato inventando una causa clinica.
- Registro NCT02279004: collegamento **studio → BRAF**, informazioni dello studio, eleggibilità individuale NOT_EVALUATED. Non è una prova di efficacia.
- FoundationOne CDx → BRAF: sola provenienza nel grafo; non è reso specifico per V600K e il test non viene aggiunto alla storia del caso.
- La figura di presentazione descrive il codice corrente del narratore controllato. La narrazione storica non viene dichiarata prodotta da quella stessa configurazione; le frasi mostrate sono parafrasi didattiche del dossier.
- Le classifiche RRF sono illustrative, non le classifiche registrate per BRAF. D è fuori dai primi 25 risultati MedCPT, non un elemento mancante dalla copertura obbligatoria del dense scorer. I quattro valori sono stati confrontati eseguendo la funzione pura `rrf_scores` estratta via AST dal backend.

## Cosa richiede una verifica ulteriore se cambia il contesto

Nessuna nuova analisi o chiamata ai modelli è stata eseguita. Per descrivere una specifica installazione occorre verificarne profilo, variabili d'ambiente e disponibilità dei modelli locali: il documento descrive i default del codice e le opzioni dichiarate. Se cambiano i sorgenti, rigenerare i manifest; l'assemblaggio rifiuta impronte diverse.

Per la successiva integrazione nel manoscritto restano da scegliere larghezza e impaginazione delle figure. I PDF sono vettoriali con testo selezionabile; la dimensione delle pagine segue il contenuto del diagramma. Il LaTeX non è stato modificato.
