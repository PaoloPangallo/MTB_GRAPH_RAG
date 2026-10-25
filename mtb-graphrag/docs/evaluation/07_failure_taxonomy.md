# 07 — Tassonomia dei fallimenti

Classi di difetto osservate, con la loro estensione misurata. Nessuna di esse è
stata corretta in questo branch: correggerle richiede decisioni di progetto che
questo studio non prende.

## RQ1 — materializzazione

| Classe | Occorrenze | Layer | Natura |
|---|---|---|---|
| `DIRECTION_INVERSION` | 486 | graph | La regola `evidence-to-drug` deriva il predicato dalla sola `significance`; `evidence_direction = "Does Not Support"` non entra né nel predicato né in `direction` |
| `ALTERATION_LOST` | 1 091 | graph | I profili multi-variante sono ridotti alla prima variante; la logica AND/OR è persa |
| `REGIMEN_SPLIT` | 1 294 | graph | Record Evidence multi-farmaco divisi in candidate a farmaco singolo; `regimen` mai popolato |
| Duplicati semantici | 1 028 (344 gruppi) | osservazione | Semantica di deduplicazione non definita nel contratto |
| `FIELD_MISMATCH`, `PATH_NOT_FOUND`, `SPURIOUS_CANDIDATE`, `LINEAGE_BROKEN`, `INCORRECT_DEDUPLICATION`, `SOURCE_RECORD_MISMATCH`, `DOCUMENT_IDENTIFIER_MISMATCH` | **0** | contract | Non osservate |

Candidate con almeno un difetto di graph fidelity: **2 419 (5.16 %)**.
Sovrapposizione `DIRECTION_INVERSION` ∩ `REGIMEN_SPLIT`: 213.

## RQ2 — associazioni PMID

| Classe | Occorrenze | Natura |
|---|---|---|
| `PMID_PARENT_LEVEL_ONLY` | 3 370 (40.9 %) | Citazione ereditata dal record Evidence padre |
| — di cui da record multi-farmaco | 1 294 | Il paper riguarda più farmaci della candidate |
| `PMID_INVALID_FORMAT` / `COMPOUND_VALUE` | 17 | Più PMID in un campo (23 PMID resi irraggiungibili) |
| `PMID_INVALID_FORMAT` / `NON_NUMERIC` | 4 | DOI nel campo `citation_id` |
| `PMID_NOT_FOUND` | 1 | PMID `174591` inesistente |
| Ritrattazione / erratum | 3 | Fra cui 1 articolo **ritrattato** citato da una candidate |
| `PMID_DOCUMENT_UNAVAILABLE` | 2 214 / 2 229 | Testo non in cache |

## RQ4 — parser

| Classe | Occorrenze | Natura |
|---|---|---|
| Nessuna tool call conforme | 9 / 35 | 5 `FORCED_TOOL_IGNORED`, 4 `INVALID_TOOL_ARGUMENTS` |
| `QUERY_INTENT_INVALID` | 4 | Lo schema non prevede «nessuno dei due intent» |
| Sintomo copiato in `disease` | 5 | Errore di scope, non allucinazione |
| Alteration inventata | 1 | `B2`: «abnormality» promosso ad alterazione specifica |
| Ambiguità non registrata | 4 / 12 attesi | `uncertainties` vuoto dove il gold la prevede |
| Contraddizione non segnalata | 5 / 5 | Nessun meccanismo esiste |
| Offset dichiarati errati | 95.6 % | Confermano la scelta di progetto del verifier |
| Fuga di prompt | **0** | |
| Fabbricazione su istruzione | **0** | |
| Injection eseguita | **0** | |

## Difetti trasversali

| Classe | Descrizione |
|---|---|
| **Assenza dello stato `OUT_OF_SCOPE`** | Un CaseContext vuoto supera `essential_fields_pass` (`MISSING_IN_TEXT` non è `MISMATCH`) e prosegue al retrieval. Solo 2 esiti di routing esistono, e la categoria dell'input non li determina |
| **Endpoint di default non funzionante** | `https://api.ollama.com` risponde HTTP 405 su `/v1/chat/completions`: con la configurazione di default **tutte** le chiamate del parser falliscono |
| **Nessuno stato bibliografico** | Il repository non porta alcun campo che segnali una ritrattazione |

---

# §11 — Il caso BGJ398 / infigratinib

**Stato: `KNOWN_DRUG_SYNONYM_GAP`. Non corretto in questo studio.**

