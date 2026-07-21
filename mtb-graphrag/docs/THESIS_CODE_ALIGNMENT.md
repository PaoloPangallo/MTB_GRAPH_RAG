# Allineamento del codice alle due architetture GraphRAG verificabili

Questo documento descrive come il codice del repository realizza le due
architetture proposte nella tesi e dove passa esattamente il confine fra ciò
che le distingue e ciò che condividono.

Terminologia: il sistema è un **prototipo di ricerca**. Gli artefatti prodotti
sono destinati alla revisione di un Molecular Tumor Board e non costituiscono
raccomandazioni terapeutiche.

---

## 1. Le due architetture

### GraphRAG deterministico verificabile

```
Caso MTB → normalizzazione → piano fisso / traversal tipizzato
  → strumenti KG autorizzati → event log append-only → vista canonica
  → proiezione pertinente → rendering candidato deterministico
  → verifica strutturale → verifica claim–fonte → valutazione di applicabilità
  → repair bounded oppure escalation → dossier verificato → revisione oncologica
```

Il percorso e l'ordine degli strumenti sono stabiliti **prima** dell'esecuzione.
Implementazione: `backend/pipeline/control/strategies/fixed_plan.py`.

### Agentic GraphRAG verificabile

Stesso flusso, con la raccolta guidata da un planner LLM controllato che
attraversa un ciclo plan–act–observe. Implementazione:
`backend/pipeline/control/strategies/agentic_plan.py`, che incapsula
`backend/pipeline/agentic/runtime.py`.

Il planner sceglie **uno strumento alla volta**, vincolato da allow-list,
dipendenze fra strumenti, budget totale, timeout per chiamata, retry bounded e
policy di completezza per `mtb_goal`. Quando non produce una decisione
utilizzabile passa a `safe_fallback`, e in quel caso la run **non** viene
descritta come pianificazione dinamica.

---

## 2. La differenza è solo nella raccolta

Le due architetture implementano la stessa interfaccia
(`strategies/protocol.py`):

```python
class CollectionStrategy(Protocol):
    architecture_id: Literal["deterministic", "agentic"]
    orchestration_mode: Literal["deterministic", "agentic"]
    def collect(self, ctx: CollectionContext) -> CollectionOutcome: ...
```

Tutto ciò che segue `collect()` è **lo stesso codice**, non codice duplicato.
Se questa interfaccia crescesse fino a includere rendering o verifica, il
confronto smetterebbe di misurare l'orchestrazione e tornerebbe a misurare due
pipeline diverse.

La differenza osservabile è concentrata in `planner_calls` (0 per il piano
fisso) e nell'attore di `plan_decision` (`fixed_plan_controller` contro
`llm_planner`). Il controller a piano fisso emette comunque `plan_decision`
con lo stesso schema del planner, così replay, canonicalizzazione e verifica
sono ciechi rispetto all'architettura.

Verifica automatica: `backend/tests/test_architecture_parity.py`.

---

## 3. Lo strato di controllo condiviso

`backend/pipeline/control/runner.py::run_verified_pipeline` esegue, nell'ordine:

| Fase | Modulo |
|---|---|
| raccolta | `strategies/{fixed_plan,agentic_plan}.py` |
| replay | `replay.py` |
| canonicalizzazione | `canonical.py` |
| proiezione | `projection.py` |
| rendering candidato | `rendering/candidate.py` |
| verifica strutturale | `verification/structural_text.py` |
| verifica claim–fonte | `verification/source_port.py` |
| applicabilità | `agentic/applicability_validator.py` |
| repair / escalation | `repair.py` |
| rendering verificato | `comparison/service.py::_render_verified_report` |
| dossier | `comparison/service.py::_build_dossier` |
| invarianti del dossier | `verification/dossier_invariants.py` |

Un solo `ActionRecorder` per esecuzione, condiviso con la strategia: una
catena, un `run_id`. In precedenza il ramo agentico apriva *due* `EventLedger`
sullo stesso `run_id`.

---

## 4. Il ledger

SQLite, append-only tramite trigger di riga `BEFORE UPDATE`/`BEFORE DELETE`,
hash-chain SHA-256, `run_id` e sequenza ordinata.

Va descritto come **append-only e tamper-evident nel threat model
considerato**, non come immutabile in senso assoluto: chi controlla il
filesystem può sostituire il file per intero.

### Schema v2

