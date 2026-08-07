# 06 — Impatto sulle claim e confini (§14)

Questo documento serve a una cosa sola: impedire che le correzioni vengano
lette come più di ciò che sono.

## A. Proprietà del runtime canonico — dopo questa fase

Vere di ciò che risponde a `POST /api/v1/research/pipeline/runs`, con
`graph_candidate_repository/2.0`:

- una fonte `Does Not Support`, `Contradicts` o `Neutral` **non può** produrre
  supporto positivo, e non raggiunge il bucket primario. Verificato su tutte le
  46 864 candidate;
- `Reduced Sensitivity` e `Adverse Response` sono trattate come direzioni
  avverse, non positive;
- un valore di direzione assente o non mappato **non è mai** positivo;
- nessuna inversione automatica della direzione viene applicata;
- un input non eleggibile non raggiunge retrieval, selezione o enricher, e
  termina con uno **stop controllato** che dichiara la categoria dell'input;
- gli stop di policy sono distinti dai guasti nel contratto
  (`CORRECT_STOP_REASONS` vs `FAILURE_STOP_REASONS`);
- una quote non validata dal validatore deterministico **non è presentabile**
  come citazione d'autore, né nel payload né nella UI;
- l'LLM non può emettere PMID, provenance, SourceUnit, canonical status o
  recommendation: lo schema della tool call ha cinque proprietà e il trasporto
  rifiuta le chiavi extra.

## B. Proprietà dimostrate nella materializzazione / evaluation GCA v3

**Non sono proprietà del runtime.** Restano vere del contratto 3.0 e del
percorso di valutazione che lo esercita:

- `source_support_polarity`, `source_alignment_status`, `graph_direction` come
  campi espliciti e distinti;
- `alteration_expression_ast` con semantica `AND` / `OR` e `PARTIAL_MATCH` mai
  promosso a `FULL_MATCH`;
- `intervention_structure` e `regimen_semantics_status`, con 572
  `MULTI_COMPONENT_UNRESOLVED` identificati;
- 0 violazioni di invariante su 46 142 candidate v3.

Il runtime **non consuma** nessuno di questi campi.
`GRAPH_CANDIDATE_REPOSITORY_VERSION` non è stato toccato e resta `2.0`.
`kg_retrieval_v3.py` resta codice non collegato (ISS-008, P2).

## C. Proprietà pianificate per una futura integrazione runtime

- migrazione del runtime a `graph_candidate_repository/3.0`, alle tre condizioni
  già elencate in `docs/runtime_v3_integration/13_runtime_switch_decision.md`;
- `stage_14_narrator` e `stage_15_narrative_verifier`, dichiarati
  `NOT_IMPLEMENTED` nel contratto (ISS-020);
- RQ5 / OncoKB, `PLANNED` con fattibilità documentata.

---

## Cosa NON si può scrivere nella tesi

> ❌ «la pipeline LIVE utilizza integralmente GraphCandidateAssertion v3»

Falso. Il runtime usa il contratto 2.0.

> ❌ «il runtime preserva la semantica delle alterazioni composte e dei regimi
> multi-componente»

Falso per il runtime. Il contratto 2.0 non ha AST né struttura del regime, e
`kg_retrieval._match_candidate` continua ad accettare `A AND B` per un caso che
menziona solo `A` (INV-C04, ISS non aperta perché già descritta come limite
della v2). **Questa fase non l'ha corretto e non lo rivendica.**

> ✅ «il runtime preserva la polarità della fonte»

Vero **dopo questa fase**, e solo per la polarità: è ciò che ISS-002 ha chiuso.
Va detto che la correzione riguarda il consumo della rappresentazione 2.0, non
la sua ricchezza semantica.

## Cosa cambia per RQ1

RQ1 misura la **materializzazione** e non è toccata: precision e recall restano
1.0, e le 486 `DIRECTION_INVERSION` / 1 091 `ALTERATION_LOST` / 1 294
`REGIMEN_SPLIT` restano le perdite del grafo sorgente, correttamente misurate.

Ciò che cambia è la separazione fra due affermazioni che l'audit aveva trovato
confuse:

| | prima | dopo |
|---|---|---|
| «la rappresentazione conserva la polarità» | vera (RQ1) | vera |
| «il runtime che la consuma conserva la polarità» | **falsa** | **vera** |

## Cosa cambia per RQ4

La claim di *selective routing* è ora dimostrabile **attraverso il runtime
canonico**, non solo attraverso la catena deterministica. Le metriche storiche
non erano sbagliate nel merito — i due percorsi concordano su tutti e 35 i casi
— ma erano misurate su un percorso che non poteva vedere la giunzione difettosa.

Va comunque dichiarato il limite ISS-012: nel benchmark congelato 9 casi su 35
(26 %) non raggiungono il gate perché il trasporto del parser fallisce. Quei
casi non sono stop del gate e non vanno conteggiati come tali.

## Cosa cambia per RQ2 e RQ3

RQ2: invariata nei numeri, con una garanzia in più —
`invented_quotes_presented_as_accepted = 0` è ora una proprietà distinta e
misurata.

RQ3: era già l'area più solida; l'unico punto che l'audit classificava
`PARZIALE` (l'output del modello raggiungeva il dossier presentato senza filtro)
è chiuso. Nessun confine è regredito.