Nessuna eccezione hard-coded, nessun mapping *ad hoc*, nessun fuzzy matching
clinico, nessuna normalizzazione permissiva, nessuna modifica del controllo di
letteralità sono stati introdotti. Il test
`test_null_tokens_collapse_but_clinical_terms_do_not` verifica che
`norm_text("BGJ398") != norm_text("infigratinib")` nella chiave canonica di RQ1.

## Perché il documento può essere pertinente

`BGJ398` è il codice di sviluppo dell'inibitore pan-FGFR poi denominato
`infigratinib`. Un paper che riporta risultati clinici su BGJ398 riporta
risultati sullo stesso principio attivo che una candidate nomina come
infigratinib. Dal punto di vista clinico la pertinenza è reale.

## Perché il validatore ha rigettato correttamente

Il contratto attuale è la **letteralità**: ogni valore deve essere sostenuto da
una citazione esatta e contigua del testo sorgente. Il verifier
(`_verify_span_field`) verifica che la citazione compaia letteralmente e che il
valore normalizzato non diverga da essa.

Un documento che dice «BGJ398» non contiene la stringa «infigratinib». Accettare
il match richiederebbe di sapere, *fuori dal testo*, che i due termini denotano
la stessa entità — cioè esattamente la conoscenza esterna che il contratto
esclude. **Il rigetto non è un bug: è il contratto che funziona.**

Il costo è un falso negativo. Il beneficio è che nessun valore entra nella
pipeline senza un ancoraggio testuale verificabile. Rilassare il controllo per
questo caso comprometterebbe la proprietà su tutti gli altri.

## Perché una soluzione futura richiede un resolver terminologico valutato

Il problema non è «aggiungere BGJ398 → infigratinib». Il progetto **ha già** quella
decisione: `qualified_claim_repository_1_4/terminology_registry.json` contiene

```
queue_id                 TRQ-BGJ398
terminology_decision_id  TP-BGJ398-INFIGRATINIB
canonical_label          infigratinib
decision                 verified_development_code_for_same_intervention
confidence               high
is_verified              true
source_literal_preserved true
mapping_scope            global
propagation_policy       prototype_only
review_independence      non_independent
review_status            first_review_complete
```

La mappatura esiste, è verificata e conserva il letterale di origine. Non è usata
dalla pipeline V3 verificabile per due ragioni sostanziali:

1. **`propagation_policy: prototype_only`** — la decisione non è autorizzata a
   propagarsi oltre il prototipo;
2. **`review_independence: non_independent`** — è stata rivista una volta sola,
   senza revisione indipendente.

Il gap, quindi, non è di conoscenza ma di **governance**: manca una revisione
indipendente e una politica di propagazione che autorizzi l'uso in produzione.
Un resolver che risolva questo caso deve essere *valutato*, con la sua propria
precisione e i suoi propri falsi positivi misurati — perché il rischio
simmetrico è unire due farmaci che non sono lo stesso.

Nella stessa coda risulta `AUY922` ancora **irrisolto**, il che mostra che la
coda terminologica è un processo aperto, non una tabella completabile.

## Quali vocabolari potrebbero essere studiati

Nessuno di questi è stato integrato, valutato o introdotto in questo branch:

| Risorsa | Copertura pertinente |
|---|---|
| **RxNorm** (NLM) | Nomi di farmaco e relazioni fra forme; copertura debole sui codici di sviluppo pre-approvazione |
| **ChEMBL** | Composti sperimentali con sinonimi e codici di sviluppo — il più adatto al caso BGJ398 |
| **DrugBank** | Sinonimi e codici di sviluppo; licenza da verificare per uso accademico |
| **NCI Thesaurus** | Concetti oncologici, inclusi agenti sperimentali |
| **UNII / GSRS** (FDA) | Identità di sostanza a livello di principio attivo |
| **OncoTree** | Non pertinente ai farmaci; già usato da OncoKB per i tipi di tumore |

Un lavoro futuro dovrebbe: (a) scegliere una risorsa e fissarne la versione;
(b) misurare precision e recall del resolver su un campione annotato;
(c) mantenere il letterale di origine accanto al canonico, come già fa il
registry; (d) sottoporre le decisioni a revisione **indipendente** prima di
consentirne la propagazione.

Fino ad allora `BGJ398 ≠ infigratinib` per la pipeline, e questo studio lo
registra come limite noto e misurato, non come difetto da nascondere.
