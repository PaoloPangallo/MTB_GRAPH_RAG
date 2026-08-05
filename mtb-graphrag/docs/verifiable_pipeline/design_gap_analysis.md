# Design gap analysis (Fase B)

Confronto fra il design derivato
([`2026-08-04-verifiable-pipeline-design.md`](../superpowers/specs/2026-08-04-verifiable-pipeline-design.md))
e lo stato reale del repository.

**Avvertenza sulla natura di questo documento.** Il SYSTEM DESIGN originale non
è mai stato fornito; su indicazione dell'utente l'ho derivato io. Questo
documento **non** confronta quindi un design indipendente con il codice: confronta
un design *estratto dal codice* con il codice. Il suo valore è nel misurare la
distanza fra il **prompt** (le 29 sezioni) e la realtà, non nel validare
un'architettura di terze parti. Un vero gap analysis resta possibile solo se il
documento originale comparirà.

## 1. Requisiti del prompt già soddisfatti dal codice

Più di quanto il prompt assumesse.

| Requisito | Dove è già soddisfatto |
|---|---|
| §7 event log append-only | `agentic/ledger.py` + trigger SQLite |
| §7 hash chain | `verify_chain`, già esposta in API |
| §7 evento / stato / output distinti | `events.py` / `canonical.py` / `projection.py` |
| §7 payload hash, causation, lineage | colonne v2 `payload_hash`, `parent_action_id`, `generating_action_id` |
| §7 replay | `control/replay.py` |
| §2 no testi documentali completi | `_DROPPED_TEXT_FIELDS`, `MAX_TEXT_FIELD_CHARS` |
| §5 no chain-of-thought | payload strutturati; nessun campo di thinking |
| §15 vocabolario errori/astensioni | 10 `ENRICHMENT_OUTCOMES` + 4 `stopped_at` + 4 `MATCH_STATUSES` |
| §16 cinque casi sintetici | `case_definitions.py` — già esistono |
| §26 Gemma non decide lo status | `evaluate_association` filtra a monte; `dossier.py` lo dichiara |
| §13 nessuna "raccomandazione clinica" in UI | verificato: zero occorrenze nel frontend |

## 2. Divergenze fra prompt e realtà

| # | Prompt | Realtà | Risoluzione |
|---:|---|---|---|
| 1 | 15 stage | 9 nel pilot | mappatura esplicita; 4/5 e 11/12 fusi nell'esecuzione, separati in UI |
| 2 | §11 dieci gate | 4 assi di `support_mask` | espongo le 4 reali; le altre 6 `NOT_IMPLEMENTED` |
| 3 | §8 STAGE 6–7 come esecuzione | replay di artefatti congelati | etichetta "artefatto congelato" obbligatoria |
| 4 | §8 STAGE 11 gate valutati | `disease`/`biomarker` **hardcoded** `SUPPORTED` | etichetta "ereditato dallo STAGE 5" + link all'evidenza |
| 5 | §8 STAGE 14–15 narratore | inesistenti | `SKIPPED` permanente, mai simulati |
| 6 | §24 token e latenza | il transport non li espone | `null` = "non disponibile", mai `0` |
| 7 | §4 "vecchio claim extractor fuori dal flusso" | il runner v2 **ne importa i loader** | reimplementati in `data_access.py` |
| 8 | §11 "non inventare una nuova API" | nessuna API estendibile esiste | namespace nuovo, ma **nessun endpoint esistente toccato** |

La #7 è la più insidiosa: senza reimplementare `_load_source_units` e
`_load_supporting_maps`, promuovere la pipeline **trascinerebbe dentro il
vecchio Claim Extractor**, violando un vincolo esplicito. Sono loader di dati,
non logica di estrazione: la separazione è fattibile.

## 3. MISSING — da costruire

| Componente | Note |
|---|---|
| `PipelineRun` / `PipelineStage` / `StageProducer` | contratti nuovi |
| vocabolario eventi della pipeline | il ledger esiste, il vocabolario no |
| colonna `stage_id` | migrazione v2→v3 additiva |
| namespace `/api/v1/research/pipeline/*` | 9 rotte |
| SSE | **nessun** `text/event-stream` nel repo |
| `data_access.py` | percorsi da configurazione, loader riscritti |
| intera UI di osservabilità | timeline, inspector, provenance, supervisor mode, dossier view |
| reducer canonico frontend | oggi 15 `useState` scollegati |

## 4. Rischi confermati o smentiti dall'analisi

| Rischio ipotizzato in Fase A | Esito |
|---|---|
| SourceUnit espone testo documentale | **smentito** — l'indice contiene solo locatori e `content_hash` |
| `architectural_decision.md` fuorviante | **confermato** — riporta la v1; la v2 ha 2 quote accettate |
| Enricher senza percorso positivo | **smentito** — 3 QUOTE, 2 accettate su `6ee64c5` |
| Move rompe i percorsi dati | **confermato** — `parents[3]` in `retrieval.py` |
| Promozione trascina il vecchio extractor | **confermato** — vedi §2 #7 |

