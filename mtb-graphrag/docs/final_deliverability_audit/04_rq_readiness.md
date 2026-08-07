# 04 — Sostenibilità di RQ1–RQ5

Dati: `evaluation/final_deliverability/rq_readiness_final.json`.

## RQ1 — DELIVERABLE (shadow / materializzazione)

Verificato **senza rieseguire** gli script, per non attivare ISS-017 (P3, che
li fa scrivere sulle directory committate). Due prove indipendenti:

1. **Hash.** `rq1/aggregate_metrics.json`, `gca_v3/aggregate_metrics.json`,
   `rq4/benchmark.jsonl`, `candidates.jsonl` (2.0) e `evidence_bundles.jsonl`
   sono **byte-identici** al blob di `0219e0a`. Quattro altri file differiscono
   solo nei fine riga (vedi `00_repository_state.md`).
2. **Chiusura transitiva degli import.** Nessuno fra `evaluation.run_rq1`,
   `run_rq2` e `run_gca_v3_audit` raggiunge alcuno dei quattro moduli modificati
   dal fix sprint. Le metriche sono **strutturalmente** inalterate.

```
materialization_precision = 1.0     direction_inversions_graph = 486
materialization_recall    = 1.0     ALTERATION_LOST            = 1091
field_completeness        = 1.0     REGIMEN_SPLIT              = 1294
```

**Condizione**: dichiarare che RQ1 misura la materializzazione da un export CSV
congelato, non una query Neo4j live (`kg_source.neo4j_used = false`).

### Separazione RQ1 shadow vs runtime — §8

| | RQ1 / GCA v3 (shadow) | Runtime / GCA 2.0 |
|---|---|---|
| polarità della fonte | campo esplicito `source_support_polarity` | letta da `source_properties`, ora **sicura** (ISS-002) |
| alterazioni composte | AST con `AND`/`OR`, `PARTIAL_MATCH` mai promosso | **non rappresentate** |
| regimi multi-componente | 572 `MULTI_COMPONENT_UNRESOLVED` | **non rappresentati** |
| consumato dal runtime | **no** | sì |

La separazione è netta e va mantenuta nella tesi.

## RQ2 — PARZIALE (fattibilità, non copertura)

I sette livelli restano distinguibili nel codice e negli artifact. Denominatori,
riportati **senza modifiche**:

```
candidate totali        46 864
con PMID                 8 230
PMID unici               2 229
documento disponibile       15
raggiungibili end-to-end    16
```

**Condizione**: presentare RQ2 come studio di fattibilità della catena di
grounding, affiancando sempre il denominatore end-to-end (ISS-007).

Una garanzia in più rispetto all'audit precedente:
`invented_quotes_presented_as_accepted = 0` è ora una proprietà distinta e
misurata, non solo `invented_quotes_accepted`.

## RQ3 — DELIVERABLE

```
prompt_only_restrictions   = 0
uncontrolled_boundaries    = 0
impossible_by_construction = 7
validated_downstream       = 2
```

È l'area più solida, e questo audit la trova **rafforzata**: il punto che
l'audit precedente classificava `PARZIALE` — l'output del modello raggiungeva il
dossier presentato senza filtro — è chiuso da ISS-003.

## RQ4 — DELIVERABLE

Benchmark rieseguito attraverso `orchestrator.run_case`, in directory
temporanea. **Riproduzione identica** all'artifact committato salvo timestamp.

```
casi                                35
non eleggibili                      27
controlled_stops_ok                 18
noneligible_retrieval_calls          0
forbidden_downstream_calls           0
expected_controlled_stops_failed     0
runtime_exceptions                   0
path_disagreements                   0
parser_transport_failures            9
```

`path_disagreements = 0` conferma quanto dichiarato dal fix sprint: sui 35 casi
`orchestrator.run_case` e `casecontext.pipeline.run` producono lo stesso
`eligibility_status`. Le metriche storiche non erano sbagliate nel merito; erano
misurate su un percorso che non poteva vedere la giunzione difettosa.

**Condizione**: dichiarare che 9 casi su 35 (26 %) non raggiungono il gate
perché il trasporto del parser fallisce (ISS-012). Non sono stop del gate e non
vanno conteggiati come tali — lo script li conta già a parte.

## RQ5 — PLANNED

`oncokb_called = false`. Nessun modulo di `backend/research_pipeline` importa
OncoKB. Il §17 lo esclude dai requisiti di freeze purché resti dichiarato
pilot/future work: lo è, con studio di fattibilità e report di licensing.