Colonne aggiunte: `schema_version`, `action_id`, `parent_action_id`,
`tool_name`, `tool_version`, `query_or_arguments_json`, `payload_hash`,
`pagination_state_json`, `completeness_status`, `generating_action_id`.

La migrazione (`agentic/ledger_schema.py`) è **puramente additiva**:
`ALTER TABLE ADD COLUMN` è DDL, non attiva i trigger di riga e non riscrive le
righe esistenti. Un rebuild-and-copy sarebbe stato indistinguibile da una
manomissione, ed è proprio ciò che un archivio di audit non deve fare.

### Hash-chain attraverso il confine v1→v2

Si versiona il **preimage**, non la catena. `_hash_event` resta byte-identico
per le righe v1; `_hash_event_v2` aggiunge il prefisso di dominio `"v2|"` —
senza il quale un evento v2 con colonne nulle collidrebbe con uno v1,
annullando il tag di versione — e codifica `NULL` come `\x00` per evitare
collisioni fra campi adiacenti. `chain_report()` verifica riga per riga e
riporta quanti eventi sono v1 e quanti v2.

Verificato sul ledger reale: 280 eventi, 14 run, 14 catene valide dopo la
migrazione, nessuna riga modificata.

### Bounding dei payload

Il ledger non è un archivio documentale. I payload sono sanitizzati **prima**
della scrittura (una credenziale in un archivio append-only non sarebbe più
rimovibile) e limitati in dimensione: si conservano i campi strutturati che il
replay usa, `payload_hash` e i riferimenti risolvibili, non gli abstract per
esteso — già ottenibili dal PMID. Ogni troncamento è registrato
esplicitamente e degrada `replay_fidelity`.

---

## 5. Replay e vista canonica

```python
canonical_view = replay_to_canonical_view(ledger.events(run_id))
```

Funzione **pura**: nessun I/O, nessuno stato, nessuna richiesta. La vista non è
più calcolata dallo stato in memoria e poi registrata, ma derivata dal solo
ledger — quindi riproducibile e verificabile senza rieseguire la pipeline. È
anche ciò che rende semplice la riparazione: dopo una nuova azione basta rifare
il fold sull'intera lista, senza patch incrementali che possano far divergere
vista e ledger.

La deduplicazione **fonde** invece di scartare. Ogni `CanonicalRecord` porta:

```
canonical_record_id   hash dell'identità → stabile fra run
source_event_ids      tutti gli eventi generatori, non solo il primo
source_action_ids     tutte le azioni generatrici
original_claim        prima osservazione, verbatim, mai riscritta
provenance            riferimenti al ledger per ogni occorrenza
conflict_annotations  disaccordi fra osservazioni, annotati non risolti
completeness_status   propagato in modo pessimistico
```

I conflitti sono rilevati sui soli campi **strutturati** (`evidence_level`,
`significance`, `phase`, `status`, …). I campi in prosa sono esclusi
deliberatamente: due curazioni CIViC dello stesso studio lo descrivono spesso
con parole diverse, e segnalarlo come conflitto abituerebbe il MTB a ignorare
le annotazioni.

Gli eventi v1 non trasportano record strutturati: un run storico riporta
`replay_fidelity = "degraded_v1_events"`, non "full" con zero record. L'assenza
di dati va distinta dall'impossibilità di ricostruirli.

---

## 6. Proiezione

`projection.py::project_for_case(view, case)` parte **esclusivamente** dalla
vista canonica. Ammette o esclude ogni record motivando l'esclusione,
distingue evidenze terapeutiche, resistenze e trial, e registra criteri ed
esito nel ledger (`projection_created`). Non inventa dati.

Ogni `ProjectedRecord` porta un `lexicon` e un insieme di `entities`: sono ciò
che trasforma "il renderer ha inventato qualcosa?" in una domanda decidibile.

---

## 7. Verifica strutturale

Due passaggi con **insiemi attesi diversi**, e due verificatori distinti.

| | candidate | final |
|---|---|---|
| Input | proiezione + report candidato | proiezione + esiti del source verifier + report finale |
| Atteso | tutti i record ammessi | i soli record **documentalmente supportati** |
| Domanda | il renderer ha rappresentato fedelmente la proiezione? | il report finale corrisponde a ciò che la verifica ha sostenuto? |

