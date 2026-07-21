Protocollo di selezione del modello
===================================

Perche' il modello non si sceglie sul test finale
-------------------------------------------------

Scegliere il modello guardando il test set lo consuma. Dopo averlo usato per
decidere, quel test non misura piu' la generalizzazione: misura quanto bene la
decisione si adatta ai dati su cui e' stata presa, e il numero che ne esce e'
ottimisticamente distorto di una quantita' non stimabile.

La selezione usa quindi **solo i quattro casi development** del pilota:

- `PILOT-K1-FGFR2-iCCA`
- `PILOT-A2-ALK-G1202R`
- `PILOT-C1-EGFR-L858R-CONTEXT`
- `PILOT-N1-RMI2-SNAPSHOT`

Il futuro test set non viene toccato. Ne consegue anche il limite piu' importante di
questo protocollo: **il modello selezionato non e' stato valutato in modo
indipendente**. Il pilota dice quale modello e' preferibile fra i candidati; non dice
quanto sara' bravo.

Candidati
---------

| Candidato | Ruolo nel protocollo | Endpoint |
| --- | --- | --- |
| modello attualmente configurato (`gemma4:31b-cloud`) | obbligatorio, e' il riferimento | cloud |
| `qwen3:14b` | obbligatorio se disponibile | locale |
| `gemma4:12b` | obbligatorio se disponibile | locale |
| `gemma4:31b` cloud | opzionale | cloud |
| `gemma4:31b` locale | opzionale, solo smoke test se la memoria lo consente | locale |

L'inventario registra ogni modello **osservato**, non ogni modello nominato. Un
candidato citato qui ma assente dall'istanza compare come `available: false` con la
ragione: non viene inventato, e non viene sostituito con un modello simile.

`inventory_ollama_models.py` interroga gli endpoint e registra per ciascun modello
nome, tag, digest, parameter size, quantizzazione, endpoint locale o cloud, context
length dichiarata, supporto ai tool, modalita' di output strutturato, data di
modifica e versione di Ollama.

I download non sono automatici. Con `--allow-pull` lo script scarica i candidati
locali mancanti, ma solo dopo aver stampato una stima leggibile e mai oltre 20 GB.

I cinque ruoli
--------------

Il registry separa `planner`, `source_verifier`, `free_report`,
`qualifier_extractor`, `optional_narrator`. Restano distinti perche' un modello puo'
essere adatto a pianificare e inadatto a estrarre qualificatori: mescolarli
produrrebbe una scelta che non e' la migliore per nessun compito.

Configurazione via ambiente: `OLLAMA_BASE_URL`, `OLLAMA_PLANNER_MODEL`,
`OLLAMA_VERIFIER_MODEL`, `OLLAMA_REPORT_MODEL`, `OLLAMA_QUALIFIER_MODEL`,
`OLLAMA_NUM_CTX`, `OLLAMA_TEMPERATURE`, `OLLAMA_SEED`, `OLLAMA_REQUEST_TIMEOUT`.

Identita' del modello
---------------------

`model_revision` = `provider:model_name:digest`.

Il digest identifica i **pesi**. Due tag possono puntare agli stessi pesi, e lo stesso
tag puo' cambiarli nel tempo: senza digest un esperimento non e' riproducibile. Se il
digest non e' disponibile si usa una revisione esplicita, e
`SOURCE_VERIFIER_MODEL_REVISION` puo' sovrascrivere il valore per invalidare una
cache restando sullo stesso modello.

La temperatura **non** entra nella revision. E' un parametro di campionamento, non
un'identita': trattarla come tale renderebbe due run dello stesso modello
indistinguibili da run di modelli diversi.

Il tag `latest` e' vietato negli esperimenti congelati, ed e' segnalato da
`assert_experiment_safe`.

Output strutturati: due regimi, non uno
---------------------------------------

