# 13 — Decisione finale sulla deliverability

# `NOT_YET_DELIVERABLE`

Esistono tre blocker P0 concreti. Nessuno richiede una riprogettazione: sono
correzioni chirurgiche in quattro file. Con esse il repository diventa
`DELIVERABLE_WITH_MINOR_FIXES`.

Il verdetto **non** è `ARCHITECTURALLY_INCONSISTENT`: il runtime implementa
davvero l'architettura descritta, e la separazione fra LLM e core deterministico
— il contributo scientifico principale — è enforced dal codice, non dai prompt.

---

## §32 — Report finale

| | |
|---|---|
| Branch | `feature/v3-runtime-gca3-eligibility-gate` |
| HEAD | `0219e0a7a4a063668c72c941413fbd8382838b32` (invariato) |
| Working tree iniziale | **non pulita** — 3 staged, 12 untracked, **0 file `.py`** |
| Working tree finale | identica all'iniziale + 2 directory di audit |
| Runtime canonico | `orchestrator.py::run_case` via `research_routes`, dietro `VERIFIABLE_PIPELINE_RESEARCH_ENABLED` |
| GCA repository usato | `graph_candidate_repository/**2.0**` |
| Contract version | `2.0` (3.0 esiste, validato, **shadow**) |
| LIVE disponibile | ❌ — 503 senza `data_cache/` |
| REPLAY disponibile | ✅ — 5 casi end-to-end fino al dossier |
| CaseContext Parser | ✅ LLM, forced tool call, `gemma4:cloud` |
| Eligibility Gate | ✅ deterministico, `stage_3b`, **0 riferimenti a LLM in 10 moduli** |
| Contradiction detection | ✅ deterministica |
| Forbidden downstream calls | **0** |
| GCA source polarity | ❌ **752 inversioni** |
| Compound alterations | ❌ `A AND B` ≡ `A`; nessun `PARTIAL_MATCH` |
| Unresolved regimens | ❌ nessuna rappresentazione nel runtime |
| DocumentResolver | ✅ `network=False`, nessun fallback |
| Candidate-level provenance | ✅ `scope: evidence_record` vs `linked_publication` |
| SourceUnit | ✅ ancorata, solo locatori + `content_hash` senza cache |
| Paper Context Enricher | ✅ LLM, schema chiuso a 5 proprietà |
| QUOTE \| ABSTAIN | ✅ enforced dal trasporto |
| Quote validator | ✅ letterale, **indipendente dall'LLM** |
| Invented quote accepted | **0** |
| Invented SourceUnit accepted | **0** |
| Canonical status | ✅ deterministico |
| Structured dossier | ✅ costruito prima di ogni narrazione |
| Dossier Narrator | **NOT IMPLEMENTED** |
| Narrative Verifier | **NOT IMPLEMENTED** |
| Event/provenance logging | ✅ ledger append-only SQLite, catena SHA-256 |
| LIVE/REPLAY distinction | ✅ **enforced, asimmetrica** |
| Unit + integration tests | **3 047 passed**, 17 skipped, 36 860 subtest |
| Evaluation tests | **91 passed** |
| Frontend tests | 195 passed (seriale) · **build FALLISCE** |
| Smoke tests | 18 LIVE + 5 REPLAY + 14 validazione quote + 14 routing |
| RQ1 readiness | **DELIVERABLE** con delimitazione |
| RQ2 readiness | **PARZIALE** — fattibilità, non copertura |
| RQ3 readiness | **DELIVERABLE** ✅ |
| RQ4 readiness | **PARZIALE** — bloccata da ISS-001 |
| RQ5 status | **PLANNED**, dichiarato e conforme |
| Reproducibility | dati e metriche ✅ · ambiente ⚠️ · LIVE ❌ |
| Contamination findings | 1 P0, 1 P1, 3 P2, 3 P3 · **4/4 controlli critici superati** |
| P0 / P1 / P2 / P3 | **3 / 4 / 8 / 6** |

### Conferme richieste dal §32