Usare lo stesso atteso in entrambi produrrebbe un `MISSING_CLAIM` per ogni
record legittimamente filtrato: un record `uncertain` assente dal report finale
non è un'omissione, è il comportamento corretto. Assente dal **dossier**,
invece, lo è — ed è `DossierInvariantVerifier` a verificarlo.

### Perché non è una tautologia

Il verificatore **non importa `rendering/`**: entrambi dipendono dal contratto
neutrale `control/claim_grammar.py`. Se il verificatore derivasse dal renderer,
"il report è corretto" significherebbe soltanto "il renderer ha fatto ciò che
fa".

Prova empirica: eseguito su una run live, il verificatore ha rilevato copertura
0.0 con 21 violazioni, individuando una mappatura errata dei campi del KG che
produceva claim con soggetto e oggetto vuoti. Il renderer stava producendo
*fedelmente* righe vuote; un controllo derivato dal renderer non avrebbe visto
nulla di anomalo.

### Output

```
status | violations | warnings | missing_claims | unsupported_claims
spurious_citations | coverage | requires_repair | requires_human_review
```

Controlli **bloccanti**, basati su identificatori ed entità strutturate:
`SPURIOUS_CITATION`, `UNSUPPORTED_CLAIM`, `EXCLUDED_RECORD_RENDERED`,
`UNKNOWN_ENTITY`, `RECOMMENDATION_WORDING`, `BUCKET_DISAGREEMENT`,
`PARTITION_VIOLATION`, `VERIFIED_RECORD_MISSING_FROM_DOSSIER`.

Controlli **riparabili**: `MISSING_CLAIM`, `COUNT_MISMATCH`,
`CONFLICT_UNSURFACED` (rendering); `TRUNCATED_VIEW`,
`MISSING_MANDATORY_TOOL`, `RECOVERABLE_SOURCE_MISSING` (raccolta).

`LEXICON_VIOLATION` è **diagnostico**, non bloccante: l'euristica "token
farmaco-simile" è calibrabile solo su output reali e, se bloccante da subito,
fermerebbe report legittimi. La difesa anti-allucinazione bloccante poggia su
citazioni ed entità strutturate.

---

## 8. Verifica documentale (claim–fonte)

`verification/source_port.py` adatta `agentic/source_verifier.py`, comune alle
due architetture. Mantiene CIViC, PubMed, parsing dei bracci di studio,
claim contestualizzata, validazione deterministica, cache, batching, retry
bounded e comportamento fail-closed.

Valori ammessi:

```
supported_as_written | supported_after_contextualization | uncertain | contradicted
```

Nessun controllo strutturale può produrre `contradicted`: quel valore può
arrivare solo dal modello che afferma esplicitamente una contraddizione.

### Revisione del modello

`model_revision` usa l'**identificatore reale del modello**
(`ollama:<LLM_PIPELINE>`), sovrascrivibile con `SOURCE_VERIFIER_MODEL_REVISION`.
In precedenza restava la stringa `"default"`, quindi cambiare modello non
invalidava la cache e i profili vecchi venivano riusati silenziosamente.

La **temperatura non entra** in `model_revision`: non è una revisione del
modello, e mescolarla renderebbe la chiave incomparabile con l'identificatore
esposto dal provider. Parametri di decodifica andrebbero, semmai, in un hash di
configurazione separato.

La cache è **iniettata**, non un singleton di processo: senza, il cold di
un'architettura sarebbe già caldo per effetto della run dell'altra.

---

## 9. Applicabilità

Asse **separato** dal supporto documentale:

```
compatible | indeterminate | not_compatible
```

Una fonte può essere *supportata documentalmente* e *non compatibile con il
caso* senza essere falsa o contraddetta. I due assi non vanno fusi.

Verificati da regole deterministiche (`applicability_validator.py`): linea,
setting, stadio, trattamenti precedenti. Estratti semanticamente dal modello e
poi validati: popolazione, prerequisiti, bracci di studio. Lasciati alla
**revisione umana**: il contesto regolatorio, per cui non esistono regole
dedicate.

---

## 10. Riparazione bounded

Due regimi distinti, entrambi deterministici — un repair planner generativo
reintrodurrebbe la non-verificabilità che la pipeline esiste per eliminare.

**Rendering** (`RenderingRepairPlanner`): rigenera il testo dagli stessi dati
canonici, senza alcuna tool call. Rifare una query per un conteggio sbagliato
in intestazione costerebbe un accesso al grafo e potrebbe cambiare l'evidenza
sotto un errore che non la riguarda.