| | `json_schema` | `prompt_validated` |
| --- | --- | --- |
| Dove | locale, Ollama >= 0.5 | cloud |
| Chi garantisce lo schema | il server, vincolando il decoding | nessuno |
| Validazione | comunque locale | locale, obbligatoria |
| Retry | non necessari | massimo 2 |

Confonderli attribuirebbe a un modello una robustezza che viene invece dal server.
Ogni run registra `structured_output_mode` e il numero di retry, cosi' che un
confronto fra un modello locale e uno cloud resti leggibile.

Per il regime `prompt_validated`:

- lo schema e' descritto nel prompt e verificato dal modello dati interno;
- il prompt di riparazione riceve **solo** output invalido, errore di validazione e
  schema — nessun contesto aggiuntivo, che altrimenti diventerebbe un canale per
  suggerire la risposta;
- dopo il secondo retry si **fallisce chiuso**: nessuna correzione silenziosa;
- niente estrazione di JSON con regex permissive. `parse_strict_json` accetta solo
  JSON che occupi il testo per intero, eventualmente dentro un blocco markdown. Una
  regex tollerante trasformerebbe un output invalido in uno apparentemente valido, che
  e' il modo piu' rapido per sopravvalutare un modello.

Controllo di contaminazione
---------------------------

Nessun prompt contiene claim del gold, PMID attesi, NCT attesi, etichette di
applicabilita', stato documentale, razionali del gold o decisioni dell'audit
(KEEP/AMEND/REPLACE/REJECT). `assert_no_leakage` verifica ogni prompt prima
dell'invio.

Il controllo distingue due categorie:

- **fuga sempre**: PMID, NCT, etichette, decisioni. Non sono mai input clinico.
- **fuga condizionale**: i nomi delle terapie attese, che sono fuga *solo se non
  compaiono gia' nella domanda del caso*.

La distinzione e' emersa da un caso reale: la domanda di C1 e' *"Ricostruisci
l'evidenza su osimertinib e distingui le fonti applicabili..."*. Il farmaco atteso e'
nella domanda. E' input legittimo — un clinico chiederebbe esattamente questo — ma
significa che il recall sulla terapia di C1 non misura la capacita' di recuperarla.
`leakage_overlap` restituisce l'elenco di queste sovrapposizioni, e vanno riportate
insieme ai risultati.

Configurazione del confronto
----------------------------

```
temperature = 0
num_ctx     = 16384
seed        = 20240517, 13, 991
```

Stessi prompt, stesso ordine dei record, stesso budget di output per tutti i modelli.
Se il provider ignora il seed, la run lo registra: un accordo run-to-run alto ottenuto
perche' il seed non ha effetto e' un'informazione diversa da un modello stabile.

`num_ctx` resta a 16384. Contesti da 128K o 256K non sono usati senza una necessita'
documentata: aumentano latenza e costo, e sul pilota non c'e' evidenza che servano.

Criterio di selezione: prima le soglie, poi la classifica
---------------------------------------------------------

**Ordine non invertibile.** Filtrare dopo aver ordinato permetterebbe a un modello con
ottime medie e un difetto disqualificante di vincere.

### Soglie di ammissibilita'

- `valid_action_rate` del planner >= 0.95
- `valid_output_rate` del verifier >= 0.95
- `valid_output_rate` del report >= 0.95
- `citation_accuracy` >= 0.95
- nessuna fuga del gold nei prompt
- nessuna omissione sistematica dei qualificatori su C1 e A2
- astensione corretta su N1 in almeno 2 run su 3

Una metrica **non misurata conta come fallimento**, non come passaggio: trattare
l'assenza come successo premierebbe un modello non misurato rispetto a uno misurato e
imperfetto.

### Classifiche per ruolo

