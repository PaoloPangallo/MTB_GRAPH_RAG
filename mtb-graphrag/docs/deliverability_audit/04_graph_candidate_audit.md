# 04 — GraphCandidateAssertion e invarianti semantici del KG

Sonda: `evaluation/deliverability/probes/probe_c_kg_invariants.py`.
Dati: `evaluation/deliverability/raw/C01_kg_invariants.jsonl`,
`evaluation/deliverability/architecture_invariants.jsonl`.

**Le due colonne restano separate per tutto il documento.** Un invariante che
regge in 3.0 ma non in 2.0 **non è una proprietà del runtime**: 2.0 è ciò che
`orchestrator.run_case` esegue, 3.0 è ciò che `evaluation/` misura.

## §7 — Quale contratto è realmente in uso

| Campo richiesto dal §7 | in 2.0 (RUNTIME) | in 3.0 (SHADOW) | **letto dal runtime** |
|---|:-:|:-:|:-:|
| `candidate_id` | ✅ | ✅ | ✅ |
| `payload_hash` | ✅ | ✅ | ❌ |
| `disease` | ✅ | ✅ | ✅ |
| `biomarkers` (gene/alteration) | ✅ lista piatta | ✅ + AST | ✅ (solo `label`) |
| `document_identifiers` | ✅ | ✅ | ✅ (a valle) |
| `predicate` | ✅ | ✅ | ✅ (solo per il dossier) |
| `direction` | ✅ **campo ibrido** | — sostituito | ✅ |
| `graph_direction` | ❌ | ✅ | ❌ |
| `source_support_polarity` | ❌ (solo in `source_properties`) | ✅ | ❌ |
| `source_supported_direction` | ❌ | ✅ | ❌ |
| `source_alignment_status` | ❌ | ✅ | ❌ |
| `alteration_expression_raw` | ❌ | ✅ | ❌ |
| `alteration_terms` | ❌ | ✅ | ❌ |
| `alteration_expression_ast` | ❌ | ✅ | ❌ |
| `alteration_parse_status` | ❌ | ✅ | ❌ |
| `intervention_expression_raw` | ❌ | ✅ | ❌ |
| `intervention_components` | ❌ | ✅ | ❌ |
| `intervention_structure` | ❌ | ✅ | ❌ |
| `regimen_semantics_status` | ❌ | ✅ | ❌ |
| `source_path_ids` | ❌ (`graph_path`, `edge_ids`, `node_ids`) | ✅ | ❌ |

`contract_version` in 3.0 è `graph-candidate-assertion/3.0`; in 2.0 il campo si
chiama `candidate_version` e vale `"2.0"`.

**`graph_candidate_contract_version` effettivamente in uso dal runtime = `2.0`.**

## §8 — Invarianti semantici: 6 violazioni su 7 nel runtime

### ⛔ INV-C01 — HARD STOP §28: la polarità negativa viene convertita in positiva

`backend/research_pipeline/determinism/gates.py:24-40`

```python
def direction_consistency(candidate_direction, evidence_kind):
    direction = _norm(candidate_direction)          # lowercase, alfanumerico
    if "resistance" in direction: ...
    if "sensitivity" in direction or "response" in direction or "support" in direction:
        if evidence_kind in POSITIVE_EVIDENCE_KINDS:   # {"RESPONSE", "BENEFIT"}
            return "CONSISTENT"
```

`_norm("Does Not Support")` → `"does not support"`, e
**`"support" in "does not support"` è `True`.**

Esito misurato, eseguendo la funzione reale:

```python
direction_consistency("Does Not Support", "RESPONSE")   -> "CONSISTENT"
direction_consistency("Does Not Support", "BENEFIT")    -> "CONSISTENT"
direction_consistency("Reduced Sensitivity", "RESPONSE")-> "CONSISTENT"
direction_consistency("Adverse Response",  "RESPONSE")  -> "CONSISTENT"
```

e a valle, `evaluate_association("THERAPY_EVALUATION", {"direction": "Does Not Support"}, [enrichment accettato RESPONSE])`:

```json
{"status": "DIRECT",
 "support_mask": {"disease":"SUPPORTED","biomarker":"SUPPORTED",
                  "intervention":"SUPPORTED","direction":"SUPPORTED"},
 "gate_bucket": "PRIMARY_BUCKET",
 "warnings": []}
```

**Una candidate la cui fonte afferma esplicitamente «Does Not Support» riceve
status `DIRECT`, maschera `SUPPORTED` su tutti e quattro gli assi, bucket
primario e nessun warning.**

Popolazione nel repository che il runtime usa:

| `direction` | candidate | causa |
|---|---:|---|
| `Does Not Support` | 513 | `"support" in "does not support"` |
| `Sensitivity/Response` **con** `evidence_direction = Does Not Support` | 213 | il runtime non legge mai la polarità della fonte |
| `Reduced Sensitivity` | 14 | `"sensitivity" in "reduced sensitivity"` |
| `Adverse Response` | 12 | `"response" in "adverse response"` |
| **totale** | **752** | |

Di queste, **1 è raggiungibile end-to-end** (possiede un EvidenceBundle):
`GCA-003ca9889b3d8906d4674f37`, `direction = Sensitivity/Response`,
`evidence_direction = Does Not Support`.

Il §28 elenca fra gli hard stop: *«source polarity negativa viene convertita
automaticamente in positiva»*. **La condizione è soddisfatta.** Per mandato il
problema è stato rilevato e documentato, non corretto.

**Severità P0.** Invalida direttamente la claim di *representation fidelity*
(RQ1) e la separazione fra direzione del grafo e supporto documentale sul
percorso realmente eseguito.

**Fix minimo** (non applicato): sostituire i test di sottostringa con un
confronto su valori normalizzati espliciti, gestendo la negazione prima
dell'affermazione (`"does not support"` va verificato **prima** di `"support"`),
e leggere `source_properties.evidence.evidence_direction` come asse separato da
`direction`. Serve inoltre un test che scorra tutte le 46 864 candidate — esiste
già l'equivalente per v3, non per v2.

### ❌ INV-C02 — Il runtime non legge la polarità della fonte

`grep -rn "evidence_direction" backend/research_pipeline/` → **0 occorrenze**.

L'informazione **esiste** in 2.0, dentro
`source_properties.evidence.evidence_direction` (7 177 `Supports`, 999 `Does Not
Support`, 54 vuoti, 38 634 assenti). Non è persa nella materializzazione: è
ignorata dal consumo.

Questa è una distinzione importante per la tesi. Il materializzatore v2
**conserva** la polarità; è il retrieval e il gate a non consultarla.

### ❌ INV-C03 — `direction` confonde due assi

Tabulazione incrociata sulle 46 864 candidate:

| `evidence_direction` (polarità della fonte) | `direction` (campo top-level) | n |
|---|---|---:|
| Supports | Supports | 4 295 |
| Supports | Sensitivity/Response | 1 945 |
| Supports | Resistance | 911 |
| **Does Not Support** | Does Not Support | 513 |
| **Does Not Support** | **Resistance** | **273** |
| **Does Not Support** | **Sensitivity/Response** | **213** |
| Supports | Reduced Sensitivity | 14 |
| Supports | Adverse Response | 12 |

`direction` contiene talvolta la **polarità della fonte** (`Supports` / `Does Not
Support`), talvolta la **direzione clinica dell'asserzione**
(`Sensitivity/Response`, `Resistance`, …). Sono due assi ortogonali in un solo
campo. **486 candidate** hanno una fonte che non supporta e un `direction`
clinico indistinguibile da uno supportato.

È esattamente il difetto che il contratto 3.0 separa in `graph_direction`,
`source_support_polarity`, `source_supported_direction` e
`source_alignment_status` — nel repository che il runtime non usa.

### ❌ INV-C04 — `A AND B` corrisponde a un caso che menziona solo `A`

```python
candidate.biomarkers = [{"label": "KRAS G12D"}, {"label": "BRAF V600E"}]
case.biomarkers      = [KRAS G12D]              # solo uno dei due
_match_candidate(...) -> (True, ['DISEASE_COMPATIBLE','BIOMARKER_COMPATIBLE','INTERVENTION_COMPATIBLE'])
```

`kg_retrieval._match_candidate` riga 93:

```python
gene_ok = bool(terms) and any(any(_term_matches(t, l) for l in labels) for t in terms)
```

`any(...any(...))` è soddisfatto da **una sola** corrispondenza. Nel retrieval v2
**non esiste alcun codice `PARTIAL_MATCH`**: il match è pieno o assente, e una
corrispondenza parziale è indistinguibile da una completa.

### ❌ INV-C05 — Alterazioni clinicamente distinte collassano l'una sull'altra

`_term_matches` (righe 40-49) accetta *un qualunque token condiviso più lungo di
2 caratteri*. Il simbolo del gene è sufficiente:

| termine del caso | label della candidate | match |
|---|---|:-:|
| `kras g12d` | `kras g12c` | ✅ |
| `braf v600e` | `braf v600k` | ✅ |
| `egfr exon 19 deletion` | `egfr exon 20 insertion` | ✅ |
| `her2 amplification` | `her2 mutation` | ✅ |
| `tp53 r175h` | `tp53 r273h` | ✅ |

