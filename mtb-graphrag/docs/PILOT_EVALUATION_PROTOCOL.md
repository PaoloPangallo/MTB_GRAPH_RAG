Protocollo di valutazione del pilota
====================================

Domande di ricerca
------------------

Sei tesi, tutte formulate in modo da poter risultare false:

1. Il GraphRAG ricostruisce evidenze multi-hop presenti nel Knowledge Graph.
2. Il report strutturato conserva fatti, fonti e qualificatori meglio di una sintesi
   LLM libera.
3. Il traversal deterministico e' sufficiente per le richieste note.
4. Il planner agentico e' giustificato solo quando deve adattare il percorso alle
   osservazioni.
5. Nessuna architettura recupera informazioni assenti dalla knowledge base.
6. Una fonte documentalmente valida non e' necessariamente applicabile al caso.

La quinta e' l'unica che ci si aspetta di confermare banalmente; serve come controllo
di sanita' dell'impianto sperimentale. Se una architettura "recuperasse" qualcosa di
assente dal grafo, il problema sarebbe nella misura, non nel sistema.

Unita' di analisi
-----------------

L'unita' e' la **claim clinica**, non il caso. Un caso con tre claim contribuisce tre
osservazioni alla loss decomposition, perche' le tre possono perdersi in punti diversi
della catena.

Le metriche di orchestrazione hanno invece il **caso** come unita': un piano e' giusto
o sbagliato nel suo insieme.

La catena
---------

```
clinical gold -> snapshot gold -> retrieval -> report strutturato -> report verificato
```

Ogni freccia puo' perdere informazione, e ogni perdita viene attribuita alla freccia
che l'ha causata. E' il motivo per cui le famiglie di metriche restano separate:

| Famiglia | Riferimento | Domanda |
| --- | --- | --- |
| `kg_coverage` | clinical gold | quanto esiste nel grafo |
| `retrieval_fidelity` | snapshot gold | quanto del recuperabile e' stato recuperato |
| `report_fidelity` | record recuperati | quanto sopravvive alla scrittura |
| `applicability` | profili clinici delle fonti | se cio' che sopravvive e' qualificato bene |
| `orchestration` | piano atteso | come il percorso e' stato scelto |

Un elemento assente dal grafo non entra nel denominatore del recall del retriever.
Un fatto mai recuperato non puo' essere perso dal report.

Architetture
------------

Due, e solo due:

1. **GraphRAG deterministico verificabile** — `FixedPlanStrategy`
2. **Agentic GraphRAG verificabile** — `AgenticPlanStrategy`

Differiscono **esclusivamente nella raccolta**. Entrambe passano da
`run_verified_pipeline(...)` e condividono tutto il resto: ledger, replay, vista
canonica, proiezione, report candidato, verifica strutturale, verifica claim-fonte,
applicabilita', repair/escalation, report verificato, dossier.

Non esistono runner alternativi. Un'implementazione parallela renderebbe la
differenza osservata fra le due architetture non attribuibile alla sola strategia di
raccolta, che e' l'unica cosa che l'esperimento vuole misurare.

La differenza osservabile si concentra in `planner_calls` (0 per il piano fisso) e
nell'attore di `plan_decision`.

Ablation di reporting
---------------------

Quattro bracci, **stesso retrieval congelato**:

| Braccio | Che cosa isola |
| --- | --- |
| `raw_records` | limite superiore di conservazione: nessuna sintesi, nessun LLM |
| `free_llm_summary` | che cosa perde una sintesi libera |
| `structured_report_unverified` | che cosa recupera la struttura, senza verifica |
| `structured_report_verified` | che cosa aggiunge la verifica delle fonti |

Il retrieval **non viene rieseguito** fra i bracci. Se lo fosse, una differenza fra
sintesi libera e report strutturato potrebbe venire da record diversi invece che dal
modo di scriverli, e la tesi 2 diventerebbe non verificabile.

Il braccio libero riceve gli stessi record nello stesso ordine, con lo stesso budget
di contesto, temperatura 0, tre repliche, e il raw output viene archiviato.

Seed e repliche
---------------

Tre seed dichiarati: `20240517`, `13`, `991`. Con tre run l'accordo run-to-run puo'
valere solo 1/3, 2/3 o 1: e' un indicatore grezzo di stabilita', non una stima di
varianza, e va letto come tale.

Se il provider ignora il seed, la run lo registra.

Cache
-----

Isolata per **modello, ruolo, architettura e condizione cold/warm**. Una run cold
agentica non deve ereditare la cache della deterministica: senza isolamento i
`cache_misses` misurerebbero l'ordine di esecuzione invece dell'architettura.

La chiave di cache include: source ID, hash dello statement, prompt version, model
revision, schema version. Cambiare uno qualunque di questi elementi deve invalidare
la voce, altrimenti si confrontano risposte prodotte da configurazioni diverse.

