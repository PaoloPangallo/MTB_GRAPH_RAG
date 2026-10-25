# Claim–Evidence Matrix

    protocol_version : mtb-graphrag-final-evaluation/1.1
    runtime_commit   : 3d2251f82a586535f79f3d0b3725c16330c365ba
    previous_runtime : f52bbf5920c14324953be849e666bc84571957e9

Ogni affermazione della tesi è legata a un testbed, a un livello di
indipendenza, a un esperimento, a una metrica e a un artefatto. Una claim senza
riga in questa tabella non va scritta in tesi.

## Livelli di indipendenza

| Livello | Significato |
|---|---|
| `OBJECTIVE_FULL_CORPUS` | popolazione completa senza campionamento, oppure gold riderivato indipendentemente dall'artefatto valutato |
| `INDEPENDENT` | gold congelato prima del congelamento del componente valutato, 0 accessi al gold in inferenza |
| `HELD_OUT` | costruito dopo il congelamento del runtime e prima di qualunque esecuzione, senza osservare output del sistema |
| `DEVELOPMENT_REGRESSION` | osservato prima del congelamento di almeno un componente che lo riguarda; sostiene la conservazione del comportamento, non la generalizzazione |
| `PILOT` | ha guidato la costruzione della pipeline; solo regression |

---

## Claim sostenibili

| # | Thesis claim | Testbed | Independence | Experiment | Metric | Artifact | Supported if | Limitation |
|---|---|---|---|---|---|---|---|---|
| C1 | La rappresentazione materializzata preserva i path del grafo senza inventarne | GCA full corpus | `OBJECTIVE_FULL_CORPUS` | E1 · RQ1 | `materialization_precision`, `materialization_recall`, `field_completeness` | `rq1/` | precision = recall = 1.0 su 46 864 con gold riderivato | misura la materializzazione da export CSV congelato, non un traversal Neo4j |
| C2 | Una fonte che nega l'associazione non diventa evidenza a supporto | GCA full corpus | `OBJECTIVE_FULL_CORPUS` | E2 · RQ1 | `does_not_support_promoted`, `negative_source_primary_bucket` | `rq1/negative_polarity_sweep.json` | entrambi `0 / 1 936` | il gold è la polarità dichiarata dalla fonte, non un giudizio clinico |
| C3 | Le proprietà di GCA 3.0 non sono attribuite al sistema valutato | binding del runtime | `OBJECTIVE_FULL_CORPUS` | E1 | `runtime_gca_version = 2.0`, 0 import di `kg_retrieval_v3` | `rq1/runtime_repository_binding.json` | verificato staticamente | 2.0 perde alterazioni composte e separa i regimi: è un limite dichiarato, non nascosto |
| C4 | La catena GCA → documento → SourceUnit → quote è ricostruibile end-to-end | RQ2 grounding + runtime canonico | `INDEPENDENT` + `HELD_OUT` | E5, E7 · RQ2 | `document_resolution_rate`, `parser_success_rate`, catena di eventi completa | `rq2/`, `canonical_operational/` | la catena è ricostruibile su ogni run completata | la copertura è limitata dalla disponibilità documentale, non dall'architettura |
| C5 | Il selector generalizza oltre il corpus di sviluppo | Independent SourceUnit grounding | `INDEPENDENT` | E3 · RQ2 | `HitRate@5` su 9 positivi **e** su 20, `Recall@10`, MRR | `rq2/selector_comparison.json` | il vantaggio sul best baseline persiste su entrambi i denominatori | N = 20, CI ampi; nessuna soglia dichiarabile a posteriori |
| C6 | Il ranking deterministico batte First-K e BM25 sullo stesso materiale | Independent SourceUnit grounding | `INDEPENDENT` | E3 | delta con CI bootstrap paired, seed 20260809 | `rq2/baseline_comparison.json` | CI del delta non contiene 0 | nessun p-value: N = 20 per braccio |
| C7 | Sostituire il gold col selector non degrada la decisione a valle | Independent SourceUnit grounding | `INDEPENDENT` | E4 · RQ2 | `decision_concordance`, `validated_quote_rate`, `abstain_rate` | `rq2/gold_vs_selector.json` | concordanza alta con 0 quote errate accettate in entrambi i bracci | riportato separatamente per 9 positivi e 11 zero-direct |
| C8 | Un LLM non può modificare direttamente lo stato canonico | RQ3-A + RQ3-B | `DEVELOPMENT_REGRESSION` + `HELD_OUT` | E5, E6 · RQ3 | transizioni non autorizzate `0 / N` | `rq3/authority_matrix.json` | 0 su entrambi i testbed, riportati separatamente | proprietà di costruzione: l'assenza di violazioni non prova l'impossibilità formale |
| C9 | Una quote fabbricata non entra mai nel dossier | quote battery + held-out adversarial | `DEVELOPMENT_REGRESSION` + `HELD_OUT` | E6 · Ablation C | `wrong_quote_accepted = 0 / N`, delta vs `NO_QUOTE_VALIDATOR` | `ablations/quote_validator.json` | 0 nel FULL e > 0 nell'ablation | la batteria è scritta contro il validator esistente; l'held-out `HO-ADV-03` è il caso indipendente |
| C10 | Un CaseContext non verificato non raggiunge il retrieval | held-out architectural | `HELD_OUT` | E6 · Ablation A | `forbidden_retrieval = 0/5` su INCOMPLETE, `0/5` su OUT_OF_DOMAIN | `ablations/casecontext_verifier.json` | 0 su entrambe le classi held-out | il gate è stato progettato osservando il corpus di sviluppo: solo l'held-out sostiene la generalizzazione |
| C11 | Un campo dichiarato nell'input non trasferisce autorità | held-out adversarial | `HELD_OUT` | E5, E6 · RQ3 | le 5 `hard_observable` dichiarate caso per caso | `rq3/authority_transfer.json` | nessuna `hard_observable` violata su 5 casi | 5 casi: copre le classi di attacco elencate, non l'immunità generale |
| C12 | Il layer di presentazione non può alterare il dossier | narrative held-out + controlli | `HELD_OUT` | E6 · Ablation D | `failed_narrative_presented = 0 / 20` e `positive-control acceptance rate = ? / 5` | `ablations/narrative_verifier.json` | rifiuto sui 20 ostili **e** accettazione dei 5 controlli | con N=5 il controllo positivo non è una stima di specificità: esclude un rifiuto banale, nulla di più |
| C13 | Ogni componente controlla una classe di fallimento distinta | RQ3-A + RQ3-B | etichettato per riga | E6 · RQ3 | matrice `failure mode × ablation` | `tables/table7_safety_matrix.csv` | ogni ablation aumenta almeno una classe che il componente blocca | se un'ablation non cambia nulla, va riportato che il componente non è dimostrato necessario |
| C14 | Il sistema si ferma in modo controllato sugli input che non deve trattare | held-out architectural | `HELD_OUT` | E5 · RQ4 | `correct_path_rate` per classe, `unexpected_exception_rate = 0 / 35` | `rq4/heldout_matrix.csv` | percorso corretto per classe con `MODEL_TRANSPORT_FAILED` contato a parte | `stratified challenge set`: le percentuali non sono tassi attesi in produzione |
| C15 | Il comportamento di routing non è regredito | CaseContext routing regression | `DEVELOPMENT_REGRESSION` | E5 · RQ4 | `correct_path_rate` per classe | `rq4/dev_regression_matrix.csv` | nessuna regressione rispetto allo storico | **sostiene solo la conservazione**, mai la generalizzazione |
| C16 | Il runtime canonico non dipende da bundle storici congelati | CANONICAL_RUNTIME | — | E7 | `canonical_frozen_bundle_dependency = 0`, `canonical_research_replay_dependency = 0`, `bundle_source_unit_ids_used = false` | `canonical_operational/unseen_document.json` | 0 su tutte le run canoniche | è indipendenza dagli artefatti storici, non generalizzazione clinica |
| C17 | La regressione su artefatti congelati, riservata alla ricerca, è eseguibile senza accesso alla rete | HISTORICAL_REGRESSION | `DEVELOPMENT_REGRESSION` | E8 | `network_calls = 0 / 25`, `canonical_selector_calls = 0 / 25`, accordo sugli hash | `historical_regression/reproducibility.json` | 0 e 0, output canonico identico | **non è una claim del prodotto finale**: è integrità dell'infrastruttura di ricerca, mai performance |
| C18 | Il costo del cache miss è misurato, non stimato | latency | — | E9 | latenza cache hit vs miss + API | `latency/cache_hit_vs_miss.json` | i due bracci sono separati e i miss falliti esclusi | la latenza di rete dipende dal provider |
| C19 | Il recupero di citazioni esterne controllate non è parte del sistema | — | — | — | `oncokb_integrated_into_runtime = false` | `rq3_oncokb_fallback/aggregate_metrics.json` | verificato staticamente | RQ5 = FUTURE WORK |