**Raccolta** (`CollectionRepairPlanner`): unico autorizzato a richiamare
strumenti, e solo quelli in `REPAIRABLE_TOOLS`. Legge argomenti e stato di
paginazione dalla riga di ledger dell'**azione generatrice** — è la ragione per
cui quelle colonne esistono.

Vincoli: massimo **un ciclo complessivo**, contato nel runner e non nei
planner, così un bug di planner non può causare un loop; nessuna modifica degli
eventi precedenti; nessun `drop_record` (cancellare evidenza per soddisfare un
verificatore è il peggior modo di fallire disponibile); nessuna promozione da
`uncertain` a `supported` senza nuova evidenza.

Se la riparazione non è possibile: `escalation_to_human_review`, registrata nel
ledger con motivo, piano, azione ed esito.

---

## 11. Metriche

`tool_calls` sommava grandezze eterogenee ed era un **letterale** in 3 run su
4. Resta come alias deprecato; il nuovo frontend non lo legge. Le metriche sono
costruite da `metrics.py::build_metrics`, che non ha argomenti oltre al
risultato della pipeline: per costruzione non può più esistere un letterale.

```
retrieval_tool_calls   planner_calls        llm_synthesis_calls
source_verifier_calls  verifier_batches     pipeline_nodes_executed
repair_attempts        ledger_events        ledger_valid
structural_coverage    structural_violations structural_warnings
spurious_citations     canonical_records_in/out  canonical_conflicts
projection_admitted/excluded  replay_fidelity  escalated
planning_mode  fallback_reason  mandatory_tools  missing_mandatory_tools
model_revision  prompt_version  cache_hits  cache_misses
```

Tempi per fase, con **chiavi unificate** emesse da entrambe le architetture (0
se la fase è un no-op, mai una chiave assente):

```
orchestration, collection, replay, canonicalization, projection,
candidate_rendering, structural_verification, source_verification,
applicability, repair, final_rendering, dossier
```

`llm_roles` è derivata dai fatti della run: il narratore non compare in
esecuzioni in cui la narrazione non viene eseguita.

---

## 12. Limiti aperti

- **Contesto regolatorio**: nessuna regola deterministica dedicata; resta in
  revisione umana, ed è dichiarato come tale.
- **Ledger v1**: i run storici restano ispezionabili ma non pienamente
  replayabili (`replay_fidelity = "degraded_v1_events"`).
- **`KNOWN_INTERVENTIONS`** (`regimen_arms.py`) è una lista chiusa di 41
  farmaci, centrata su NSCLC/EGFR: fuori da quel dominio il matching dei bracci
  degrada a `unknown`.
- **`LEXICON_VIOLATION`** è ancora diagnostico. Promuoverlo a bloccante
  richiede una calibrazione su un corpus più ampio di output reali.
- **Riparazione**: il gate valuta il verdetto del report *candidato*. Una
  violazione riparabile che emerge solo nella verifica finale porta a
  escalation senza tentativo di riparazione — comportamento fail-closed
  corretto, ma un secondo gate sul verdetto finale sarebbe un miglioramento.
- **Rendering verificato**: `_render_verified_report` non espone le annotazioni
  di conflitto, che il renderer candidato invece mostra.
- **Determinismo del verificatore**: a temperatura 0 il source verifier mostra
  comunque variazione fra run sugli stessi item (vedi il case study), quindi i
  conteggi di supporto non sono perfettamente riproducibili.
- **Runner di test**: il repository usa `unittest` stdlib. Non è stato
  introdotto un cambio di test runner dentro questo intervento.

---

## Riproducibilità

```bash
# Test backend
cd mtb-graphrag && PYTHONPATH=. python -m unittest discover -s backend/tests -t .

# Frontend
cd frontend && npm run lint && npm run typecheck && npm test && npm run build

# Case study live (richiede Neo4j attivo e credenziali LLM)
PYTHONPATH=. SOURCE_VERIFIER_MAX_WORKERS=6 \
  python experiments/thesis_alignment/run_case_study.py --live
```

Il case study distingue esplicitamente **run live** da test con LLM scriptato,
benchmark e case study descrittivo, e verifica l'isolamento della cache
(cold → 0 hit, warm → 0 miss) segnalando ogni anomalia invece di esportare dati
potenzialmente contaminati.
