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

Domanda di ricerca — formulazione ammessa
-----------------------------------------

Il confronto e' **esplorativo fra famiglie, capacita' e scale differenti**. Non
permette di attribuire causalmente a una singola variabile — la taglia — un eventuale
miglioramento: i candidati differiscono anche per famiglia, architettura, dati di
addestramento e post-training.

> Quanto la scelta fra modelli cloud di scala e famiglia differenti influenza planner,
> verifier e free report sui quattro casi development?

**Formulazioni vietate**: scaling law, effetto causale della taglia, «il modello piu'
grande e' migliore perche' e' piu' grande».

I descrittori vanno riportati **separati**, mai collassati in un asse unico: parametri
totali, parametri attivi quando disponibili, famiglia, architettura, capability.
`active_parameters` e' registrato come `null` con la ragione — l'API del provider non
lo espone — invece di essere stimato.

Candidati
---------

I due candidati nominati nella prima stesura del protocollo, `qwen3:14b` e
`gemma4:12b`, sono modelli **locali**: sul cloud non esistono. La macchina non ha GPU
(planner su K1 misurato a 117 s contro 5 s sul cloud), e `gemma4:12b` non e' nemmeno
scaricabile perche' il server Ollama installato e' la 0.9.0 e quel formato richiede
una versione piu' recente.

Il set e' quindi ridefinito su modelli cloud effettivamente **abilitati per
l'account**. Su 18 modelli elencati dall'endpoint, 8 rispondono a `/api/chat`: gli
altri restituiscono 403 pur comparendo in `/api/tags`.

| Candidato | Parametri totali | Famiglia | Ruolo nel confronto |
| --- | ---: | --- | --- |
| `gpt-oss:20b-cloud` | 20.9B | gpt-oss | estremo piccolo |
| `gemma4:31b-cloud` | 32.7B | gemma | **modello attuale del progetto**, baseline |
| `gpt-oss:120b-cloud` | 116.8B | gpt-oss | stessa famiglia del primo, taglia maggiore |
| `nemotron-3-ultra-cloud` | 550B | nemotron | estremo grande |

La coppia `gpt-oss:20b` / `gpt-oss:120b` e' l'unico confronto **entro la stessa
famiglia**, quindi quello in cui la differenza di taglia e' meno confusa da altre
variabili. Resta comunque non causale: due checkpoint della stessa famiglia
differiscono anche per dati e post-training.

Esclusi, con la ragione registrata in `exclusions.jsonl` come `operational_exclusion`:

| Modello | Ragione |
| --- | --- |
| `qwen3:14b` | nessuna GPU: ~2,5 ore di CPU per i tre ruoli |
| `gemma4:12b` | server Ollama 0.9.0, formato non supportato |
| `qwen3.5:397b-cloud` | elencato ma 403 su `/api/chat`: account non abilitato |

**`operational_exclusion` non e' `model_failure`.** Un modello escluso non ha fallito:
non e' stato messo alla prova. Confonderli farebbe apparire come debolezza del modello
cio' che e' un limite dell'infrastruttura o dell'account.

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

Identita' atomica della run
---------------------------

Ogni run ha una **`run_key`** deterministica: SHA-256 del JSON canonico di tredici
componenti — `requested_model_tag`, `effective_api_model`, `model_revision`, `role`,
`case_id`, `task_id`, `seed`, `prompt_version`, `schema_version`, `case_hash`,
`source_profile_hash`, `temperature`, `num_ctx`.

`case_hash` e `source_profile_hash` sono la parte che conta di piu': senza di essi, un
cambiamento nei dati di input passerebbe inosservato e run prodotte da materiale
diverso finirebbero nella stessa media.

Il resume opera per `run_key`, mai per coppia modello-ruolo:

| Stato | Azione |
| --- | --- |
| completa e compatibile | skip |
| mancante | execute |
| incompleta | replace |
| incompatibile | preserve but do not reuse |
| `run_key` duplicata con componenti divergenti | **fail** |

La completezza di una coppia si stabilisce **solo dopo** aver verificato tutte le
`run_key` attese: contare le righe direbbe quante ce ne sono, non quali.

Gli artefatti si scrivono in modo atomico — file temporaneo, `flush`, `fsync`,
`os.replace` — perche' una riga JSON parziale renderebbe il resume inaffidabile
proprio dopo un'interruzione, che e' l'unico momento in cui serve.

Risoluzione del modello
-----------------------

Il modello si risolve **interrogando l'inventario del server**, non deducendo
l'endpoint dal nome. La vecchia regola `endswith("-cloud")` era fragile in due
direzioni: un modello locale chiamato `qualcosa-cloud` sarebbe finito sul cloud, e un
modello remoto servito con un altro nome non sarebbe stato trovato.

Ogni run registra separatamente `requested_model_tag`, `effective_api_model`,
`endpoint_mode`, `endpoint_url_sanitized`, `digest`, `model_revision`. Sui candidati
reali il tag differisce dal nome effettivo: `gemma4:31b-cloud` e' servito come
`gemma4:31b`.

`endpoint_mode` ammette `local`, `local_proxy_to_cloud`, `direct_cloud_api`, ed e'
dedotto da cio' che il server dichiara.

Prima di eseguire il protocollo su un modello si sonda l'**abilitazione** con una
chiamata minima: un modello elencato in `/api/tags` puo' comunque essere negato su
`/api/chat`, e scoprirlo alla dodicesima chiamata sprecherebbe undici run
attribuendo al modello un fallimento che e' dell'account.

Credenziali e rate limit
------------------------

`OLLAMA_API_KEYS` contiene **esclusivamente chiavi autorizzate**, identificate negli
artefatti solo da un `credential_slot` numerico. Non si registrano chiavi, prefissi,
suffissi, header `Authorization` ne' hash reversibili.

| Condizione | Comportamento |
| --- | --- |
| 401 / 403 | credenziale invalidata, si prova la successiva, fallimento a esaurimento |
| 429 | `Retry-After` rispettato; backoff esponenziale con jitter; retry limitato |
| 5xx | retry limitato con backoff |

La rotazione e' **resilienza fra credenziali legittime, non elusione**. Su 429 non si
cambia chiave per default: aggirare una quota d'account sarebbe un abuso del provider.
Si abilita solo dichiarando esplicitamente che le quote lo consentono.

Budget del contesto
-------------------

Prima di ogni chiamata: `input_tokens + reserved_output_tokens <= effective_context_window`,
dove la finestra effettiva e' il minimo fra `num_ctx` e quella dichiarata dal modello.

**Nessun troncamento silenzioso.** La riduzione dei record e' deterministica e
identica per tutti i modelli, e registra record iniziali, mantenuti, esclusi, token
iniziali, finali e motivo. Serve davvero: il free report su C1 ha un prompt da 11.466
token.

Privacy
-------

Sul cloud si inviano solo casi sintetici, casi benchmark, fonti pubbliche o dati
anonimizzati. Ogni prompt e' sottoposto a screening prima dell'invio: se emerge un
possibile identificatore personale, `cloud_input_rejected = true` e il prompt **non
parte**. Si registra la categoria rilevata, mai il valore.

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