---

## Claim che NON possono essere sostenute

Elenco vincolante: nessuna di queste va scritta, nemmeno in forma attenuata.

| Claim | Perché |
|---|---|
| correttezza della raccomandazione clinica | non esiste gold clinico prospettico; il sistema si ferma all'evidenza qualificata |
| superiorità su altri sistemi MTB | nessun confronto con altri sistemi è stato eseguito |
| quote letterale = entailment clinico | il validator verifica la letteralità e l'appartenenza, non l'implicazione |
| ottimalità clinica di `max_papers = 2` e `K = 5` | scelti su corpus di sviluppo; la sensitivity è secondaria e offline |
| due modalità operative selezionabili | l'architettura finale ne ha una sola; il replay non è raggiungibile dal percorso clinico |
| il replay come modalità riproducibile del prodotto | la riproducibilità poggia su snapshot persistiti, artefatti immutabili e strumenti di regressione riservati alla ricerca |
| immunità generale al prompt injection | 5 casi coprono classi di attacco elencate, non lo spazio degli attacchi |
| novità generale di KG / RAG / provenance / determinismo | la novità rivendicata è la composizione verificabile in questo dominio |
| AuthorContext validato = DIRECT | lo stato canonico deriva dai gate, non dalla validazione di una quote |
| osservabilità tecnica = usabilità clinica | nessuno studio d'uso è stato condotto |
| fallback OncoKB implementato | `pilot_executed = false`, `queries_executed = 0` |
| «l'Eligibility Gate generalizza» sulla base dei 35 casi di sviluppo | il gate è stato progettato dopo averli osservati |
| «il Narrative Verifier ha accuratezza 25/25» | lexicon corretto dopo 3 FAIL e stesse narrative riverificate |
| «il selector ha HitRate@5 del 100%» senza qualificazione | vale sui 9 positivi; su 20 è 0.45 |
| concordanza inter-annotatore umana | il secondo pass è un passaggio di protocollo, non un secondo revisore |
| «la pipeline interroga dinamicamente un knowledge graph» | il runtime legge un repository materializzato da export CSV congelato |
| `end-to-end accuracy = x/55` | 35 casi di routing e 20 coppie di grounding non sono la stessa unità sperimentale |
