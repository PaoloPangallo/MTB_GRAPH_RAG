# Limitazioni note — dichiarate prima dell'esecuzione

    protocol_version : mtb-graphrag-final-evaluation/1.0
    runtime_commit   : f52bbf5920c14324953be849e666bc84571957e9

| # | Limitazione | RQ | Impatto | Mitigazione adottata | Future work |
|---|---|---|---|---|---|
| L1 | Corpus indipendente del selector: 20 coppie, 9 positive, 11 zero-direct, 29 unità direttamente rilevanti, 49 parzialmente | RQ2 | intervalli di confidenza ampi; nessuna significatività raggiungibile | denominatori sempre in coppia; CI di Wilson; bootstrap paired; nessuna soglia post-hoc | ampliare il corpus con nuove coppie annotate |
| L2 | Gold principale ad annotazione singola; il secondo pass è un passaggio di protocollo, non un secondo revisore umano | RQ2 | non è disponibile un accordo inter-annotatore reale | il campo è dichiarato `annotator_2_status = independent_protocol_pass_not_human_reviewer`; κ = 0.82 riportato come accordo fra protocolli, non fra persone | seconda annotazione umana indipendente, in fase separata, senza toccare il sistema |
| L3 | Sottoinsieme PMC full-text piccolo: 8 documenti su 20 | RQ2 | la degradazione ad abstract domina il corpus | classificazione osservata full-text vs abstract con denominatori | selezione mirata di candidate con PMC disponibile |
| L4 | **L'Eligibility Gate è stato progettato dopo aver osservato il benchmark CaseContext** | RQ4 | i 35 casi sono regression, non generalizzazione | corpus riclassificato DEVELOPMENT; claim ristretta agli invarianti architetturali | nuovo corpus di robustezza mai visto dal gate |
| L5 | **Il narrative lexicon è stato corretto dopo 3 FAIL e le stesse narrative riverificate** | RQ3 | il 25/25 è post-tuning sullo stesso campione | corpus riclassificato DEVELOPMENT; usato per l'ablation, dove la misura è il delta | nuove narrative ostili non usate per il lexicon |
| L6 | Feature del selector e K=5 scelti sui 25 bundle congelati | RQ2 | quel corpus non prova generalizzazione | evidenza di generalizzazione ristretta al corpus indipendente | — |
| L7 | Non determinismo del modello cloud: nessun seed esposto dal provider | RQ2, RQ3, RQ4 | run ripetute possono divergere | 1 run primaria per caso + reliability subsample a 3 run definito per regola; determinismo del selector dimostrato separatamente | provider con seed, o modello locale |
| L8 | Nessuna soglia di rifiuto validata: il selector restituisce sempre top-k se esistono unità | RQ2 | non esiste `NO_RELEVANT_SOURCE_UNIT` tarato | l'ABSTAIN di Gemma agisce da rifiuto a valle; la soglia non viene introdotta ora perché sarebbe una variabile nuova | calibrazione della soglia su corpus dedicato |
| L9 | Nessuna validazione clinica prospettica | tutte | la tesi non può affermare accuratezza clinica | le RQ sono formulate come proprietà architetturali | studio clinico |
| L10 | KG materializzato da export CSV congelato, non traversal dinamico su Neo4j | RQ1 | RQ1 misura la materializzazione, non l'interrogazione di un grafo vivo | dichiarato in `kg_source.kind = FROZEN_CSV_EXPORT`, `neo4j_used = false` | binding a istanza Neo4j |
| L11 | Disponibilità di API ufficiali e full text fuori dal controllo del sistema | RQ2, LIVE | copertura limitata; 3 documenti noti con `PMC_RESOLUTION_FAILED` | classificati come `ENVIRONMENTAL_LIMIT`, non come guasti | — |
| L12 | GCA v3 non è il runtime | RQ1 | polarità esplicita, regimi preservati e alterazioni composte non sono proprietà del sistema valutato | confronto shadow etichettato come non-runtime | promozione di v3 a runtime |
| L13 | OncoKB non implementato né autorizzato | RQ5 | nessun recupero di citazioni esterne controllate | RQ5 classificata FUTURE WORK | licenza e integrazione |
| L14 | `MODEL_TRANSPORT_FAILED` (ISS-012): 9 casi su 35 non hanno raggiunto il gate nel benchmark storico | RQ4 | riduce il denominatore effettivo | contato a parte nella tassonomia, mai confuso con uno stop mancato | irrigidimento del trasporto tool-call |
| L15 | Il testbed A è uno `stratified challenge set`, non un campione a prevalenza clinica | RQ4 | le percentuali per classe non sono tassi attesi in produzione | etichetta obbligatoria in ogni tabella | — |
| L16 | Il sotto-corpus narratore usa 20 dossier sintetici su 25 e ha le colonne del revisore vuote | RQ3 | la fedeltà è verificata automaticamente, non da giudizio esperto | dichiarato; l'ablation misura il delta, non l'accuratezza assoluta | revisione esperta delle narrative |

## Nota di consistenza rilevata durante l'inventario

Il docstring di `backend/research_pipeline/experimental/__init__.py` afferma che
nessun modulo di `backend/research_pipeline` importa il package sperimentale.
A `f52bbf5` questo non è più vero: `retrieval/live_sourceunit_selection.py` lo
importa, come previsto dalla promozione del selector in LIVE.

Il comportamento del runtime è corretto e coerente con il contratto dichiarato
in `runtime_contract.json`; è il commento a essere rimasto indietro. **Non viene
corretto**, perché il runtime è congelato: è registrato qui come discrepanza
documentale nota.