```
working_tree_initially_clean                 = false
code_modified_during_audit                   = false
canonical_runtime_identified                 = true
legacy_runtime_confusion_found               = true

casecontext_parser_implemented               = true
pre_retrieval_gate_implemented               = true
noneligible_retrieval_calls                  = 0
adversarial_forbidden_calls                  = 0

graph_candidate_contract_version             = "2.0"
source_polarity_preserved                    = false
automatic_direction_inversions               = 752
compound_alteration_terms_lost               = true  (A AND B trattato come A)
compound_operators_lost                      = true  (v2 non ha AST)
unresolved_regimens_split_into_components    = n/a   (nessuna rappresentazione)
invented_regimen_semantics                   = 0

candidate_document_separation_preserved      = true
candidate_level_provenance_available         = true
sourceunit_grounded                          = true

quote_abstain_contract_enforced              = true
invented_quotes_accepted                     = 0
invented_sourceunits_accepted                = 0
wrong_document_quotes_accepted               = 0

canonical_status_deterministic               = true
llm_can_directly_change_canonical_status     = false
narrator_can_change_canonical_dossier        = n/a
narrative_verifier_implemented               = false

live_replay_distinction_enforced             = true
experimental_contamination_found             = true

rq1_deliverable                              = true
rq2_deliverable                              = PARZIALE
rq3_deliverable                              = true
rq4_deliverable                              = PARZIALE
rq5_status                                   = "PLANNED"

reproducible_from_clean_repository           = false

p0_count = 3    p1_count = 4    p2_count = 8    p3_count = 6

push_executed  = false
merge_executed = false
```

---

## §27 — Criteri di deliverability, uno per uno

| Criterio | Esito |
|---|:-:|
| non esistono P0 aperti | ❌ **3** |
| gli eventuali P1 sono assenti o minori e isolati | ⚠️ 4, isolati ma non minori |
| RQ1–RQ4 supportate da codice e artifact riproducibili | ⚠️ RQ1 e RQ3 sì; RQ2 e RQ4 parzialmente |
| il runtime non viola gli invarianti fondamentali | ❌ ISS-002 |
| LIVE e REPLAY distinguibili | ✅ |
| GCA mantiene provenance e semantica necessarie | ⚠️ provenance sì, semantica della polarità no |
| quote inventate non vengono accettate | ✅ nello stato canonico · ❌ nel dossier presentato |
| SourceUnit inventate non vengono accettate | ✅ |
| input non eleggibili non raggiungono il retrieval | ✅ **verificato indipendentemente** |
| l'LLM non controlla il canonical status | ✅ |
| dossier canonico separato dalla narrazione | ✅ (per assenza di narratore) |
| esperimenti fondamentali ricostruibili | ✅ 5 script su 5, exit 0 |

---

## §34 — Le dodici domande

**1. Il runtime realmente eseguito corrisponde all'architettura finale descritta
nella tesi?**
Nella struttura sì: 13 dei 15 stage sono implementati nell'ordine dichiarato, e
il gate pre-retrieval è al posto giusto. Nella semantica **no**, su un punto: la
tesi descrive un contratto GCA con polarità della fonte, AST delle alterazioni e
struttura dei regimi; il runtime consuma il contratto **2.0**, che non ha nessuno
dei tre. Il repository lo dichiara onestamente
(`runtime_default_changed_to_v3 = false`), quindi non c'è discrepanza fra codice
e documentazione — c'è una scelta di perimetro che la tesi deve rendere esplicita.

**2. I confini fra LLM e core deterministico sono enforced dal codice o dipendono
dai prompt?**
**Enforced dal codice.** 8 punti su 9 del §21 sono `IMPOSSIBLE_BY_CONSTRUCTION` o
`VALIDATED_DOWNSTREAM`; **zero** sono `PROMPT_ONLY_RESTRICTION`. Lo schema della
tool call ha cinque proprietà e il trasporto rifiuta le chiavi extra: il modello
non *può* emettere un PMID, una provenance o un canonical status. La catena
deterministica CaseContext→gate contiene **zero riferimenti** a LLM in dieci
moduli. Questa è la risposta più solida dell'audit.

**3. Una GraphCandidateAssertion resta distinta da evidenza documentale e
supporto validato lungo tutta la pipeline?**
**Sì.** Lo stage 5 dichiara `graph_derived: true, documentary_proof: false`;
`_ACCEPTED_OUTCOMES` codifica che solo una validazione accettata rende
`document_grounded` vero; `redact_retrieval_result` impedisce che il testo della
fonte esca con la candidate. Ben implementato.

**4. Una quote inventata o una SourceUnit inventata possono entrare nel dossier
canonico?**
**SourceUnit: no.** **Quote: sì** — non nello *stato* canonico, che resta
`AMBIGUOUS / NO_DOCUMENT_SIGNAL`, ma nel *payload* del dossier e nella UI, dove
viene mostrata come citazione d'autore. È ISS-003.

**5. Il sistema sa fermarsi prima del retrieval quando il CaseContext non è
eleggibile?**
**Sì, e l'ho misurato invece di leggerlo:** 0 chiamate al retrieval su 12 casi
non eleggibili con parser stub e su 5 categorie in LIVE con LLM reale. Ma **non
sa dirlo**: attraverso il runtime la fermata si presenta come un guasto
(ISS-001).