Fingerprint
-----------

Ogni artefatto porta il fingerprint dello snapshot:
`ffc97bc7c660f19478c33d28d1599b70e442525f0fae34b512e5efbf0796a9ae`.

E' derivato da conteggi per label, conteggi per tipo di relazione, totali e min/max
degli identificatori stabili. Non e' un hash del contenuto: due grafi con le stesse
statistiche collidono. Serve a rilevare che lo snapshot e' cambiato, non a provarne il
contenuto.

Loss decomposition
------------------

Ogni claim clinica riceve **esattamente uno** di undici stati:

`present_and_correct`, `missing_from_kg`, `partially_modelled_in_kg`,
`missed_by_retrieval`, `lost_in_report`, `misrepresented_in_report`, `citation_error`,
`qualifier_omission`, `applicability_error`, `correctly_abstained`, `unresolved`.

Gli stati sono valutati in ordine di catena e il primo che si applica vince: se una
claim non e' nel grafo, non ha senso chiedersi se il report l'abbia persa. E' questo
ordinamento a renderli mutuamente esclusivi senza casi ambigui, e
`ensure_exhaustive_loss` verifica la partizione a ogni chiamata.

Criteri di fallimento
---------------------

L'esperimento e' da considerarsi fallito, non "riuscito male", se:

- il fingerprint dello snapshot cambia durante le run;
- un prompt contiene informazione del gold (`GoldLeakageError`);
- i bracci dell'ablation ricevono record diversi;
- la loss decomposition non e' una partizione;
- le cache non sono isolate fra architetture;
- N1 produce una raccomandazione terapeutica.

In questi casi i risultati non vanno interpretati: vanno rifatte le run.

Limiti del campione
-------------------

Quattro casi. Le conseguenze vanno dichiarate insieme ai numeri, non in nota:

1. I valori **descrivono questo campione**. Non stimano una popolazione di casi
   clinici.
2. Nessun intervallo di confidenza: con n=4 sarebbe piu' ampio dell'intervallo dei
   valori possibili.
3. I casi sono stati usati per **selezionare il modello**, quindi non ne costituiscono
   una valutazione indipendente.
4. Una differenza fra le due architetture su quattro casi non e' una differenza
   dimostrata fra le due architetture.
5. La domanda di C1 nomina la terapia attesa, quindi il recall terapeutico di quel
   caso e' meno informativo.

Linguaggio ammesso
------------------

Questo e' uno studio tecnico su un knowledge graph, non uno studio clinico.

**Da usare**: valutazione tecnica, ricostruzione dell'evidenza, supporto alla
revisione, studio pilota, risultato sul campione, applicabilita' stimata, revisione
umana richiesta.

**Da non usare**: validazione clinica, terapia corretta, raccomandazione clinica
corretta, utilita' oncologica dimostrata, sistema pronto all'uso clinico.

Non e' una questione di prudenza formale. Il pilota misura se un sistema conserva
fatti e qualificatori recuperati da un grafo; non ha mai osservato un esito clinico, e
nessuna metrica qui calcolata potrebbe supportare un'affermazione su un paziente.

Revisione umana successiva
--------------------------

I risultati del pilota **non chiudono nulla**. Il gold stesso e' in prima annotazione,
la seconda revisione indipendente e' aperta, e i profili clinici delle fonti sono
`human_reviewed` ma non `frozen`.

Qualunque conclusione tratta da queste run e' provvisoria fino a che la seconda
revisione non e' completata e i disaccordi non sono stati risolti in modo esplicito.

Riproduzione
------------

```bash
cd mtb-graphrag

# gold
PYTHONPATH=. python benchmarks/mtb_evidence/evaluation/scripts/build_snapshot_gold.py

# pilota, con i modelli selezionati
PYTHONPATH=. python benchmarks/mtb_evidence/evaluation/scripts/run_pilot_evaluation.py \
    --clinical-gold benchmarks/mtb_evidence/evaluation/data/clinical_gold_v1.jsonl \
    --snapshot-gold benchmarks/mtb_evidence/evaluation/data/snapshot_gold_ffc97bc7c660f194.jsonl \
    --selected-models benchmarks/mtb_evidence/model_selection/results/v1/selected_models.json \
    --architectures deterministic agentic \
    --execution-mode live \
    --seeds 20240517 13 991 \
    --output benchmarks/mtb_evidence/evaluation/results/pilot_v1

# ablation di reporting, sul retrieval congelato
PYTHONPATH=. python benchmarks/mtb_evidence/evaluation/scripts/run_reporting_ablation.py \
    --output benchmarks/mtb_evidence/evaluation/results/pilot_v1

# test
PYTHONPATH=. python -m unittest discover -s backend/tests -t .
```