Il rischio sicurezza dello STAGE 7 è quindi **più basso** di quanto stimato in
Fase A, e resta governato da una regola di contratto: `text` sempre `null`
nell'API.

### 4.1 Vincolo scoperto in Fase C — sorgenti sigillati

`benchmarks/mtb_evidence/final_experiment/systems_v1.json` sigilla gli SHA-256
di **120 sorgenti di runtime**, verificati da
`test_final_experiment_harness.py::test_every_frozen_input_validates`.
L'elenco include `backend/pipeline/agentic/ledger.py`, `ledger_schema.py`,
`backend/api/schemas.py`, `backend/comparison/*`, `backend/pipeline/agents/*` e
`backend/pipeline/agentic/*`.

**Conseguenza operativa:** nessuno di quei file può essere modificato senza
invalidare il record dell'esperimento comparativo finale della tesi. Aggiornare
i digest per compensare sarebbe falsificazione, non manutenzione.

Questo ha annullato la migrazione ledger v2 → v3 prevista dalla Fase B.
L'identità di stage viaggia nel payload dell'evento, che è già nel preimage
dell'hash: stessa tamper-evidence, zero file sigillati toccati.

### 4.2 Mappa sigillato / libero

| Area | File sigillati | Modificabile? |
|---|---:|---|
| `backend/pipeline/evidence/**` | 75 | **no** |
| `backend/pipeline/control/**` | 22 | **no** |
| `backend/pipeline/agents/**` | 10 | **no** |
| `backend/pipeline/agentic/**` | 8 | **no** |
| `backend/pipeline/llm/__init__.py` | 1 | **no** (import consentito) |
| `backend/comparison/**` | 3 | **no** |
| `backend/api/schemas.py` | 1 | **no** |
| `backend/api/main.py`, `routes.py`, `v3_*.py` | 0 | sì |
| `backend/config/requirements.txt` | 0 | sì |
| `backend/research_pipeline/**` (nuovo) | 0 | sì |

Il design regge senza modifiche sostanziali, perché due scelte prese in Fase B
per altre ragioni si rivelano necessarie:

1. il vocabolario eventi vive in `research_pipeline/events.py` e **non** estende
   `control/events.py` — che è sigillato;
2. `backend/pipeline/llm/__init__.py` è usato in **sola lettura** per le
   costanti di configurazione — l'import non altera il file, quindi non rompe il
   sigillo.

Da verificare **prima** di ogni modifica futura a `backend/`:

```bash
python -c "import json;print('\n'.join(json.load(open(
  'benchmarks/mtb_evidence/final_experiment/systems_v1.json'))['source_manifest']))"
```

## 5. Debito tecnico dichiarato

1. **Duplicazione fra branch.** I moduli entrano in `backend/research_pipeline/`
   su questo branch mentre restano in `benchmarks/` su
   `research/v3-end-to-end-pipeline-interaction-pilot`. Il "move" completo
   richiede un merge che l'utente ha escluso. Fino ad allora le due copie
   possono divergere.
2. **`architectural_decision.md` non aggiornato** sul branch corrente.
3. **Vitest non verificato** su Windows (`spawn EPERM` segnalato dalla spec
   precedente). Nessun test frontend è dichiarato passante finché non eseguito.
4. **Campione sperimentale minuscolo:** 7 chiamate, 2 quote accettate. Il
   sistema dimostra meccanica e sicurezza, non resa.

## 6. Hard stop — nessuno raggiunto

Verifica rispetto alla §27 del prompt:

| Condizione di arresto | Stato |
|---|---|
| design incompatibile con componenti fondamentali | no |
| necessario indebolire il validatore | no |
| necessario trasformare mock in risultati reali | no |
| frontend dovrebbe calcolare status clinici | no — reducer puro, nessun calcolo canonico |
| Gemma dovrebbe decidere gate o claim | no — filtro a monte preservato |
| perdita di provenance | no |
| impossibile distinguere candidate e prova documentale | no — etichetta obbligatoria |
| rischio di committare dati sensibili | no — indice senza testo, payload bounded |
| cancellare codice senza comprenderne l'uso | no — nessuna rimozione in Fase B |
| test esistenti falliscono in modo non compreso | **non verificabile**: non ancora eseguiti |

L'ultima riga è l'unica aperta ed è il primo compito della Fase C: eseguire la
baseline prima di modificare qualunque cosa.

## 7. Ordine di lavoro proposto per la Fase C

1. eseguire la baseline dei test backend e frontend, registrarne l'esito reale;
2. migrazione ledger v2→v3 additiva + test della catena di hash;
3. `data_access.py` con percorsi configurati e loader reimplementati;
4. promozione dei moduli in `backend/research_pipeline/`;
5. orchestratore con emissione eventi, verificato contro gli artefatti del pilot
   come baseline di regressione;
6. endpoint REST dietro flag;
7. SSE;
8. solo allora il frontend.

Il punto 5 è il controllo che rende la promozione verificabile: a parità di
input, output identici al pilot.