```
planner  = 0.30 task_completion + 0.25 conditional_step_accuracy
         + 0.20 required_tool_recall + 0.15 stop_condition_accuracy
         + 0.10 run_to_run_agreement
         - penalita' unnecessary_tool_rate, planner_failure_rate

verifier = 0.30 documentary_status_accuracy + 0.30 applicability_status_accuracy
         + 0.20 qualifier_extraction_accuracy + 0.10 missing_context_detection
         + 0.10 run_to_run_agreement
         - penalita' compatible_overstatement_rate

report   = 0.25 claim_precision + 0.20 claim_recall + 0.20 citation_accuracy
         + 0.20 qualifier_preservation + 0.10 abstention_accuracy
         + 0.05 run_to_run_agreement
         - penalita' unsupported_claim_rate, context_omission_rate
```

I ruoli non vengono mescolati automaticamente. Un **modello unico** per tutti i ruoli
e' ammesso solo se resta entro il **5%** del migliore in ciascun ruolo: la semplicita'
di deployment non vale una perdita arbitraria.

Se nessun modello supera le soglie, l'esito e'
`model_selection_status = "no_model_qualified"`. **Le soglie non vengono abbassate
automaticamente**: la decisione torna a un umano.

Note sui casi
-------------

- **K1, C1, N1** non devono premiare il planner per aver eseguito piu' strumenti.
  `conditional_step_accuracy` resta indefinita fuori da ADAPTIVE invece di valere 1
  per default, e `unnecessary_tool_rate` penalizza l'esplorazione superflua.
- **A2** e' l'unico caso che verifica davvero il ramo condizionale: riconoscimento
  della resistenza, distinzione singola/composta, prosecuzione verso evidenza e trial,
  condizione di stop corretta.
- **N1** verifica l'astensione. E' l'unica metrica in cui produrre meno e' meglio.

Latenza
-------

Registrata per stadio e riportata come mediana, non come media: con tre run per
modello una singola chiamata lenta sposterebbe la media senza dire nulla sul
comportamento tipico.

Limiti
------

1. **Quattro casi.** I punteggi descrivono questo campione. Non stimano una
   popolazione, e nessun intervallo di confidenza viene riportato perche' con questo
   n sarebbe piu' ampio dell'intervallo dei valori possibili.
2. **Il modello selezionato non e' valutato in modo indipendente.** I casi usati per
   sceglierlo non possono anche misurarlo.
3. **Regimi diversi.** Un modello locale con `json_schema` e uno cloud con
   `prompt_validated` non partono alla pari sul `valid_output_rate`. La differenza va
   letta come proprieta' del deployment, non del modello.
4. **Tre seed** danno un accordo run-to-run che vale solo 1/3, 2/3 o 1. E' un
   indicatore grezzo di stabilita', non una stima di varianza.
5. **La domanda di C1 nomina la terapia attesa**, quindi il recall terapeutico di quel
   caso e' meno informativo degli altri.

Riproduzione
------------

```bash
cd mtb-graphrag

# 1. inventario (aggiungere --allow-pull per scaricare i candidati locali mancanti)
PYTHONPATH=. python benchmarks/mtb_evidence/model_selection/scripts/\
inventory_ollama_models.py --output benchmarks/mtb_evidence/model_selection/results/v1

# 2. selezione sui soli casi development
PYTHONPATH=. python benchmarks/mtb_evidence/model_selection/scripts/\
run_model_selection.py \
    --models current qwen3:14b gemma4:12b gemma4:31b-cloud \
    --roles planner verifier free_report \
    --seeds 20240517 13 991 \
    --output benchmarks/mtb_evidence/model_selection/results/v1
```

Il runner salta in modo leggibile i modelli non disponibili e non interrompe
l'esperimento se il modello cloud non e' autenticato: registra il motivo in
`failures.jsonl` e prosegue con i restanti.

`selected_models.json` contiene i modelli scelti per ruolo, le revision, i digest, la
configurazione, la motivazione e lo stato della selezione. **`.env` non viene
aggiornato automaticamente**: viene generato `selected_models.env.example` con i
valori proposti, e l'adozione resta una decisione esplicita.