5 su 5. Queste coppie non sono equivalenti in oncologia: EGFR exon 19 deletion è
sensibilizzante mentre exon 20 insertion è tipicamente resistente; KRAS G12C ha
un inibitore dedicato che G12D non ha.

Il commento nel codice motiva la regola con la copertura di
`"microsatellite instability (msi)"` contro `"msi high"` «senza una tabella di
sinonimi hardcoded». La soluzione a quel caso produce un sovra-matching molto
più ampio, non misurato.

**Severità P0**, per la stessa ragione di INV-C01: è una perdita di fedeltà
rappresentativa sul percorso eseguito, ed è la claim centrale di RQ1.

### ❌ INV-C06 — Nel runtime i regimi non hanno alcuna rappresentazione

Misurato su 2.0:

```
campo `regimen`       : VUOTO su tutte e 46 864 le candidate
campo `interventions` : 0 elementi su 10 524, 1 elemento su 36 340, mai più di 1
```

Non esiste `intervention_structure` né `regimen_semantics_status`. I regimi
multi-farmaco sopravvivono solo come **label composita** di un unico
`intervention`. E `_match_candidate` riga 103 usa
`target_value in label or label in target_value`:

```python
case.target_intervention = "encorafenib"
candidate.interventions  = [{"label": "Encorafenib, Cetuximab"}]
-> (True, [..., 'INTERVENTION_COMPATIBLE'])
```

**L'evidenza di una combinazione viene attribuita al singolo agente**, senza
alcun segnale di regime irrisolto. v3 identifica 572
`MULTI_COMPONENT_UNRESOLVED`; nel runtime sono indistinguibili da agenti
singoli.

*(Nota di precisione: le 361 label che contengono `+`, `,`, `and` o `plus` sono
in larga parte nomi chimici con virgole — «INSULIN, REGULAR, HUMAN» — e quel
numero **non** misura i regimi reali. Il numero affidabile è 572, da v3.)*

### ✅ INV-C07 — Il contratto 3.0 rappresenta tutto ciò che manca a 2.0

46 142 candidate, con distribuzioni dal manifest verificate rileggendo il file:

```
source_support_polarity      SUPPORTS 7177 · DOES_NOT_SUPPORT 873 · NOT_REPORTED 38092 …
source_alignment_status      NOT_AVAILABLE 38688 · (allineate / non allineate / neutre)
alteration_parse_status      PARSED_EXACT 1010 · ATOMIC 6498 · MISSING 38634
intervention_structure       SINGLE_AGENT 35046 · MULTI_COMPONENT_UNRESOLVED 572 · UNKNOWN 10524
```

Il lavoro v3 è solido, e il manifest dichiara onestamente le proprie
`known_limitations` (l'export non distingue combinazione da alternativa da
sequenza; `component_role` è sempre `UNKNOWN`; nessuna normalizzazione
farmacologica).

### ❌ INV-C08 — Ma nessuno di quei campi raggiunge il runtime

Vedi `02_target_vs_runtime.md`. `admission.py` e `repository_v3.py` sono
`SHADOW_EVALUATION`; `kg_retrieval_v3.py` è `DEAD_OR_UNREACHABLE`.

### ✅ INV-C09 — GraphCandidateAssertion resta distinta dall'evidenza documentale

Questo invariante **regge**, ed è un merito reale del progetto.

`orchestrator.py:439-445` — lo stage 5 dichiara esplicitamente nel proprio
output:

```python
retrieval_preview = {"graph_derived": True, "documentary_proof": False, ...}
```

Il supporto documentale è un asse **separato**, calcolato solo dopo la
risoluzione del documento, la materializzazione della SourceUnit, la proposta di
quote e la sua validazione. Nessun modulo tratta la presenza di una candidate
nel KG come prova clinica, come claim degli autori o come raccomandazione. La
`redaction.redact_retrieval_result` impedisce inoltre che il testo della fonte
esca insieme alla candidate.

## Sintesi del Checkpoint C

```
graph_candidate_contract_version   = "2.0"   (runtime)
source_polarity_preserved          = false   (752 candidate, 1 raggiungibile end-to-end)
automatic_direction_inversions     = 752
compound_alteration_terms_lost     = A AND B trattato come A  (nessun PARTIAL_MATCH esiste)
compound_operators_lost            = tutti: v2 non ha AST
unresolved_regimens_split          = nessuna rappresentazione di regime nel runtime
invented_regimen_semantics         = 0  (non inventa: semplicemente non rappresenta)
candidate_document_separation      = PRESERVATA ✅
```

Le stesse proprietà, misurate su 3.0, danno tutti zero — ed è il risultato che
`docs/runtime_v3_integration/` riporta correttamente. La differenza è quale dei
due repository risponde a `POST /runs`.