**6. Source polarity, alterazioni composte e regimi irrisolti restano
semanticamente preservati nel runtime reale?**
**No, su tutti e tre.** 752 inversioni di polarità, `A AND B` trattato come `A`,
`KRAS G12D` che corrisponde a `KRAS G12C`, nessuna rappresentazione di regime.
Tutti e tre sono risolti nel contratto 3.0 — che il runtime non usa.

**7. LIVE, REPLAY, mock, fixture e cache sono sufficientemente distinti da
rendere interpretabili gli esperimenti?**
**Sì, ed è fatto meglio della media.** La classificazione è asimmetrica per
costruzione, `HYBRID` non è richiedibile, `DETERMINISTIC_CACHE` è deliberatamente
distinto da `RECORDED_REAL_RUN`, e il fallback silenzioso è stato attivamente
rimosso. Nessun mock è raggiungibile dal runtime.

**8. RQ1, RQ2, RQ3 e RQ4 sono sostenibili con gli artifact attuali?**
RQ1 sì, con delimitazione. RQ3 **pienamente**. RQ2 come studio di fattibilità,
non come copertura. RQ4 no, finché ISS-001 non è corretto e la metrica non è
rimisurata attraverso l'orchestratore.

**9. Quali risultati non sarebbero riproducibili da un clone pulito?**
Qualunque run LIVE; i livelli 3-7 della catena di grounding di RQ2; la
validazione delle quote end-to-end; il build del frontend; la rilevanza semantica
dei PMID; la fedeltà semantica di v3 rispetto a un giudizio esperto; il ramo non
eleggibile attraverso il runtime.

**10. Esiste un motivo tecnico o sperimentale per NON congelare il codice?**
**Sì: ISS-002.** Congelare ora significherebbe congelare un runtime che
classifica come «evidenza diretta, bucket primario, nessun warning» una candidate
la cui fonte afferma di non supportarla. In uno strumento destinato a un
Molecular Tumor Board non è un difetto accettabile in un deliverable.

**11. Qual è il numero minimo di interventi necessari prima del freeze?**
**Quattro correzioni di codice** (ISS-001, ISS-002, ISS-003, ISS-004) in
**quattro file**, **due file di configurazione** (ISS-006), **due nuovi test**, e
**un rerun** del benchmark RQ4 (ISS-005). ISS-007 è una correzione di
presentazione nella tesi.

**12. Il repository è deliverable?**
**Non ancora.** Ma è molto più vicino di quanto il numero «3 P0» suggerisca.

---

## Cosa questo audit ha trovato di *giusto*

Un audit di falsificazione tende a produrre solo l'elenco di ciò che è rotto. Va
detto anche il resto, perché è ciò che rende il progetto recuperabile in poche
ore invece che in settimane.

- **Nessuna metrica dichiarata è gonfiata.** 3 047 / 91 / 195 riprodotti
  esattamente, flakiness inclusa. Cinque script di evaluation su cinque girano
  oggi e riproducono i propri artifact byte a byte, timestamp esclusi.
- **Nessuna self-comparison del materializzatore.** `precision = recall = 1.0`
  di RQ1 è un risultato, non una tautologia: l'atteso è costruito dall'export CSV
  grezzo, senza importare il materializzatore.
- **La separazione dell'autorità dell'LLM è reale e verificabile.** Non è una
  frase in un prompt: è uno schema a cinque campi, un trasporto che rifiuta le
  chiavi extra, un validatore letterale, un `frozenset` di due stage su quindici.
- **Il fallback silenzioso è stato attivamente rimosso**, e i commenti nel codice
  documentano *perché*. `POST /runs` in LIVE risponde 503 invece di degradare in
  un replay travestito.
- **Il repository misura già i propri limiti.** `direction_inversions_graph: 486`
  — il mio conteggio indipendente ha dato 486. `check_origin` dichiara sei
  controlli `NOT_IMPLEMENTED` e impedisce per costruzione che dichiarino uno
  stage. RQ2 rifiuta di rivendicare una precisione semantica che non può
  misurare. L'harness RQ4 registra nel proprio artifact di essere stato costretto
  a sovrascrivere l'endpoint di default.

Un repository che misura onestamente i propri limiti è un repository di cui ci si
può fidare. I tre P0 sono difetti di *giunzione* — fra il gate e il contratto
della run, fra la rappresentazione e il suo consumo, fra la validazione e la
presentazione — non difetti di concezione.

---

## Verdetto

```
NOT_YET_DELIVERABLE
```

con la nota che il percorso verso `DELIVERABLE_WITH_MINOR_FIXES` è breve,
localizzato e interamente specificato in `12_open_issues.md`.
